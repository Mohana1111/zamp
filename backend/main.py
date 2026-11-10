"""
ClearPay AP - Main FastAPI Application.

Full REST API implementing:
- Health & Dashboard Overview with Dual-Convention Real-time KPIs
- Multi-Source Ingestion (Upload, Gmail Live/Simulated, Drive, Webhook, Slack, WhatsApp, Outlook)
- 8-Stage Deterministic Invoice Run Execution
- Side-by-Side Compare & Highlight Workbench Endpoints
- PO Consumption Ledger & Overbilling Tracker
- File Previews (Serving Raw Files & PyMuPDF-rendered PNG Visual Previews for All Formats)
- Human Reviewer Decision Overrides
- Live Demo State Reset
"""

import shutil
import base64
import zipfile
import io
import os
import re
import time
import asyncio

from pathlib import Path
from datetime import datetime, date
from typing import List, Optional, Literal, Dict, Any, Tuple
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.auth import (
    LoginRequest,
    SignupRequest,
    AuthResponse,
    UserPublic,
    authenticate_user,
    register_user,
    create_session,
    get_session_user,
    delete_session,
)

import json
import uuid
from backend.schemas import (
    InvoiceRunResult,
    StoredQuotation,
    StandardInvoice,
    SourceInfo,
    ExtractedField,
    StandardLineItem,
)
from backend.extractor import (
    extract_standard_invoice,
    render_file_preview_png,
    set_ai_api_key,
    get_ai_config,
    generate_document_summary_and_flaws,
)
from backend.engine import (
    process_invoice_file,
    attach_quotation_to_run,
    record_human_approval,
    get_all_runs,
    get_run,
    override_run_decision,
    reset_engine_state,
    load_vendors,
    load_purchase_orders,
    load_po_lines,
    load_fx_rates,
    load_quotations,
    save_quotations,
    get_quotation_by_id,
    create_or_update_quotation,
    delete_quotation,
    link_quotation_to_run,
    compute_document_duration,
    update_run_details,
    delete_run,
    DATA_DIR,
    SAMPLE_INVOICES_DIR,
    VENDORS_CSV,
    save_vendor_record,
    update_vendor_record,
    soft_delete_vendor,
    get_vendor_stats,
    get_dashboard_metrics,
)
from backend.policy import (
    load_settings,
    save_settings,
    get_vendor_policy,
    save_vendor_policy,
)
from backend.llm import get_ai_status
from backend.persist import start_persistence, stop_persistence, get_persistence_mode
from fastapi.responses import StreamingResponse


from backend.connectors import (
    get_gmail_status,
    connect_gmail,
    list_gmail_messages,
    pull_gmail_messages,
    send_email_to_agent,
    add_inbound_email,
    add_extension_push_message,
    reset_gmail_inbox,
    get_all_platforms,
    pull_all_sources,
    install_extension_direct,
    uninstall_extension_direct,
    GMAIL_CONFIG,
    AGENT_EMAIL_CONFIG,
    generate_agent_email,
    DOWNLOADS_DIR,
    poll_and_process_bot_inbox,
    test_bot_imap_connection,
    remove_gmail_message_for_run,
)

# Initialize FastAPI App
app = FastAPI(
    title="ClearPay AP — Autonomous Invoice-to-Decision API",
    description="PS-1 Compliant Automated AP Processing Engine with 8-Stage Deterministic Rules & Compare Workbench",
    version="1.0.0",
)

# Enable CORS for Frontend (configurable via CORS_ORIGINS, default same-origin / *)
cors_env = os.getenv("CORS_ORIGINS", "*").strip()
if not cors_env or cors_env == "*":
    cors_origins = ["*"]
else:
    cors_origins = [o.strip() for o in cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOADS_DIR = DATA_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Upload limits & sanitization
MAX_UPLOAD_FILES = 10
MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB


def _sanitize_filename(filename: Optional[str]) -> str:
    """Sanitizes filename and strips path traversal sequences."""
    if not filename:
        return f"file_{uuid.uuid4().hex[:8]}"
    base = Path(filename).name
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", base).strip("._")
    if not safe:
        safe = f"file_{uuid.uuid4().hex[:8]}"
    return safe


async def _save_upload_file(file: UploadFile, dest_path: Path, max_bytes: int = MAX_FILE_SIZE_BYTES) -> int:
    """
    Streams uploaded file to dest_path safely.
    Raises 413 if file exceeds max_bytes, cleaning up partial file.
    """
    resolved_dest = dest_path.resolve()
    resolved_uploads = UPLOADS_DIR.resolve()
    if not str(resolved_dest).startswith(str(resolved_uploads)):
        raise HTTPException(status_code=400, detail="Invalid filename or path traversal detected")

    size = 0
    try:
        with open(dest_path, "wb") as buffer:
            while chunk := await file.read(65536):
                size += len(chunk)
                if size > max_bytes:
                    break
                buffer.write(chunk)
    except Exception as e:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Error saving upload: {e}")

    if size > max_bytes:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        raise HTTPException(
            status_code=413,
            detail=f"File '{file.filename}' exceeds maximum allowed size of 15MB."
        )

    return size

# ---------------------------------------------------------------------------
# Sample Scenarios Catalog
# ---------------------------------------------------------------------------
def _load_scenarios_catalog():
    p = DATA_DIR / "sample_scenarios.json"
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

SCENARIOS_CATALOG = _load_scenarios_catalog()


# ---------------------------------------------------------------------------
# Startup Event & Autonomous Background Bot Poller
# ---------------------------------------------------------------------------
async def _bot_poller_background_loop():
    """Continuous autonomous background worker that polls the central agent bot Gmail inbox with backoff."""
    backoff = 10
    while True:
        try:
            bot_pwd = (AGENT_EMAIL_CONFIG.get("bot_app_password") or os.getenv("AGENT_BOT_APP_PASSWORD", "")).strip()
            bot_email = (AGENT_EMAIL_CONFIG.get("bot_base_email") or os.getenv("AGENT_BOT_EMAIL", "")).strip()
            if bot_pwd and bot_email:
                await asyncio.to_thread(poll_and_process_bot_inbox)
                backoff = 10
            else:
                backoff = 30
        except Exception:
            backoff = min(backoff * 2, 120)
        await asyncio.sleep(backoff)


@app.on_event("startup")
async def startup_event():
    """Ensures uploads and watch_folder exist, starts DB persistence and background bot poller."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "watch_folder").mkdir(parents=True, exist_ok=True)
    start_persistence()
    asyncio.create_task(_bot_poller_background_loop())


@app.on_event("shutdown")
def shutdown_event():
    """Flushes persistence changes and shuts down background workers."""
    stop_persistence()



# ---------------------------------------------------------------------------
# API Request Models
# ---------------------------------------------------------------------------
class POLineItemInput(BaseModel):
    item_code: Optional[str] = ""
    description: str
    qty: float
    unit_price: float
    amount: Optional[float] = None
    tax_rate: Optional[float] = 0.0


class PurchaseOrderInput(BaseModel):
    po_number: str
    vendor_id: str
    currency: str = "INR"
    po_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = 0.0
    total_amount: Optional[float] = None
    approver: Optional[str] = "AP Lead"
    lines: Optional[List[POLineItemInput]] = []


class VendorInput(BaseModel):
    vendor_id: str
    legal_name: str
    aliases: Optional[str] = ""
    country: str = "IN"
    tax_id: Optional[str] = ""
    default_currency: str = "INR"
    bank_account: Optional[str] = ""
    bank_code: Optional[str] = ""
    status: str = "ACTIVE"
    payment_terms: str = "NET30"


class VendorMasterUpdate(BaseModel):
    legal_name: Optional[str] = None
    aliases: Optional[str] = None
    country: Optional[str] = None
    tax_id: Optional[str] = None
    default_currency: Optional[str] = None
    bank_account: Optional[str] = None
    bank_code: Optional[str] = None
    status: Optional[str] = None
    payment_terms: Optional[str] = None


class VendorPolicyUpdate(BaseModel):
    trust: Optional[str] = None
    auto_approve_limit: Optional[float] = None
    price_tolerance_pct: Optional[float] = None
    total_tolerance_pct: Optional[float] = None
    allow_without_po: Optional[bool] = None
    notes: Optional[str] = None


class SettingsUpdate(BaseModel):
    default_price_tolerance_pct: Optional[float] = None
    default_total_tolerance_pct: Optional[float] = None
    default_auto_approve_limit_inr: Optional[float] = None
    duplicate_window_days: Optional[int] = None
    require_po_above_inr: Optional[float] = None
    ai_review_enabled: Optional[bool] = None
    ai_min_confidence: Optional[float] = None


class HumanApprovalRequest(BaseModel):
    reviewer: str = "AP Lead"
    action: str = "APPROVE"  # "APPROVE", "REJECT", "APPROVE_AND_PREAPPROVE"
    comment: Optional[str] = None
    preapprove_vendor: Optional[bool] = False


class OverrideRequest(BaseModel):
    decision: Literal["AUTO_APPROVE", "REJECT"]
    comment: str = ""
    reviewer: str = "AP Lead"
    preapprove_vendor: Optional[bool] = False



class GmailConnectRequest(BaseModel):
    mode: Literal["SIMULATED", "IMAP", "OAUTH"] = "SIMULATED"
    email: Optional[str] = "ap-invoices@acmemfg.in"
    app_password: Optional[str] = None
    oauth_token: Optional[str] = None
    imap_host: Optional[str] = None


class ExtensionInstallRequest(BaseModel):
    email: Optional[str] = None
    app_password: Optional[str] = None
    oauth_token: Optional[str] = None
    imap_host: Optional[str] = None
    use_sandbox: Optional[bool] = False


class ExtensionPushRequest(BaseModel):
    sender: str
    subject: str
    date: Optional[str] = None
    body: Optional[str] = ""
    thread_history: Optional[List[Dict[str, Any]]] = None
    attachment_name: Optional[str] = None
    attachment_base64: Optional[str] = None
    quotation_name: Optional[str] = None
    quotation_base64: Optional[str] = None


class GmailPullRequest(BaseModel):
    message_ids: List[str]


class AIConfigRequest(BaseModel):
    provider: str = "GEMINI"
    api_key: str


class PullAllRequest(BaseModel):
    platform: Optional[str] = None


class QuotationInput(BaseModel):
    quotation_number: str
    vendor_name: str
    vendor_country: Optional[str] = "IN"
    vendor_tax_id: Optional[str] = ""
    currency: Optional[str] = "INR"
    validity_period: Optional[str] = "NET30"
    quotation_date: Optional[str] = None
    subtotal: Optional[float] = 0.0
    tax_amount: Optional[float] = 0.0
    total_amount: Optional[float] = 0.0
    notes: Optional[str] = None
    lines: Optional[List[POLineItemInput]] = []


class SendToAgentRequest(BaseModel):
    message_id: str


# ---------------------------------------------------------------------------
# Endpoints: Authentication & User Management
# ---------------------------------------------------------------------------
@app.post("/api/auth/login", response_model=AuthResponse)
def login_endpoint(req: LoginRequest):
    """Logs in an existing user or pre-configured admin."""
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_session(user)
    return AuthResponse(
        token=token,
        user=UserPublic(
            id=user["id"],
            username=user["username"],
            name=user.get("name", user["username"]),
            role=user.get("role", "user"),
            email=user.get("email"),
            created_at=user.get("created_at", "")
        ),
        message="Login successful"
    )


@app.post("/api/auth/signup", response_model=AuthResponse)
def signup_endpoint(req: SignupRequest):
    """Registers a new user account."""
    try:
        new_user = register_user(
            username=req.username,
            password=req.password,
            name=req.name,
            email=req.email
        )
        token = create_session(new_user)
        return AuthResponse(
            token=token,
            user=UserPublic(
                id=new_user["id"],
                username=new_user["username"],
                name=new_user.get("name", new_user["username"]),
                role=new_user.get("role", "user"),
                email=new_user.get("email"),
                created_at=new_user.get("created_at", "")
            ),
            message="Account created successfully"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create user account")


@app.get("/api/auth/me")
def get_current_user_endpoint(authorization: Optional[str] = Header(None)):
    """Retrieves authenticated session user."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_session_user(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")
    return {"user": user}


@app.post("/api/auth/logout")
def logout_endpoint(authorization: Optional[str] = Header(None)):
    """Logs out and terminates active session."""
    if authorization:
        delete_session(authorization)
    return {"status": "ok", "message": "Logged out successfully"}


# ---------------------------------------------------------------------------
# Endpoints: System Health & Dashboard Overview
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Endpoints: Real Purchase Orders & Quotations Management
# ---------------------------------------------------------------------------
@app.get("/api/purchase-orders")
def get_all_purchase_orders():
    """Returns all real purchase orders with lines."""
    pos = load_purchase_orders()
    lines = load_po_lines()
    lines_by_po: Dict[str, List[Dict[str, Any]]] = {}
    for ln in lines:
        lines_by_po.setdefault(ln["po_number"], []).append(ln)

    vendors = {v["vendor_id"]: v["legal_name"] for v in load_vendors()}
    for po in pos:
        po["lines"] = lines_by_po.get(po["po_number"], [])
        po["vendor_name"] = vendors.get(po["vendor_id"], po["vendor_id"])

    return {"purchase_orders": pos}


@app.post("/api/purchase-orders")
def create_purchase_order(po: PurchaseOrderInput):
    """Creates and saves a real purchase order / quotation to purchase_orders.csv and po_lines.csv."""
    import csv
    from datetime import date

    pos = load_purchase_orders()
    po_num = po.po_number.strip().upper()
    if any(p["po_number"].upper() == po_num for p in pos):
        raise HTTPException(status_code=400, detail=f"Purchase Order '{po_num}' already exists")

    calc_subtotal = 0.0
    for idx, ln in enumerate(po.lines or []):
        line_amt = ln.amount if (ln.amount is not None and ln.amount > 0) else round(ln.qty * ln.unit_price, 2)
        calc_subtotal += line_amt

    subtotal = po.subtotal if (po.subtotal is not None and po.subtotal > 0) else calc_subtotal
    tax = po.tax_amount or 0.0
    total = po.total_amount if (po.total_amount is not None and po.total_amount > 0) else round(subtotal + tax, 2)
    po_date = po.po_date or date.today().isoformat()

    new_po = {
        "po_number": po_num,
        "vendor_id": po.vendor_id.strip(),
        "currency": po.currency.strip().upper(),
        "po_date": po_date,
        "subtotal": subtotal,
        "tax_amount": tax,
        "total_amount": total,
        "invoiced_amount": 0.0,
        "remaining_amount": total,
        "status": "OPEN",
        "approver": po.approver or "AP Lead",
    }

    pos_file = DATA_DIR / "purchase_orders.csv"
    pos_file.parent.mkdir(parents=True, exist_ok=True)
    file_exists = pos_file.exists() and pos_file.stat().st_size > 0
    with open(pos_file, "a", encoding="utf-8", newline="") as f:
        fieldnames = ["po_number", "vendor_id", "currency", "po_date", "subtotal", "tax_amount", "total_amount", "invoiced_amount", "remaining_amount", "status", "approver"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(new_po)

    if po.lines:
        lines_file = DATA_DIR / "po_lines.csv"
        lines_exist = lines_file.exists() and lines_file.stat().st_size > 0
        with open(lines_file, "a", encoding="utf-8", newline="") as f:
            ln_fields = ["po_number", "line_no", "item_code", "description", "qty", "unit_price", "amount", "tax_rate"]
            ln_writer = csv.DictWriter(f, fieldnames=ln_fields)
            if not lines_exist:
                ln_writer.writeheader()
            for idx, ln in enumerate(po.lines):
                line_amt = ln.amount if (ln.amount is not None and ln.amount > 0) else round(ln.qty * ln.unit_price, 2)
                ln_writer.writerow({
                    "po_number": po_num,
                    "line_no": idx + 1,
                    "item_code": (ln.item_code or f"ITEM-{idx+1}").strip(),
                    "description": ln.description.strip(),
                    "qty": ln.qty,
                    "unit_price": ln.unit_price,
                    "amount": line_amt,
                    "tax_rate": ln.tax_rate or 0.0,
                })

    return {"status": "ok", "purchase_order": new_po}


@app.delete("/api/purchase-orders/{po_number}")
def delete_purchase_order(po_number: str):
    """Deletes a purchase order and its lines."""
    import csv
    po_clean = po_number.strip().upper()
    pos = [p for p in load_purchase_orders() if p["po_number"].upper() != po_clean]
    pos_file = DATA_DIR / "purchase_orders.csv"
    fieldnames = ["po_number", "vendor_id", "currency", "po_date", "subtotal", "tax_amount", "total_amount", "invoiced_amount", "remaining_amount", "status", "approver"]
    with open(pos_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in pos:
            writer.writerow(p)

    lines = [ln for ln in load_po_lines() if ln["po_number"].upper() != po_clean]
    lines_file = DATA_DIR / "po_lines.csv"
    ln_fields = ["po_number", "line_no", "item_code", "description", "qty", "unit_price", "amount", "tax_rate"]
    with open(lines_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=ln_fields)
        writer.writeheader()
        for ln in lines:
            writer.writerow(ln)

    return {"status": "ok", "deleted": po_clean}


# ---------------------------------------------------------------------------
# Endpoints: Advance Quotations Management (Store Quotations Before Invoices Arrive)
# ---------------------------------------------------------------------------
@app.get("/api/quotations")
def get_all_quotations():
    """Returns all pre-stored advance quotations and bills."""
    return {"quotations": load_quotations()}


@app.post("/api/quotations/upload")
async def upload_quotation_endpoint(file: UploadFile = File(...)):
    """
    Standalone Quotation Intake:
    Uploads an Expected Quotation / Bill BEFORE an invoice arrives.
    Extracts Quotation Number, Vendor Name, Country, GSTIN/Tax ID,
    Validity Period, Item Lines, Subtotal, Tax Amount, and Grand Total via AI.
    Saves to persistent quotations.json store.
    """
    safe_name = _sanitize_filename(file.filename)
    save_path = UPLOADS_DIR / f"quotation_{uuid.uuid4().hex[:6]}_{safe_name}"
    await _save_upload_file(file, save_path)

    std_inv = extract_standard_invoice(str(save_path), source_type="UPLOAD")
    q_num = str(std_inv.invoice_number.value or std_inv.po_reference.value or Path(file.filename).stem).strip()
    if not q_num.upper().startswith("QTE") and not q_num.upper().startswith("QUO"):
        q_num = f"QTE-{q_num}"

    v_tax = str(std_inv.vendor_tax_id.value or "").strip() or None
    v_name = str(std_inv.vendor_name.value or "Vendor Legal Entity").strip()
    v_country = str(std_inv.vendor_country.value or "IN").strip()
    curr = str(std_inv.currency.value or "INR").upper()
    subtotal = float(std_inv.subtotal.value or 0.0)
    tax_amt = float(std_inv.tax_amount.value or 0.0)
    total_amt = float(std_inv.total.value or 0.0)
    items = std_inv.line_items or []

    validity = compute_document_duration(
        str(std_inv.invoice_date.value or "") if std_inv.invoice_date else None,
        str(std_inv.due_date.value or "") if std_inv.due_date else None,
    )
    if validity == "NET30":
        validity = "30 Days Validity"

    ai_sum, ai_flws, _ = generate_document_summary_and_flaws(std_inv, doc_type="QUOTATION")

    quote_record = {
        "quotation_id": f"qte-{uuid.uuid4().hex[:6]}",
        "quotation_number": q_num,
        "vendor_name": v_name,
        "vendor_country": v_country,
        "vendor_tax_id": v_tax,
        "currency": curr,
        "validity_period": validity,
        "quotation_date": str(std_inv.invoice_date.value or "") or None,
        "subtotal": subtotal,
        "tax_amount": tax_amt,
        "total_amount": total_amt,
        "items_count": len(items),
        "total_qty": sum(float(l.qty) for l in items) if items else 1.0,
        "line_items": [l.dict() for l in items],
        "filename": file.filename,
        "file_path": str(save_path),
        "status": "PENDING_INVOICE",
        "matched_run_ids": [],
        "matched_invoice_numbers": [],
        "notes": f"Standalone quotation uploaded in advance. Extracted {len(items)} line item(s).",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ai_summary": ai_sum,
        "ai_flaws": ai_flws,
    }

    saved = create_or_update_quotation(quote_record)
    matched_runs = [get_run(rid) for rid in saved.get("matched_run_ids", []) if get_run(rid)]
    return {
        "status": "ok",
        "quotation": saved,
        "matched_runs": matched_runs,
        "reconciled_count": len(matched_runs),
    }


@app.post("/api/quotations")
def create_quotation_manual(req: QuotationInput):
    """Manually registers an advance quotation without file upload."""
    calc_subtotal = 0.0
    lines_data = []
    for idx, ln in enumerate(req.lines or []):
        amt = ln.amount if (ln.amount is not None and ln.amount > 0) else round(ln.qty * ln.unit_price, 2)
        calc_subtotal += amt
        lines_data.append({
            "line_no": idx + 1,
            "item_code": ln.item_code or f"ITEM-{idx+1:02d}",
            "description": ln.description,
            "qty": ln.qty,
            "unit_price": ln.unit_price,
            "amount": amt,
            "tax_rate": ln.tax_rate or 0.0,
        })

    subtotal = req.subtotal if (req.subtotal is not None and req.subtotal > 0) else calc_subtotal
    tax = req.tax_amount or 0.0
    total = req.total_amount if (req.total_amount is not None and req.total_amount > 0) else round(subtotal + tax, 2)

    temp_inv = StandardInvoice(
        document_type="QUOTATION",
        source_info=SourceInfo(filename="manual_quotation", file_hash="manual"),
        vendor_name=ExtractedField(value=req.vendor_name),
        vendor_tax_id=ExtractedField(value=req.vendor_tax_id),
        vendor_country=ExtractedField(value=req.vendor_country or "IN"),
        vendor_bank_account=ExtractedField(value=None),
        vendor_bank_code=ExtractedField(value=None),
        invoice_number=ExtractedField(value=req.quotation_number),
        invoice_date=ExtractedField(value=req.quotation_date),
        due_date=ExtractedField(value=None),
        po_reference=ExtractedField(value=None),
        currency=ExtractedField(value=req.currency or "INR"),
        subtotal=ExtractedField(value=subtotal),
        tax_amount=ExtractedField(value=tax),
        total=ExtractedField(value=total),
        line_items=[StandardLineItem(**l) for l in lines_data],
    )
    ai_sum, ai_flws, _ = generate_document_summary_and_flaws(temp_inv, doc_type="QUOTATION")

    quote_record = {
        "quotation_id": f"qte-{uuid.uuid4().hex[:6]}",
        "quotation_number": req.quotation_number.strip().upper(),
        "vendor_name": req.vendor_name.strip(),
        "vendor_country": (req.vendor_country or "IN").strip().upper(),
        "vendor_tax_id": (req.vendor_tax_id or "").strip() or None,
        "currency": (req.currency or "INR").strip().upper(),
        "validity_period": req.validity_period or "NET30",
        "quotation_date": req.quotation_date or datetime.now().strftime("%Y-%m-%d"),
        "subtotal": subtotal,
        "tax_amount": tax,
        "total_amount": total,
        "items_count": len(lines_data),
        "total_qty": sum(l["qty"] for l in lines_data) if lines_data else 1.0,
        "line_items": lines_data,
        "filename": None,
        "file_path": None,
        "status": "PENDING_INVOICE",
        "matched_run_ids": [],
        "matched_invoice_numbers": [],
        "notes": req.notes or "Manually registered quotation.",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "ai_summary": ai_sum,
        "ai_flaws": ai_flws,
    }

    saved = create_or_update_quotation(quote_record)
    matched_runs = [get_run(rid) for rid in saved.get("matched_run_ids", []) if get_run(rid)]
    return {
        "status": "ok",
        "quotation": saved,
        "matched_runs": matched_runs,
        "reconciled_count": len(matched_runs),
    }


@app.delete("/api/quotations/{quotation_id}")
def delete_quotation_endpoint(quotation_id: str):
    """Deletes an advance quotation."""
    deleted = delete_quotation(quotation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Quotation '{quotation_id}' not found")
    return {"status": "ok", "deleted": quotation_id}


@app.post("/api/runs/{run_id}/link-quotation/{quotation_id}")
def link_quotation_endpoint(run_id: str, quotation_id: str):
    """Links an existing pre-registered quotation to an invoice run."""
    updated = link_quotation_to_run(run_id, quotation_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Run or Quotation not found")
    return {"status": "ok", "run": updated}


# ---------------------------------------------------------------------------
# Endpoints: Real Vendor Master & Policy Management
# ---------------------------------------------------------------------------
@app.get("/api/vendors")
def get_all_vendors():
    """Returns all registered vendors merged with policy and AP statistics."""
    vendors = load_vendors()
    merged_vendors = []
    for v in vendors:
        v_id = v.get("vendor_id", "").strip().upper()
        pol = get_vendor_policy(v_id)
        stats = get_vendor_stats(v_id)
        rec = dict(v)
        rec["policy"] = pol
        rec["trust"] = pol.get("trust", "STANDARD")
        rec["auto_approve_limit"] = pol.get("auto_approve_limit")
        rec["price_tolerance_pct"] = pol.get("price_tolerance_pct")
        rec["total_tolerance_pct"] = pol.get("total_tolerance_pct")
        rec["allow_without_po"] = pol.get("allow_without_po", False)
        rec["policy_notes"] = pol.get("notes", "")
        rec.update(stats)
        merged_vendors.append(rec)
    return {"vendors": merged_vendors}


@app.post("/api/vendors")
def create_vendor(vendor: VendorInput):
    """Registers and saves a new vendor in vendors.csv with default policy."""
    v_id = vendor.vendor_id.strip().upper()
    vendors = load_vendors()
    if any(v.get("vendor_id", "").upper() == v_id for v in vendors):
        raise HTTPException(status_code=400, detail=f"Vendor ID '{v_id}' already exists")

    saved = save_vendor_record(vendor.dict())
    pol = get_vendor_policy(v_id)
    stats = get_vendor_stats(v_id)
    rec = dict(saved)
    rec["policy"] = pol
    rec["trust"] = pol.get("trust", "STANDARD")
    rec["auto_approve_limit"] = pol.get("auto_approve_limit")
    rec["allow_without_po"] = pol.get("allow_without_po", False)
    rec["policy_notes"] = pol.get("notes", "")
    rec.update(stats)
    return {"status": "ok", "vendor": rec}


@app.put("/api/vendors/{vendor_id}")
def update_vendor_endpoint(vendor_id: str, updates: VendorMasterUpdate):
    """Edits master vendor attributes (name, aliases, tax_id, bank, terms, etc.)."""
    v_id = vendor_id.strip().upper()
    update_data = {k: v for k, v in updates.dict().items() if v is not None}
    updated = update_vendor_record(v_id, update_data)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    pol = get_vendor_policy(v_id)
    stats = get_vendor_stats(v_id)
    rec = dict(updated)
    rec["policy"] = pol
    rec["trust"] = pol.get("trust", "STANDARD")
    rec["auto_approve_limit"] = pol.get("auto_approve_limit")
    rec["allow_without_po"] = pol.get("allow_without_po", False)
    rec["policy_notes"] = pol.get("notes", "")
    rec.update(stats)
    return {"status": "ok", "vendor": rec}


@app.put("/api/vendors/{vendor_id}/policy")
def update_vendor_policy_endpoint(vendor_id: str, policy_update: VendorPolicyUpdate):
    """Updates policy settings (trust tier, limits, tolerances, allow_without_po) for a vendor."""
    v_id = vendor_id.strip().upper()
    vendors = load_vendors()
    if not any(v.get("vendor_id", "").upper() == v_id for v in vendors):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    update_data = {k: v for k, v in policy_update.dict().items() if v is not None}
    saved_pol = save_vendor_policy(v_id, update_data)
    return {"status": "ok", "vendor_id": v_id, "policy": saved_pol}


@app.post("/api/vendors/{vendor_id}/preapprove")
def preapprove_vendor_endpoint(vendor_id: str):
    """Convenience endpoint: sets vendor trust to PREAPPROVED."""
    v_id = vendor_id.strip().upper()
    vendors = load_vendors()
    if not any(v.get("vendor_id", "").upper() == v_id for v in vendors):
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")

    saved_pol = save_vendor_policy(v_id, {"trust": "PREAPPROVED"})
    return {"status": "ok", "vendor_id": v_id, "policy": saved_pol}


@app.delete("/api/vendors/{vendor_id}")
def delete_vendor_endpoint(vendor_id: str):
    """Soft delete: sets vendor status to INACTIVE."""
    v_id = vendor_id.strip().upper()
    ok = soft_delete_vendor(v_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Vendor '{vendor_id}' not found")
    return {"status": "ok", "vendor_id": v_id, "status": "INACTIVE"}


# ---------------------------------------------------------------------------
# Endpoints: Global Settings & AI Status
# ---------------------------------------------------------------------------
@app.get("/api/settings")
def get_global_settings_endpoint():
    """Returns global AP configuration settings."""
    return {"settings": load_settings()}


@app.put("/api/settings")
def update_global_settings_endpoint(settings_update: SettingsUpdate):
    """Updates global AP settings (tolerances, limits, AI review toggle)."""
    update_data = {k: v for k, v in settings_update.dict().items() if v is not None}
    saved = save_settings(update_data)
    return {"status": "ok", "settings": saved}


@app.get("/api/ai/status")
def get_ai_status_public():
    """Returns public AI review status without provider names."""
    return get_ai_status()



@app.get("/api/health")
def get_health():
    """Health check endpoint reporting timestamp and persistence mode."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "persistence": get_persistence_mode(),
    }


@app.get("/api/dashboard")
def get_dashboard_endpoint():
    """Returns aggregated executive AP dashboard analytics."""
    return get_dashboard_metrics()



@app.get("/api/overview")
def get_overview():
    """
    Returns dashboard KPIs, runs list, POs, vendors, FX rates,
    sample scenarios catalog, connected sources, and AI config.
    Supports BOTH key conventions so Frontend never encounters undefined properties.
    """
    runs = get_all_runs()
    pos = load_purchase_orders()
    vendors = load_vendors()
    fx_rates = load_fx_rates()
    all_po_lines = load_po_lines()

    # Calculate KPIs
    total_invoices = len(runs)
    auto_approved = sum(1 for r in runs if r.decision == "AUTO_APPROVE")
    needs_review = sum(1 for r in runs if r.decision == "NEEDS_REVIEW")
    on_hold = sum(1 for r in runs if r.decision == "ON_HOLD")
    rejected = sum(1 for r in runs if r.decision == "REJECT")
    total_spend_inr = round(sum(r.base_total_inr for r in runs if r.decision == "AUTO_APPROVE"), 2)
    spend_protected_inr = round(sum(r.base_total_inr for r in runs if r.decision == "REJECT"), 2)
    auto_approve_pct = round((auto_approved / total_invoices) * 100, 1) if total_invoices > 0 else 0.0

    kpis_payload = {
        "total_runs": total_invoices,
        "total_invoices": total_invoices,
        "auto_approve_count": auto_approved,
        "auto_approved": auto_approved,
        "auto_approve_pct": auto_approve_pct,
        "auto_approval_rate": auto_approve_pct,
        "needs_review_count": needs_review,
        "needs_review": needs_review,
        "on_hold_count": on_hold,
        "on_hold": on_hold,
        "reject_count": rejected,
        "rejected": rejected,
        "fraud_and_duplicates_blocked_inr": spend_protected_inr,
        "spend_protected_inr": spend_protected_inr,
        "total_amount_processed_inr": total_spend_inr,
        "total_spend_inr": total_spend_inr,
    }

    # Enrich POs with vendor_name and line items
    enriched_pos = []
    for po in pos:
        po_copy = dict(po)
        matching_vendor = next((v for v in vendors if v["vendor_id"] == po["vendor_id"]), None)
        po_copy["vendor_name"] = matching_vendor["legal_name"] if matching_vendor else po["vendor_id"]
        po_copy["lines"] = [l for l in all_po_lines if l["po_number"] == po["po_number"]]
        enriched_pos.append(po_copy)

    # Enrich sample scenarios
    scenario_po_map = {
        "01": ("PO-2026-1041", "₹2,36,000.00"),
        "02": ("PO-2026-1042", "₹60,000.00"),
        "03": ("PO-2026-1042", "₹40,000.00"),
        "04": ("PO-2026-1042", "₹15,000.00"),
        "05": ("PO-2026-1041", "₹2,36,000.00"),
        "06": ("PO-2026-1045", "€7,021.00"),
        "07": ("PO-2026-1043", "$12,000.00"),
        "08": ("PO-2026-1045", "$7,650.00 USD"),
        "09": ("PO-2026-1047", "S$8,950.00"),
        "10": ("PO-2026-1041", "₹64,000.00"),
        "11": ("PO-2026-1041", "₹2,36,450.00"),
    }
    enriched_scenarios = []
    for item in SCENARIOS_CATALOG:
        item_copy = dict(item)
        po_no, amt_fmt = scenario_po_map.get(item["id"], ("N/A", "N/A"))
        item_copy["vendor_name"] = item.get("vendor", "")
        item_copy["po_number"] = po_no
        item_copy["amount_formatted"] = amt_fmt
        enriched_scenarios.append(item_copy)

    unread_gmail = sum(1 for m in list_gmail_messages("GMAIL") if m.get("status") == "UNREAD")

    return {
        "kpis": kpis_payload,
        "recent_runs": runs[:10],
        "runs": runs,
        "quotations": load_quotations(),
        "pos": enriched_pos,
        "purchase_orders": enriched_pos,
        "vendors": vendors,
        "fx_rates": fx_rates,
        "sample_scenarios": enriched_scenarios,
        "gmail_status": {
            "connected": GMAIL_CONFIG["connected"],
            "email": GMAIL_CONFIG["email"],
            "mode": GMAIL_CONFIG["mode"],
            "extension_installed": GMAIL_CONFIG.get("extension_installed", False),
            "extension_version": GMAIL_CONFIG.get("extension_version", "2.4.0-direct"),
            "unread_count": unread_gmail,
        },
        "platforms": get_all_platforms(),
        "sources": {
            "gmail": get_gmail_status(),
        },
        "ai_config": get_ai_config(),
    }


# ---------------------------------------------------------------------------
# Endpoints: Invoice Runs & Execution
# ---------------------------------------------------------------------------
@app.get("/api/runs")
def list_runs() -> List[InvoiceRunResult]:
    """Returns all invoice run results, newest first."""
    return get_all_runs()


@app.get("/api/runs/{run_id}")
def get_single_run(run_id: str) -> InvoiceRunResult:
    """Returns a single invoice run by run_id."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.put("/api/runs/{run_id}")
def update_run_endpoint(run_id: str, payload: Dict[str, Any]):
    """Modifies invoice run details (vendor, amounts, line items, decision, etc.)."""
    updated_run = update_run_details(run_id, payload)
    if not updated_run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"status": "ok", "run": updated_run}


@app.delete("/api/runs/{run_id}")
def delete_run_endpoint(run_id: str):
    """Deletes an invoice run by run_id."""
    remove_gmail_message_for_run(run_id)
    success = delete_run(run_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"status": "ok", "deleted_run_id": run_id}


@app.post("/api/runs/upload")
async def upload_invoices(
    files: List[UploadFile] = File(...),
    quotation_file: Optional[UploadFile] = File(None),
    quotation_id: Optional[str] = Form(None),
    source_type: str = Form("UPLOAD"),
):
    """
    Accepts invoice files and optional Expected Invoice / Quotation file (or quotation_id),
    runs extraction, and returns the results with side-by-side quotation comparison.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files uploaded ({len(files)}). Maximum allowed is {MAX_UPLOAD_FILES} files.")

    results: List[InvoiceRunResult] = []
    quotation_path = None
    if quotation_file and quotation_file.filename:
        q_safe = _sanitize_filename(quotation_file.filename)
        quotation_path = UPLOADS_DIR / f"quotation_{uuid.uuid4().hex[:6]}_{q_safe}"
        await _save_upload_file(quotation_file, quotation_path)

    for file in files:
        f_safe = _sanitize_filename(file.filename)
        file_path = UPLOADS_DIR / f_safe
        await _save_upload_file(file, file_path)

        run = process_invoice_file(
            filepath=str(file_path),
            source_type=source_type,
            scenario_tag="user_upload",
            quotation_filepath=str(quotation_path) if quotation_path else None,
            quotation_id=quotation_id if quotation_id else None,
        )
        results.append(run)

    return {"runs": results}


@app.post("/api/runs/upload-stream")
async def upload_invoices_stream(
    files: List[UploadFile] = File(...),
    quotation_file: Optional[UploadFile] = File(None),
    quotation_id: Optional[str] = Form(None),
    source_type: str = Form("UPLOAD"),
):
    """
    Accepts invoice files and streams real-time stage progress and results via Server-Sent Events (SSE).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files uploaded ({len(files)}). Maximum allowed is {MAX_UPLOAD_FILES} files.")

    import queue
    import threading

    saved_files: List[Tuple[str, str]] = []
    for file in files:
        f_safe = _sanitize_filename(file.filename)
        file_path = UPLOADS_DIR / f_safe
        await _save_upload_file(file, file_path)
        saved_files.append((f_safe, str(file_path)))

    saved_quotation_path = None
    if quotation_file and quotation_file.filename:
        q_safe = _sanitize_filename(quotation_file.filename)
        q_path = UPLOADS_DIR / f"quotation_{uuid.uuid4().hex[:6]}_{q_safe}"
        await _save_upload_file(quotation_file, q_path)
        saved_quotation_path = str(q_path)

    event_queue: queue.Queue = queue.Queue()

    def worker_target():
        total_count = len(saved_files)
        for i, (f_name, f_path) in enumerate(saved_files):
            event_queue.put({
                "type": "file_start",
                "file": f_name,
                "index": i,
                "total": total_count,
            })
            time.sleep(0.05)

            def stage_listener(st_data):
                event_queue.put({
                    "type": "stage",
                    "file": f_name,
                    "stage": {
                        "key": st_data.get("key"),
                        "name": st_data.get("name"),
                        "status": st_data.get("status"),
                        "summary": st_data.get("summary"),
                        "duration_ms": st_data.get("duration_ms"),
                    },
                })
                time.sleep(0.25)  # Pacing ~250ms between stage events

            try:
                run_res = process_invoice_file(
                    filepath=f_path,
                    source_type=source_type,
                    scenario_tag="user_upload",
                    quotation_filepath=saved_quotation_path,
                    quotation_id=quotation_id if quotation_id else None,
                    on_stage=stage_listener,
                )
                run_dict = run_res.model_dump() if hasattr(run_res, "model_dump") else run_res.dict()
                event_queue.put({
                    "type": "run_complete",
                    "file": f_name,
                    "run": run_dict,
                })
            except Exception as exc:
                event_queue.put({
                    "type": "error",
                    "file": f_name,
                    "message": str(exc),
                })
        event_queue.put({"type": "done"})

    thread = threading.Thread(target=worker_target, daemon=True, name="upload-stream-worker")
    thread.start()

    def sse_generator():
        while True:
            try:
                item = event_queue.get(timeout=60)
                yield f"data: {json.dumps(item, default=str)}\n\n"
                if item.get("type") == "done":
                    break
            except queue.Empty:
                yield "data: {\"type\": \"ping\"}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )



@app.post("/api/runs/{run_id}/quotation")
async def attach_quotation_endpoint(run_id: str, file: UploadFile = File(...)):
    """
    Uploads and attaches an Expected Invoice or Quotation document to an existing run,
    running dual AI extraction and updating quotation matching and human approval status.
    """
    safe_name = _sanitize_filename(file.filename)
    safe_run_id = _sanitize_filename(run_id)
    file_path = UPLOADS_DIR / f"quotation_{safe_run_id}_{safe_name}"
    await _save_upload_file(file, file_path)

    updated_run = attach_quotation_to_run(run_id, str(file_path))
    if not updated_run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"status": "ok", "run": updated_run}


@app.post("/api/runs/{run_id}/approve")
def approve_or_reject_run_endpoint(run_id: str, req: HumanApprovalRequest):
    """
    Mandatory Human Last-Point Sign-Off: Records human approval or rejection of an invoice.
    Supports preapprove_vendor convenience flag.
    """
    updated_run = record_human_approval(
        run_id=run_id,
        reviewer=req.reviewer,
        action=req.action,
        comment=req.comment,
        preapprove_vendor=bool(getattr(req, "preapprove_vendor", False)),
    )
    if not updated_run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"status": "ok", "run": updated_run}



@app.post("/api/runs/sample/{sample_id}")
def run_sample_scenario(sample_id: str):
    """
    Executes one of the 11 built-in scenarios (or 'batch_demo' to run all 11 deterministically).
    Supports both native formats and PDF fallbacks seamlessly.
    """
    if sample_id.lower() == "batch_demo":
        # Reset state first so PO balances start clean and duplicate detection works deterministically
        reset_engine_state()
        all_ids = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11"]
        runs: List[InvoiceRunResult] = []
        for sid in all_ids:
            r = _execute_sample_by_id(sid)
            if r:
                runs.append(r)
        return {"runs": runs}

    run = _execute_sample_by_id(sample_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Sample scenario '{sample_id}' could not be executed.")
    return {"runs": [run]}


def _execute_sample_by_id(sample_id: str) -> Optional[InvoiceRunResult]:
    """Locates and runs a sample invoice scenario by ID or filename."""
    clean_id = sample_id.replace("scenario_", "").zfill(2) if sample_id.isdigit() else sample_id

    target_scenario = None
    for item in SCENARIOS_CATALOG:
        stem = Path(item["filename"]).stem
        if (
            item["id"] == clean_id
            or item["id"] == f"scenario_{clean_id}"
            or item["id"] == sample_id
            or item["id"].endswith(clean_id)
            or item["filename"] == sample_id
            or stem == sample_id
            or sample_id.startswith(item["id"] + "_")
        ):
            target_scenario = item
            break

    if not target_scenario:
        return None

    filename = target_scenario["filename"]
    file_path = SAMPLE_INVOICES_DIR / filename

    if not file_path.exists():
        stem = Path(filename).stem
        for alt_ext in [".pdf", ".png", ".xlsx", ".docx"]:
            alt_path = SAMPLE_INVOICES_DIR / f"{stem}{alt_ext}"
            if alt_path.exists():
                file_path = alt_path
                break

    if not file_path.exists():
        SAMPLE_INVOICES_DIR.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(b"%PDF-1.4 Mock Invoice File for " + filename.encode())

    # Match corresponding Gmail message metadata if present so provenance is preserved
    email_meta = None
    src_type = "GMAIL"
    try:
        for msg in list_gmail_messages("GMAIL"):
            if msg.get("attachment_name") == filename:
                email_meta = {
                    "from": msg.get("from", ""),
                    "subject": msg.get("subject", ""),
                    "date": msg.get("date", ""),
                    "platform": "GMAIL",
                }
                break
    except Exception:
        pass

    return process_invoice_file(
        filepath=str(file_path),
        source_type=src_type if email_meta else "SAMPLE",
        email_meta=email_meta,
        scenario_tag=target_scenario["id"],
    )


@app.post("/api/runs/{run_id}/override")
def override_decision(run_id: str, req: OverrideRequest):
    """
    Applies a human reviewer override to a run decision (and updates PO ledger if approved).
    Supports optional preapprove_vendor flag.
    """
    updated_run = override_run_decision(
        run_id=run_id,
        new_decision=req.decision,
        comment=req.comment,
        reviewer=req.reviewer,
        preapprove_vendor=bool(getattr(req, "preapprove_vendor", False)),
    )
    if not updated_run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return updated_run



# ---------------------------------------------------------------------------
# Endpoints: Multi-Source Connectors (Gmail, Drive, Slack, WhatsApp, Outlook)
# ---------------------------------------------------------------------------
@app.get("/api/sources/gmail/messages")
def get_gmail_inbox_messages(platform: Optional[str] = Query(None)):
    """Lists messages in the connected inbox (optional platform filter or 'ALL')."""
    return list_gmail_messages(platform=platform)


@app.post("/api/sources/gmail/connect")
def connect_gmail_account(req: GmailConnectRequest):
    """Connects to Gmail via SIMULATED AP Inbox, live IMAP, or Google OAuth REST API."""
    res = connect_gmail(
        mode=req.mode,
        email_addr=req.email,
        app_password=req.app_password,
        oauth_token=req.oauth_token,
        imap_host=req.imap_host,
    )
    if res.get("status") == "error":
        raise HTTPException(status_code=400, detail=res.get("message", "Connection failed"))
    messages = list_gmail_messages("GMAIL")
    return {"connection": res, "messages": messages}


@app.post("/api/sources/gmail/pull")
def pull_from_gmail(req: GmailPullRequest):
    """Pulls selected email attachments directly into the AP pipeline across ANY platform."""
    runs = pull_gmail_messages(req.message_ids)
    return {"runs": runs}


@app.post("/api/sources/gmail/send-to-agent")
def send_gmail_invoice_to_agent_endpoint(req: SendToAgentRequest):
    """
    Interactive Email Reader Action ("Send to Site"):
    Directly sends an email's invoice attachment alongside its entire message body
    and full conversation thread history into ClearPay AP's extraction and quotation-matching pipeline.
    If already present in quotations/invoices, skips creating a duplicate.
    """
    try:
        res = send_email_to_agent(req.message_id)
        if isinstance(res, dict):
            return {"status": "ok", **res}
        return {"status": "ok", "run": res, "already_exists": False}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class AgentEmailConfigRequest(BaseModel):
    company_name: Optional[str] = None
    employee_name: Optional[str] = None
    bot_base_email: Optional[str] = None
    bot_app_password: Optional[str] = None


@app.get("/api/agent/email-id")
def get_agent_email_id_endpoint(
    company_name: Optional[str] = Query(None),
    employee_name: Optional[str] = Query(None),
    bot_base_email: Optional[str] = Query(None),
):
    """Returns the unique company and employee Agent Email IDs with real Gmail + subaddressing."""
    if company_name or employee_name or bot_base_email:
        generate_agent_email(
            company_name=company_name,
            employee_name=employee_name,
            bot_base_email=bot_base_email,
        )
    safe_cfg = {k: v for k, v in AGENT_EMAIL_CONFIG.items() if k != "bot_app_password"}
    return {"status": "ok", **safe_cfg}


@app.post("/api/agent/email-id")
def configure_agent_email_id_endpoint(req: AgentEmailConfigRequest):
    """Configures or regenerates unique company and employee Agent Email IDs, and connects IMAP if bot credentials provided."""
    imap_ok = None
    imap_msg = None

    if req.bot_app_password and req.bot_app_password.strip():
        bot_email = req.bot_base_email or AGENT_EMAIL_CONFIG.get("bot_base_email") or "ap.agent.invoice@gmail.com"
        imap_ok, imap_msg = test_bot_imap_connection(bot_email, req.bot_app_password)

    config = generate_agent_email(
        company_name=req.company_name,
        employee_name=req.employee_name,
        bot_base_email=req.bot_base_email,
        bot_app_password=req.bot_app_password if (imap_ok is not False) else None,
    )
    safe_cfg = {k: v for k, v in config.items() if k != "bot_app_password"}
    res = {"status": "ok", **safe_cfg}
    if imap_ok is not None:
        res["imap_test_ok"] = imap_ok
        res["imap_message"] = imap_msg
        if imap_ok:
            try:
                poll_and_process_bot_inbox()
            except Exception:
                pass
    return res


@app.post("/api/agent/sync-now")
def trigger_agent_sync_now():
    """Immediately triggers poll_and_process_bot_inbox() on demand."""
    new_runs = poll_and_process_bot_inbox()
    return {"status": "ok", "processed_count": len(new_runs), "runs": new_runs}


@app.post("/api/sources/gmail/inbound-email")
async def receive_inbound_email(
    from_sender: str = Form("Ramesh Patel <accounts@shreeganeshpkg.com>"),
    subject: str = Form("Tax Invoice INV-2026-0081 & Quotation QTE-2026-081"),
    body: str = Form("Please find attached our tax invoice and quotation for your review and processing."),
    attachment: Optional[UploadFile] = File(None),
    quotation_attachment: Optional[UploadFile] = File(None),
):
    """
    Direct Autonomous Inbound AP Email Ingestion:
    Receives an inbound email containing invoice and/or quotation attachments.
    AUTOMATICALLY launches the entire pipeline immediately upon receipt:
    - If quotation_attachment ONLY: extracts and persists quotation into quotations.json with Groq summary & flaws.
    - If attachment (invoice) OR email body: automatically invokes send_email_to_agent to create the invoice run
      and match against quotations immediately without requiring any manual button click!
    """
    att_name = None
    att_bytes = None
    if attachment and attachment.filename:
        att_name = _sanitize_filename(attachment.filename)
        att_bytes = await attachment.read()
        if len(att_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"Attachment '{attachment.filename}' exceeds maximum allowed size of 15MB.")

    q_name = None
    q_bytes = None
    if quotation_attachment and quotation_attachment.filename:
        q_name = _sanitize_filename(quotation_attachment.filename)
        q_bytes = await quotation_attachment.read()
        if len(q_bytes) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(status_code=413, detail=f"Quotation attachment '{quotation_attachment.filename}' exceeds maximum allowed size of 15MB.")

    msg = add_inbound_email(
        from_sender=from_sender,
        subject=subject,
        body=body,
        attachment_filename=att_name,
        attachment_bytes=att_bytes,
        quotation_filename=q_name,
        quotation_bytes=q_bytes,
    )

    # Case A: Quotation attachment ONLY (no invoice attachment)
    if (q_name and q_bytes) and not (att_name and att_bytes):
        q_path = DOWNLOADS_DIR / q_name
        std_inv = extract_standard_invoice(str(q_path), source_type="UPLOAD")
        q_num = str(std_inv.invoice_number.value or std_inv.po_reference.value or Path(q_name).stem).strip()
        if not q_num.upper().startswith("QTE") and not q_num.upper().startswith("QUO"):
            q_num = f"QTE-{q_num}"

        v_tax = str(std_inv.vendor_tax_id.value or "").strip() or None
        v_name = str(std_inv.vendor_name.value or "Vendor Legal Entity").strip()
        v_country = str(std_inv.vendor_country.value or "IN").strip()
        curr = str(std_inv.currency.value or "INR").upper()
        subtotal = float(std_inv.subtotal.value or 0.0)
        tax_amt = float(std_inv.tax_amount.value or 0.0)
        total_amt = float(std_inv.total.value or 0.0)
        items = std_inv.line_items or []

        validity = compute_document_duration(
            str(std_inv.invoice_date.value or "") if std_inv.invoice_date else None,
            str(std_inv.due_date.value or "") if std_inv.due_date else None,
        )
        if validity == "NET30":
            validity = "30 Days Validity"

        ai_sum, ai_flws, _ = generate_document_summary_and_flaws(std_inv, doc_type="QUOTATION")

        quote_record = {
            "quotation_id": f"qte-{uuid.uuid4().hex[:6]}",
            "quotation_number": q_num,
            "vendor_name": v_name,
            "vendor_country": v_country,
            "vendor_tax_id": v_tax,
            "currency": curr,
            "validity_period": validity,
            "quotation_date": str(std_inv.invoice_date.value or "") or None,
            "subtotal": subtotal,
            "tax_amount": tax_amt,
            "total_amount": total_amt,
            "items_count": len(items),
            "total_qty": sum(float(l.qty) for l in items) if items else 1.0,
            "line_items": [l.dict() for l in items],
            "filename": q_name,
            "file_path": str(q_path),
            "status": "PENDING_INVOICE",
            "matched_run_ids": [],
            "matched_invoice_numbers": [],
            "notes": f"Autonomous email intake: pre-stored quotation extracted with {len(items)} line item(s).",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "ai_summary": ai_sum,
            "ai_flaws": ai_flws,
        }
        saved_quotation = create_or_update_quotation(quote_record)
        linked_run = None
        if saved_quotation.get("matched_run_ids"):
            linked_run = get_run(saved_quotation["matched_run_ids"][0])
        msg["status"] = "PROCESSED"
        msg["processed"] = True
        if linked_run:
            msg["run_id"] = linked_run.run_id
        return {
            "status": "ok",
            "auto_processed": True,
            "type": "QUOTATION",
            "quotation": saved_quotation,
            "run": linked_run,
            "message": msg,
        }

    # Case B: Invoice attachment provided OR email body sent -> Launch full autonomous processing immediately!
    try:
        agent_res = send_email_to_agent(msg["id"])
        return {
            "status": "ok",
            "auto_processed": True,
            "type": "INVOICE",
            "message": msg,
            "run": agent_res.get("run"),
            "agent_summary": agent_res.get("agent_summary"),
        }
    except Exception as e:
        return {
            "status": "ok",
            "auto_processed": False,
            "message": msg,
            "error": str(e),
        }


@app.post("/api/sources/gmail/install-extension")
def install_browser_extension_direct_endpoint(req: Optional[ExtensionInstallRequest] = None):
    """
    Directly installs/activates the ClearPay AP Extension.
    Supports real Gmail IMAP, Google OAuth REST API, or Sandbox demo.
    """
    email_val = req.email if req else None
    app_pwd_val = req.app_password if req else None
    oauth_val = req.oauth_token if req else None
    imap_host_val = req.imap_host if req else None
    sandbox_val = req.use_sandbox if req else False

    status_info = install_extension_direct(
        email_addr=email_val,
        app_password=app_pwd_val,
        oauth_token=oauth_val,
        imap_host=imap_host_val,
        use_sandbox=sandbox_val,
    )
    if status_info.get("status") == "error":
        raise HTTPException(status_code=400, detail=status_info.get("message", "Connection failed"))

    messages = list_gmail_messages("GMAIL")
    return {
        "status": "installed",
        "extension_installed": True,
        "extension_version": status_info.get("extension_version", "2.4.0-direct"),
        "mode": GMAIL_CONFIG["mode"],
        "email": GMAIL_CONFIG["email"],
        "message": status_info.get("message", "ClearPay AP Extension connected & activated!"),
        "unread_count": sum(1 for m in messages if m.get("status") == "UNREAD"),
        "messages": messages,
    }


@app.post("/api/sources/gmail/extension-push")
def extension_push_endpoint(req: ExtensionPushRequest):
    """
    Receives an email pushed directly from the ClearPay Chrome Extension running in real mail.google.com,
    saves attachments, parses the full thread, and immediately runs send_email_to_agent.
    """
    att_bytes = None
    if req.attachment_base64:
        try:
            att_bytes = base64.b64decode(req.attachment_base64)
        except Exception:
            pass

    quote_bytes = None
    if req.quotation_base64:
        try:
            quote_bytes = base64.b64decode(req.quotation_base64)
        except Exception:
            pass

    new_msg = add_extension_push_message(
        sender=req.sender,
        subject=req.subject,
        body=req.body or "",
        date_str=req.date,
        thread_history=req.thread_history,
        attachment_name=req.attachment_name,
        attachment_bytes=att_bytes,
        quotation_name=req.quotation_name,
        quotation_bytes=quote_bytes,
    )

    # Immediately execute Agent on the email
    agent_res = send_email_to_agent(new_msg["id"])
    return {
        "status": "ok",
        "message": new_msg,
        **agent_res,
    }


@app.get("/api/sources/gmail/download-extension")
def download_extension_zip():
    """
    Zips the chrome-extension/ folder dynamically and returns it as clearpay-gmail-extension.zip.
    """
    project_root = Path(__file__).resolve().parent.parent
    ext_dir = project_root / "chrome-extension"
    if not ext_dir.exists():
        raise HTTPException(status_code=404, detail="chrome-extension directory not found")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(ext_dir):
            for file in files:
                abs_path = Path(root) / file
                rel_path = abs_path.relative_to(ext_dir)
                z.write(abs_path, str(rel_path))
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="clearpay-gmail-extension.zip"'
        },
    )


@app.get("/api/sources/gmail/extension-js")
def get_extension_js():
    """Serves content.js for 1-click bookmarklet injection into mail.google.com."""
    js_path = Path(__file__).resolve().parent.parent / "chrome-extension" / "content.js"
    if js_path.exists():
        return Response(content=js_path.read_text(encoding="utf-8"), media_type="application/javascript")
    raise HTTPException(status_code=404, detail="content.js not found")


@app.get("/api/sources/gmail/extension-css")
def get_extension_css():
    """Serves content.css for 1-click bookmarklet styling inside mail.google.com."""
    css_path = Path(__file__).resolve().parent.parent / "chrome-extension" / "content.css"
    if css_path.exists():
        return Response(content=css_path.read_text(encoding="utf-8"), media_type="text/css")
    raise HTTPException(status_code=404, detail="content.css not found")


@app.post("/api/sources/gmail/launch-chrome-extension")
def launch_chrome_extension():
    """
    Finds the exact local chrome-extension folder path and attempts to launch
    Chrome with the unpacked extension or opens Gmail for testing.
    """
    import subprocess
    project_root = Path(__file__).resolve().parent.parent
    ext_dir = project_root / "chrome-extension"
    ext_path_str = str(ext_dir.resolve())

    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]

    launched = False
    for cp in chrome_candidates:
        if os.path.exists(cp):
            try:
                subprocess.Popen([cp, f"--load-extension={ext_path_str}", "https://mail.google.com"])
                launched = True
                break
            except Exception:
                pass

    return {
        "status": "ok",
        "launched": launched,
        "extension_path": ext_path_str,
        "message": f"Chrome Extension Path: {ext_path_str}"
    }


@app.post("/api/sources/gmail/uninstall-extension")
def uninstall_browser_extension_direct_endpoint():
    """Resets the direct website extension installation state (for demo/testing popup)."""
    uninstall_extension_direct()
    return {
        "status": "uninstalled",
        "extension_installed": False,
        "message": "Direct Website Extension state reset.",
    }


@app.post("/api/sources/gmail/sync-extension")
def sync_browser_extension_endpoint():
    """
    Password-Free 1-Click Extension & Direct Connector Sync:
    Syncs the active mailbox session without exposing or storing raw email passwords.
    """
    install_extension_direct()
    messages = list_gmail_messages("GMAIL")
    return {
        "status": "connected",
        "extension_installed": True,
        "mode": "EXTENSION_DIRECT",
        "email": GMAIL_CONFIG["email"],
        "message": "ClearPay AP Direct Website Extension synced successfully. Zero raw passwords stored.",
        "unread_count": sum(1 for m in messages if m.get("status") == "UNREAD"),
        "messages": messages,
    }


@app.get("/api/sources/platforms")
def list_multi_platforms():
    """
    Returns the Multi-Platform Connector Hub: status and item queues across
    Gmail, Microsoft 365 / Outlook, Google Drive, Slack #ap-vendor-bills, WhatsApp, and Webhooks.
    """
    return {"platforms": get_all_platforms()}


@app.post("/api/sources/pull-all")
def pull_all_invoices(req: Optional[PullAllRequest] = None):
    """
    1-Click Pull across ALL or selected connected enterprise platforms.
    """
    plat = req.platform if req else None
    runs = pull_all_sources(plat)
    return {"runs": runs, "pulled_count": len(runs)}


# ---------------------------------------------------------------------------
# Endpoints: File Downloads & Visual Document Previews
# ---------------------------------------------------------------------------
def _find_file_on_disk(filename: str) -> Optional[Path]:
    """Finds file in sample invoices, uploads, or downloads directory with path-traversal safety."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return None

    clean_name = Path(filename).name
    if not clean_name or clean_name in (".", ".."):
        return None

    allowed_dirs = [
        SAMPLE_INVOICES_DIR.resolve(),
        UPLOADS_DIR.resolve(),
        (DATA_DIR / "downloads").resolve(),
    ]

    candidates = [
        SAMPLE_INVOICES_DIR / clean_name,
        UPLOADS_DIR / clean_name,
        DATA_DIR / "downloads" / clean_name,
    ]
    for p in candidates:
        try:
            resolved = p.resolve()
            if resolved.exists() and any(str(resolved).startswith(str(d)) for d in allowed_dirs):
                return resolved
        except Exception:
            pass

    stem = Path(clean_name).stem
    for alt_ext in [".pdf", ".png", ".xlsx", ".docx", ".jpg"]:
        try:
            alt_p = (SAMPLE_INVOICES_DIR / f"{stem}{alt_ext}").resolve()
            if alt_p.exists() and str(alt_p).startswith(str(SAMPLE_INVOICES_DIR.resolve())):
                return alt_p
        except Exception:
            pass

    return None


@app.get("/api/files/{filename}")
def serve_raw_file(filename: str):
    """Serves the raw original invoice document (PDF/PNG/XLSX/DOCX)."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename or path traversal detected")

    p = _find_file_on_disk(filename)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    return FileResponse(path=str(p), filename=Path(filename).name)


@app.get("/api/files/{filename}/preview-image")
def serve_preview_image(filename: str):
    """
    Renders page 1 of a PDF (or formats XLSX/DOCX/Images) as a crisp PNG
    so the Frontend can display a visual preview side-by-side with the Standardized Template.
    """
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename or path traversal detected")

    p = _find_file_on_disk(filename)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    png_bytes = render_file_preview_png(str(p))
    return Response(content=png_bytes, media_type="image/png")


# ---------------------------------------------------------------------------
# Endpoints: System Reset & Runtime Config
# ---------------------------------------------------------------------------
@app.post("/api/reset")
def reset_system():
    """
    Resets PO balances to initial amounts, clears run history, and
    resets inbox unread status for a pristine live demo.
    """
    reset_engine_state()
    reset_gmail_inbox()
    return {"status": "ok", "message": "Demo state reset successfully. Initial PO balances restored."}


@app.get("/api/config/ai")
def get_ai_configuration():
    """Returns AI configuration status."""
    return {"status": "ok", "config": get_ai_config()}


@app.post("/api/config/ai")
def configure_ai_provider(req: AIConfigRequest):
    """Configures optional Groq, Gemini or OpenAI API key at runtime."""
    set_ai_api_key(req.provider, req.api_key)
    return {"status": "ok", "config": get_ai_config()}


# Serve Frontend Production Build (Single-Port Support on http://localhost:8000)
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


# --- Serve built frontend (single-port deployment) ---
_DIST = Path(__file__).resolve().parent.parent / 'frontend' / 'dist'
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse as _FR

    app.mount('/assets', StaticFiles(directory=_DIST / 'assets'), name='assets')

    @app.get('/{full_path:path}', include_in_schema=False)
    def _spa(full_path: str):
        if full_path.startswith('api/'):
            raise HTTPException(status_code=404, detail='Not found')
        f = _DIST / full_path
        return _FR(f if full_path and f.is_file() else _DIST / 'index.html')

