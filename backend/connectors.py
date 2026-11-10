"""
ClearPay AP - Ingestion Connectors (Strictly 2 Modes: Gmail & Manual Upload).

Supports real Gmail retrieval (Live IMAP with App Password, Google OAuth REST API,
Direct In-Site Extension, and Chrome Extension Push), as well as Manual Document Upload.
"""

import os
import json
import re
import io
import uuid
import email
import email.utils
import imaplib
import urllib.request
import urllib.parse
import base64
from email.header import decode_header
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

import pymupdf as fitz

from backend.schemas import InvoiceRunResult
from backend.engine import (
    process_invoice_file,
    get_all_runs,
    get_run,
    load_quotations,
    find_matching_quotation,
    link_quotation_to_run,
    save_run,
    create_or_update_quotation,
    compute_document_duration,
)
from backend.extractor import (
    compute_sha256,
    extract_standard_invoice,
    generate_document_summary_and_flaws,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAMPLE_INVOICES_DIR = DATA_DIR / "sample_invoices"
DOWNLOADS_DIR = DATA_DIR / "downloads"
AGENT_EMAIL_CONFIG_PATH = DATA_DIR / "agent_email_config.json"
PROCESSED_IMAP_IDS_PATH = DATA_DIR / "processed_imap_ids.json"

AGENT_BOT_EMAIL_DEFAULT = os.getenv("AGENT_BOT_EMAIL", "ap.agent.invoice@gmail.com")
AGENT_BOT_APP_PASSWORD_DEFAULT = os.getenv("AGENT_BOT_APP_PASSWORD", "umdoinhxtgoqletx")


def _parse_bot_base_email(email_str: Optional[str]) -> Tuple[str, str]:
    """Extracts bot username and domain, stripping any existing +tag."""
    raw = (email_str or "").strip().lower()
    if "@" in raw:
        user_part, domain_part = raw.split("@", 1)
    else:
        user_part = raw or "ap.agent.invoice"
        domain_part = "gmail.com"
    user_part = user_part.split("+")[0].strip()
    if not user_part:
        user_part = "ap.agent.invoice"
    if not domain_part:
        domain_part = "gmail.com"
    return user_part, domain_part


def load_agent_email_config() -> Dict[str, Any]:
    """Loads persisted agent email config or defaults with deliverable Gmail + subaddressing."""
    bot_u, bot_d = _parse_bot_base_email(AGENT_BOT_EMAIL_DEFAULT)
    default_cfg = {
        "company_name": "Zamp Corp",
        "company_slug": "zampcorp",
        "employee_name": "admin_1",
        "employee_slug": "admin_1",
        "bot_base_email": f"{bot_u}@{bot_d}",
        "bot_app_password": AGENT_BOT_APP_PASSWORD_DEFAULT,
        "company_agent_email": f"{bot_u}+zampcorp@{bot_d}",
        "employee_agent_email": f"{bot_u}+zampcorp.admin_1@{bot_d}",
        "primary_agent_email": f"{bot_u}+zampcorp@{bot_d}",
        "bot_imap_connected": bool(AGENT_BOT_APP_PASSWORD_DEFAULT),
        "routing_mode": "GMAIL_PLUS_SUBADDRESSING",
    }
    if AGENT_EMAIL_CONFIG_PATH.exists():
        try:
            with open(AGENT_EMAIL_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    default_cfg.update(saved)
        except Exception:
            pass

    if AGENT_BOT_EMAIL_DEFAULT:
        default_cfg["bot_base_email"] = AGENT_BOT_EMAIL_DEFAULT
    if AGENT_BOT_APP_PASSWORD_DEFAULT:
        default_cfg["bot_app_password"] = AGENT_BOT_APP_PASSWORD_DEFAULT

    b_u, b_d = _parse_bot_base_email(default_cfg.get("bot_base_email"))
    c_s = default_cfg.get("company_slug") or "zampcorp"
    e_s = default_cfg.get("employee_slug") or "admin_1"
    default_cfg["bot_base_email"] = f"{b_u}@{b_d}"
    default_cfg["company_agent_email"] = f"{b_u}+{c_s}@{b_d}"
    default_cfg["employee_agent_email"] = f"{b_u}+{c_s}.{e_s}@{b_d}"
    default_cfg["primary_agent_email"] = default_cfg["company_agent_email"]
    default_cfg["bot_imap_connected"] = bool(default_cfg.get("bot_app_password"))
    default_cfg["routing_mode"] = "GMAIL_PLUS_SUBADDRESSING"
    return default_cfg


def save_agent_email_config(cfg: Dict[str, Any]):
    """Persists agent email config to agent_email_config.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(AGENT_EMAIL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving agent email config: {e}")


def _load_processed_imap_ids() -> set:
    """Loads set of processed IMAP message IDs."""
    if PROCESSED_IMAP_IDS_PATH.exists():
        try:
            with open(PROCESSED_IMAP_IDS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except Exception:
            pass
    return set()


def _save_processed_imap_ids(ids: set):
    """Persists set of processed IMAP message IDs."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(PROCESSED_IMAP_IDS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(list(ids)), f, indent=2)
    except Exception as e:
        print(f"Error saving processed IMAP ids: {e}")


def test_bot_imap_connection(email_addr: str, app_password: str) -> Tuple[bool, str]:
    """Tests IMAP authentication with the provided email and app password."""
    if not email_addr or not app_password:
        return False, "Email address and app password are required."
    clean_pwd = app_password.replace(" ", "").strip()
    mail = None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", port=993)
        mail.login(email_addr.strip(), clean_pwd)
        mail.logout()
        return True, "Successfully authenticated with Gmail IMAP."
    except Exception as e:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass
        return False, str(e)


# Initialize Agent Email Config with Real Deliverable Subaddressing
AGENT_EMAIL_CONFIG = load_agent_email_config()


def generate_agent_email(
    company_name: Optional[str] = None,
    employee_name: Optional[str] = None,
    bot_base_email: Optional[str] = None,
    bot_app_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates unique company and employee agent email IDs using Gmail + subaddressing."""
    if bot_base_email and bot_base_email.strip():
        AGENT_EMAIL_CONFIG["bot_base_email"] = bot_base_email.strip()
    if bot_app_password is not None:
        AGENT_EMAIL_CONFIG["bot_app_password"] = bot_app_password.replace(" ", "").strip()

    bot_user, bot_domain = _parse_bot_base_email(AGENT_EMAIL_CONFIG.get("bot_base_email"))
    AGENT_EMAIL_CONFIG["bot_base_email"] = f"{bot_user}@{bot_domain}"

    if company_name and company_name.strip():
        c_clean = re.sub(r"[^a-zA-Z0-9]", "", company_name.lower().strip())
        if c_clean:
            AGENT_EMAIL_CONFIG["company_name"] = company_name.strip()
            AGENT_EMAIL_CONFIG["company_slug"] = c_clean

    c_clean = AGENT_EMAIL_CONFIG.get("company_slug") or "company"
    AGENT_EMAIL_CONFIG["company_agent_email"] = f"{bot_user}+{c_clean}@{bot_domain}"

    if employee_name is not None and employee_name.strip():
        emp_clean = re.sub(r"[^a-zA-Z0-9_]", "_", employee_name.lower().strip()).strip("_")
        AGENT_EMAIL_CONFIG["employee_name"] = employee_name.strip()
        AGENT_EMAIL_CONFIG["employee_slug"] = emp_clean or "employee"

    emp_clean = AGENT_EMAIL_CONFIG.get("employee_slug") or "employee"
    AGENT_EMAIL_CONFIG["employee_agent_email"] = f"{bot_user}+{c_clean}.{emp_clean}@{bot_domain}"

    AGENT_EMAIL_CONFIG["primary_agent_email"] = AGENT_EMAIL_CONFIG["company_agent_email"]
    AGENT_EMAIL_CONFIG["routing_mode"] = "GMAIL_PLUS_SUBADDRESSING"
    AGENT_EMAIL_CONFIG["bot_imap_connected"] = bool(AGENT_EMAIL_CONFIG.get("bot_app_password"))

    GMAIL_CONFIG["email"] = AGENT_EMAIL_CONFIG["company_agent_email"]
    GMAIL_CONFIG["alias_email"] = AGENT_EMAIL_CONFIG["employee_agent_email"]
    GMAIL_CONFIG["agent_id"] = AGENT_EMAIL_CONFIG["company_agent_email"]

    save_agent_email_config(AGENT_EMAIL_CONFIG)
    return dict(AGENT_EMAIL_CONFIG)


# Runtime connector configurations
GMAIL_CONFIG = {
    "mode": "AGENT_ID",  # Autonomous Agent Email Ingestion Channel
    "email": AGENT_EMAIL_CONFIG["company_agent_email"],
    "alias_email": AGENT_EMAIL_CONFIG["employee_agent_email"],
    "agent_id": AGENT_EMAIL_CONFIG["company_agent_email"],
    "app_password": None,
    "oauth_token": None,
    "imap_host": "imap.gmail.com",
    "connected": True,
    "last_sync": datetime.utcnow().isoformat() + "Z",
    "extension_installed": True,
    "extension_version": "3.0.0-agent-id",
}

# State store for Gmail messages (cleared by default to avoid pre-seeded sample emails)
_GMAIL_MESSAGES_STATE: List[Dict[str, Any]] = []


def _detect_imap_host(email_addr: str, custom_host: Optional[str] = None) -> str:
    """Auto-detects IMAP host from email domain or falls back to custom/default."""
    if custom_host and custom_host.strip():
        return custom_host.strip()
    em = (email_addr or "").lower().strip()
    if "@" in em:
        domain = em.split("@")[-1]
        if domain in ["gmail.com", "googlemail.com"]:
            return "imap.gmail.com"
        elif domain in ["outlook.com", "hotmail.com", "live.com", "office365.com"]:
            return "outlook.office365.com"
        elif domain in ["yahoo.com", "ymail.com"]:
            return "imap.mail.yahoo.com"
    return "imap.gmail.com"


def _decode_header_str(val: Optional[str]) -> str:
    """Decodes MIME encoded-word email headers into clean unicode strings."""
    if not val:
        return ""
    try:
        decoded_parts = decode_header(val)
        res = []
        for part, enc in decoded_parts:
            if isinstance(part, bytes):
                res.append(part.decode(enc or "utf-8", errors="ignore"))
            else:
                res.append(str(part))
        return " ".join(res).strip()
    except Exception:
        return str(val)


def _generate_email_record_pdf(
    pdf_path: Path,
    subject: str,
    sender: str,
    date_str: str,
    body_text: str,
    thread_history: List[Dict[str, Any]],
):
    """
    Generates a valid, readable PDF file using PyMuPDF for an email that lacks a binary file attachment.
    Enables ClearPay AP extraction and matching to process ANY plain email.
    """
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page()

    lines = [
        "============================================================",
        "INBOUND EMAIL INVOICE / AP TRANSACTION RECORD",
        "============================================================",
        f"SUBJECT:   {subject}",
        f"FROM:      {sender}",
        f"DATE:      {date_str}",
        f"SOURCE:    ClearPay AP Autonomous Ingestion Engine",
        "------------------------------------------------------------",
        "EMAIL BODY CONTENT:",
        "",
    ]
    lines.extend((body_text or "No text content in email body.").split("\n"))

    if len(thread_history) > 1:
        lines.append("")
        lines.append("------------------------------------------------------------")
        lines.append("CONVERSATION THREAD HISTORY:")
        lines.append("------------------------------------------------------------")
        for t in thread_history:
            lines.append(f">> SENDER: {t.get('sender', '')} | TIME: {t.get('timestamp', '')}")
            lines.extend(t.get("body", "").split("\n"))
            lines.append("")

    y = 50
    for line in lines:
        if y > 750:
            page = doc.new_page()
            y = 50
        if line and line.strip():
            page.insert_text((45, y), line[:115], fontsize=9)
        y += 13

    doc.save(str(pdf_path))
    doc.close()


def _extract_amount_and_currency_from_text(text: str) -> Tuple[str, str]:
    """Infers monetary amount badge and currency code from email text."""
    if not text:
        return "Ready to Scan", "INR"

    pattern = r"(?:(₹|INR|Rs\.?|\$|USD|€|EUR|£|GBP)\s*([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s*(₹|INR|Rs\.?|\$|USD|€|EUR|£|GBP))"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        curr = match.group(1) or match.group(4) or "INR"
        curr_clean = curr.upper().replace(".", "").strip()
        if curr_clean in ["₹", "RS"]:
            curr_code = "INR"
            symbol = "₹"
        elif curr_clean in ["$", "USD"]:
            curr_code = "USD"
            symbol = "$"
        elif curr_clean in ["€", "EUR"]:
            curr_code = "EUR"
            symbol = "€"
        elif curr_clean in ["£", "GBP"]:
            curr_code = "GBP"
            symbol = "£"
        else:
            curr_code = curr_clean
            symbol = curr_clean + " "

        amt_str = match.group(2) or match.group(3) or ""
        amt_str = amt_str.strip()
        if amt_str:
            return f"{symbol}{amt_str}", curr_code

    return "Ready to Scan", "INR"


def _parse_thread_history(body_text: str, sender: str, date_str: str) -> List[Dict[str, str]]:
    """Splits email body on reply markers into conversation thread turns."""
    if not body_text:
        return [{
            "sender": sender,
            "timestamp": date_str,
            "body": "No message body text."
        }]

    split_pattern = r"(?m)(?=^On\s+.*?wrote:|^-----Original Message-----|^From:\s+.*?Sent:)"
    parts = re.split(split_pattern, body_text)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) <= 1:
        return [{
            "sender": sender,
            "timestamp": date_str,
            "body": body_text
        }]

    turns = []
    for idx, part in enumerate(parts):
        turn_sender = sender if idx == 0 else "Thread Participant"
        turn_time = date_str if idx == 0 else "Earlier Message"

        m_on = re.match(r"^On\s+(.*?)\s+wrote:\s*(.*)", part, re.DOTALL | re.IGNORECASE)
        m_orig = re.match(r"^-----Original Message-----\s*(?:From:\s*(.*?)\s*)?(?:Sent:\s*(.*?)\s*)?(.*)", part, re.DOTALL | re.IGNORECASE)
        m_from = re.match(r"^From:\s*(.*?)\s*Sent:\s*(.*?)\s*(.*)", part, re.DOTALL | re.IGNORECASE)

        if m_on:
            turn_time = m_on.group(1).strip()
            turn_body = m_on.group(2).strip()
        elif m_orig:
            if m_orig.group(1):
                turn_sender = m_orig.group(1).strip()
            if m_orig.group(2):
                turn_time = m_orig.group(2).strip()
            turn_body = m_orig.group(3).strip() if m_orig.group(3) else part
        elif m_from:
            if m_from.group(1):
                turn_sender = m_from.group(1).strip()
            if m_from.group(2):
                turn_time = m_from.group(2).strip()
            turn_body = m_from.group(3).strip() if m_from.group(3) else part
        else:
            turn_body = part

        turns.append({
            "sender": turn_sender,
            "timestamp": turn_time,
            "body": turn_body[:2500]
        })

    return turns if turns else [{
        "sender": sender,
        "timestamp": date_str,
        "body": body_text
    }]


def _generate_default_thread(raw: Dict[str, Any], sender_name: str, sender_email: str, att_name: str, subject: str) -> List[Dict[str, str]]:
    """Generates realistic B2B purchasing conversation history for sample emails."""
    if raw.get("thread_history"):
        return raw["thread_history"]

    item_id = str(raw.get("id") or "")
    sc_id = str(raw.get("scenario_id") or "")

    if "001" in item_id or "01" in sc_id:
        return [
            {
                "sender": "Priya Sharma (AP Specialist - Acme Mfg)",
                "timestamp": "2026-10-24 10:30 AM",
                "body": "Hi Ramesh, we would like to procure 10,000 export corrugated cartons and 50 rolls of strapping tape for our November shipment batch. Please share the final quotation with GST breakdown."
            },
            {
                "sender": f"{sender_name} <{sender_email}>",
                "timestamp": "2026-10-24 02:45 PM",
                "body": "Hello Priya, Please find attached our formal quotation QTE-2026-081. 10,000 boxes @ ₹18.00 and 50 rolls tape @ ₹400.00. Subtotal: ₹2,00,000 + 18% IGST ₹36,000 = ₹2,36,000.00. Quotation validity: 30 days."
            },
            {
                "sender": "Priya Sharma (AP Specialist - Acme Mfg)",
                "timestamp": "2026-10-25 11:15 AM",
                "body": "Thank you Ramesh. We have approved quotation QTE-2026-081 and issued Purchase Order PO-2026-1041. Please proceed with delivery and submit your tax invoice referencing this PO."
            },
            {
                "sender": f"{sender_name} <{sender_email}>",
                "timestamp": "2026-10-28 09:15 AM",
                "body": "Dear Acme AP Team, All cartons and tape have been delivered to your Bhiwandi warehouse. Please find attached Tax Invoice INV-2026-0081. Kindly release payment within agreed Net 30 days."
            }
        ]
    elif "002" in item_id or "02" in sc_id:
        return [
            {
                "sender": "Vikram Seth (Procurement Lead - Acme Mfg)",
                "timestamp": "2026-10-15 09:00 AM",
                "body": "Hi Pooja, We are issuing PO-2026-1042 for 10 units High-Torque CNC Spindle Assemblies @ ₹10,000 each per quote QTE-2026-1042. Total ₹1,00,000. Please dispatch in 2 partial lots."
            },
            {
                "sender": f"{sender_name} <{sender_email}>",
                "timestamp": "2026-10-15 11:45 AM",
                "body": "Thank you Vikram. Order received. Lot 1 of 6 units will ship early next week, with the remaining 4 units following by month-end."
            },
            {
                "sender": f"{sender_name} <{sender_email}>",
                "timestamp": "2026-10-20 11:30 AM",
                "body": "Hello Accounts Payable Team, We have dispatched the first lot of 6 units of CNC Spindle Assemblies. Attached is invoice APEX-26-101 for INR 60,000.00."
            }
        ]
    elif "007" in item_id or "07" in sc_id:
        return [
            {
                "sender": "Ananya Roy (IT Procurement - Acme Mfg)",
                "timestamp": "2026-09-28 04:00 PM",
                "body": "Hi Brightline Team, We are proceeding with the Annual SaaS Subscription under quotation QTE-2026-1043. Please invoice $12,000 against PO-2026-1043."
            },
            {
                "sender": f"{sender_name} <{sender_email}>",
                "timestamp": "2026-10-01 09:30 AM",
                "body": "Attached is invoice BL-2026-9042 for $12,000.00. IMPORTANT NOTICE: We have recently migrated treasury banks. Remittance must be sent to our new account 999888777666 (Chase NYC) instead of the previous account."
            }
        ]

    # Default 2-turn thread
    return [
        {
            "sender": "Acme AP Procurement Team <ap-invoices@acmemfg.in>",
            "timestamp": "2026-10-20 10:00 AM",
            "body": f"Order confirmation sent to {sender_name}. Please submit final bill referencing approved PO or estimate."
        },
        {
            "sender": f"{sender_name} <{sender_email}>",
            "timestamp": "2026-10-28 11:00 AM",
            "body": raw.get("body") or raw.get("snippet") or f"Please find attached {att_name} for your review and processing."
        }
    ]


def _resolve_amount_and_currency(raw: Dict[str, Any], att_name: str) -> tuple:
    """Extracts or infers amount_display, amount_badge, and currency."""
    amt = raw.get("amount_display") or raw.get("amount_badge") or "Ready to Scan"
    curr = raw.get("currency") or "INR"
    return amt, curr


def _normalize_email_item(raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """Normalizes an item dictionary containing all keys expected by frontend drawer."""
    item_id = raw.get("id") or f"eml-{idx+1:03d}"
    from_str = raw.get("from")
    fn = raw.get("from_name")
    fe = raw.get("from_email")

    if not from_str:
        fn = fn or "Vendor Accounts"
        fe = fe or "billing@vendor.com"
        from_str = f"{fn} <{fe}>"
    else:
        if not fn:
            fn = re.sub(r"<.*?>", "", from_str).strip() or "Vendor Accounts"
        if not fe:
            m = re.search(r"<([^>]+)>", from_str)
            fe = m.group(1) if m else "billing@vendor.com"

    att_name = raw.get("attachment_filename") or raw.get("attachment_name") or ""
    unread = raw.get("unread", True)
    status = raw.get("status", "UNREAD" if unread else "PROCESSED")
    amt_disp, curr = _resolve_amount_and_currency(raw, att_name)
    body_text = raw.get("body") or raw.get("snippet") or "Please find attached document for your review."
    threads = _generate_default_thread(raw, fn, fe, att_name, raw.get("subject", ""))

    return {
        "id": item_id,
        "platform": "GMAIL",
        "from": from_str,
        "from_sender": fn,
        "sender_email": fe,
        "recipient": raw.get("recipient") or GMAIL_CONFIG.get("email") or "agent-ap-7492@clearpay.ai",
        "subject": raw.get("subject", "Vendor Invoice"),
        "date": raw.get("received_at") or raw.get("date") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "snippet": raw.get("snippet", ""),
        "body": body_text,
        "thread_history": threads,
        "has_attachment": bool(att_name),
        "attachment_name": att_name,
        "attachment_size": raw.get("attachment_size", "Ready"),
        "amount_badge": amt_disp,
        "amount_display": amt_disp,
        "currency": curr,
        "processed": status == "PROCESSED",
        "status": status,
        "run_id": raw.get("run_id"),
        "scenario_id": raw.get("scenario_id", ""),
    }


def _load_sandbox_sample_emails():
    """Disabled: sample emails are cleared to prevent pre-seeding fake data."""
    pass


def _ensure_gmail_messages_loaded():
    """State remains as added by inbound emails, keeping sample emails disabled."""
    pass


def get_all_platforms() -> List[Dict[str, Any]]:
    """Returns the two active intake channels: Manual Upload & Agent Email ID."""
    unread_gmail = sum(1 for m in _GMAIL_MESSAGES_STATE if m.get("status") == "UNREAD")
    return [
        {
            "platform_id": "manual_upload",
            "name": "Manual Document Upload",
            "icon": "upload",
            "account": "Direct Multi-Format Dropzone",
            "mode": "MANUAL",
            "status": "ACTIVE",
            "unread_count": 0,
            "total_count": 0,
            "last_sync": datetime.utcnow().isoformat() + "Z",
            "items": [],
        },
        {
            "platform_id": "gmail",
            "name": "Unique AP Agent Email ID",
            "icon": "gmail",
            "account": GMAIL_CONFIG["email"],
            "alias_account": GMAIL_CONFIG.get("alias_email", "ap_invoice@acmemfg.gmail.com"),
            "mode": "AGENT_ID",
            "status": "ACTIVE",
            "unread_count": unread_gmail,
            "total_count": len(_GMAIL_MESSAGES_STATE),
            "last_sync": GMAIL_CONFIG["last_sync"],
            "items": _GMAIL_MESSAGES_STATE,
        },
    ]


def list_gmail_messages(platform: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lists messages received by the Agent Email ID inbox."""
    global _GMAIL_MESSAGES_STATE
    return _GMAIL_MESSAGES_STATE


def remove_gmail_message_for_run(run_id: str) -> bool:
    """
    Removes any message in _GMAIL_MESSAGES_STATE whose run_id == run_id.
    Keeps its IMAP ID in processed_imap_ids.json so the IMAP poller never re-imports a deleted email.
    """
    _ensure_gmail_messages_loaded()
    global _GMAIL_MESSAGES_STATE
    initial_len = len(_GMAIL_MESSAGES_STATE)
    _GMAIL_MESSAGES_STATE[:] = [m for m in _GMAIL_MESSAGES_STATE if m.get("run_id") != run_id]
    return len(_GMAIL_MESSAGES_STATE) < initial_len


def send_email_to_agent(message_id: str) -> Dict[str, Any]:
    """
    Directly ingests an email's invoice attachment alongside its entire message body
    and multi-turn thread history into the ClearPay AP extraction & matching pipeline.
    Checks existing quotations and existing invoice runs:
    - If already there -> does NOT create a new duplicate invoice/quotation!
    - If not there -> creates a new invoice and compares against existing quotations.
    """
    _ensure_gmail_messages_loaded()
    global _GMAIL_MESSAGES_STATE
    target_item = next((itm for itm in _GMAIL_MESSAGES_STATE if itm["id"] == message_id), None)
    if not target_item:
        raise ValueError(f"Email message with ID '{message_id}' not found.")

    att_name = target_item.get("attachment_name") or ""
    file_path = DOWNLOADS_DIR / att_name if att_name else None
    if not file_path or not file_path.exists():
        file_path = SAMPLE_INVOICES_DIR / att_name if att_name else None

    # If no file exists on disk, generate a valid PDF from email body & thread history!
    if not file_path or not file_path.exists():
        fallback_name = att_name or f"{message_id}_record.pdf"
        file_path = DOWNLOADS_DIR / fallback_name
        _generate_email_record_pdf(
            file_path,
            subject=target_item.get("subject", "Inbound Invoice"),
            sender=target_item.get("from", "vendor@accounts.com"),
            date_str=target_item.get("date", datetime.now().strftime("%Y-%m-%d")),
            body_text=target_item.get("body", ""),
            thread_history=target_item.get("thread_history", [])
        )
        target_item["attachment_name"] = fallback_name
        target_item["has_attachment"] = True

    email_meta = {
        "from": target_item.get("from", ""),
        "subject": target_item.get("subject", ""),
        "date": target_item.get("date", ""),
        "platform": "GMAIL",
    }
    thread_history = target_item.get("thread_history", [])

    # 1. Inspect file and extract metadata to compare against existing quotations & runs
    file_hash = compute_sha256(str(file_path))
    std_inv = extract_standard_invoice(str(file_path), source_type="GMAIL", email_meta=email_meta)

    # 2. Check if the incoming email/attachment is actually a QUOTATION
    lower_att = (att_name or "").lower()
    lower_subj = (target_item.get("subject", "") or "").lower()
    lower_raw = (std_inv.raw_text_preview or "").lower()
    q_att_name = target_item.get("quotation_attachment_name")

    is_quotation_doc = False
    quote_keywords = ["quote", "quotation", "qte", "estimate"]

    if any(k in lower_att for k in quote_keywords):
        is_quotation_doc = True
    elif q_att_name and not att_name:
        is_quotation_doc = True
    elif any(k in lower_subj for k in quote_keywords) and not any(k in lower_subj for k in ["tax invoice", "final invoice", "bill"]):
        is_quotation_doc = True
    elif any(k in lower_raw[:350] for k in ["quotation", "price quote", "cost estimate", "formal quotation", "proforma quote"]):
        is_quotation_doc = True

    # If the email actually has BOTH an invoice attachment AND a quotation attachment,
    # it is an invoice with quotation context, not a standalone quotation!
    if q_att_name and att_name and q_att_name != att_name:
        is_quotation_doc = False

    if is_quotation_doc:
        q_num = str(std_inv.invoice_number.value or std_inv.po_reference.value or Path(att_name or "quotation").stem).strip()
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
            "line_items": [l.dict() if hasattr(l, "dict") else l for l in items],
            "filename": att_name or file_path.name,
            "file_path": str(file_path),
            "status": "PENDING_INVOICE",
            "matched_run_ids": [],
            "matched_invoice_numbers": [],
            "notes": f"Autonomous email intake: quotation extracted from '{att_name or target_item.get('subject', '')}'.",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "ai_summary": ai_sum,
            "ai_flaws": ai_flws,
        }

        # create_or_update_quotation will automatically call reconcile_existing_runs_with_quotation
        saved_quotation = create_or_update_quotation(quote_record)

        linked_run: Optional[InvoiceRunResult] = None
        if saved_quotation.get("matched_run_ids"):
            linked_run = get_run(saved_quotation["matched_run_ids"][0])

        target_item["status"] = "PROCESSED"
        target_item["processed"] = True
        if linked_run:
            target_item["run_id"] = linked_run.run_id

        inv_details = (
            f"and auto-approved existing Invoice {linked_run.standard_invoice.invoice_number.value}!"
            if linked_run
            else "and saved to Advance Quotations store."
        )
        return {
            "run": linked_run,
            "quotation": saved_quotation,
            "is_quotation": True,
            "already_exists": False,
            "quotation_already_exists": True,
            "matched_quotation_number": saved_quotation["quotation_number"],
            "agent_summary": (
                f"Agent analyzed email thread ({len(thread_history)} turns) & attachment: "
                f"Extracted Quotation {saved_quotation['quotation_number']} from {v_name} ({len(items)} items) {inv_details}"
            ),
        }

    norm_inv = (
        re.sub(r"[\/\-\_\s]", "", str(std_inv.invoice_number.value)).upper()
        if std_inv.invoice_number and std_inv.invoice_number.value
        else None
    )

    # 2. Check existing quotations in quotations.json (from invoice fields AND full email history)
    matched_quotation = find_matching_quotation(std_inv)
    if not matched_quotation:
        all_quotes = load_quotations()
        combined_email_text = " ".join([
            str(target_item.get("subject", "")),
            str(target_item.get("body", "")),
            " ".join(f"{t.get('sender', '')} {t.get('body', '')}" for t in thread_history),
        ]).upper()
        clean_combined = re.sub(r"[^A-Z0-9]", "", combined_email_text)
        for q in all_quotes:
            q_num = str(q.get("quotation_number", "")).strip().upper()
            clean_q = re.sub(r"[^A-Z0-9]", "", q_num)
            if clean_q and clean_q in clean_combined:
                matched_quotation = q
                break

    quotation_filepath = None
    q_att_name = target_item.get("quotation_attachment_name")
    if q_att_name and not matched_quotation:
        qp = DOWNLOADS_DIR / q_att_name
        if qp.exists():
            quotation_filepath = str(qp)

    # 3. Check if an invoice run for this email / file hash / invoice number ALREADY exists on the site
    existing_runs = get_all_runs()
    existing_run: Optional[InvoiceRunResult] = None

    # 3a. Check by run_id already linked to this email
    if target_item.get("run_id"):
        existing_run = next((r for r in existing_runs if r.run_id == target_item["run_id"]), None)

    # 3b. Check by exact file_hash or normalized_invoice_number + same vendor
    if not existing_run:
        inv_vendor_clean = re.sub(r"[^a-z0-9]", "", str(std_inv.vendor_name.value or "").lower())
        for prev_run in existing_runs:
            if prev_run.decision == "REJECT" and "DUPLICATE_INVOICE" in prev_run.reason_codes:
                continue
            prev_inv = prev_run.standard_invoice
            if prev_inv.source_info.file_hash == file_hash:
                existing_run = prev_run
                break
            prev_norm = prev_inv.normalized_invoice_number
            prev_vendor_clean = re.sub(r"[^a-z0-9]", "", str(prev_inv.vendor_name.value or "").lower())
            same_vendor = (
                (std_inv.matched_vendor_id and std_inv.matched_vendor_id == prev_run.matched_vendor_id)
                or (inv_vendor_clean and prev_vendor_clean and (inv_vendor_clean in prev_vendor_clean or prev_vendor_clean in inv_vendor_clean))
            )
            if norm_inv and prev_norm and norm_inv == prev_norm and same_vendor:
                existing_run = prev_run
                break

    if existing_run:
        # Already exists -> DO NOT make a new invoice run!
        updated_existing = existing_run
        if thread_history and not updated_existing.email_thread_history:
            updated_existing.email_thread_history = thread_history
            save_run(updated_existing)
        if matched_quotation and (
            not updated_existing.expected_quotation
            or updated_existing.expected_quotation.match_status == "NO_QUOTATION"
        ):
            linked = link_quotation_to_run(updated_existing.run_id, matched_quotation["quotation_id"])
            if linked:
                updated_existing = linked

        target_item["status"] = "PROCESSED"
        target_item["processed"] = True
        target_item["run_id"] = updated_existing.run_id

        q_label = (
            matched_quotation.get("quotation_number")
            if matched_quotation
            else (
                updated_existing.expected_quotation.quotation_number
                if updated_existing.expected_quotation and updated_existing.expected_quotation.quotation_number
                else "Stored Ledger"
            )
        )
        inv_label = updated_existing.standard_invoice.invoice_number.value or updated_existing.run_id
        return {
            "run": updated_existing,
            "already_exists": True,
            "quotation_already_exists": bool(matched_quotation),
            "matched_quotation_number": q_label,
            "agent_summary": f"Agent verified email thread ({len(thread_history)} turns) & attachment: Invoice {inv_label} already exists on the Dashboard — skipped creating duplicate!",
        }

    # 4. Not there -> Create a NEW invoice run and compare with existing quotation
    run_result = process_invoice_file(
        filepath=str(file_path),
        source_type="GMAIL",
        email_meta=email_meta,
        scenario_tag=target_item.get("scenario_id") or target_item.get("id"),
        quotation_filepath=quotation_filepath,
        quotation_id=matched_quotation["quotation_id"] if matched_quotation else None,
        email_thread_history=thread_history,
    )

    target_item["status"] = "PROCESSED"
    target_item["processed"] = True
    target_item["run_id"] = run_result.run_id

    q_label = (
        matched_quotation.get("quotation_number")
        if matched_quotation
        else (
            run_result.expected_quotation.quotation_number
            if run_result.expected_quotation and run_result.expected_quotation.quotation_number
            else "PO / Quotation Ledger"
        )
    )
    inv_label = run_result.standard_invoice.invoice_number.value or run_result.run_id

    return {
        "run": run_result,
        "already_exists": False,
        "quotation_already_exists": bool(matched_quotation),
        "matched_quotation_number": q_label,
        "agent_summary": f"Agent analyzed email history ({len(thread_history)} turns) & attachment: Created new Invoice {inv_label} and compared with Quotation {q_label}.",
    }


def add_extension_push_message(
    sender: str,
    subject: str,
    body: str,
    date_str: Optional[str] = None,
    thread_history: Optional[List[Dict[str, Any]]] = None,
    attachment_name: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    quotation_name: Optional[str] = None,
    quotation_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """
    Directly adds an email pushed from the Chrome Extension into _GMAIL_MESSAGES_STATE,
    saving any binary attachments or generating a PDF from the email conversation.
    """
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    new_id = f"ext-{datetime.now().strftime('%H%M%S')}-{uuid.uuid4().hex[:4]}"

    saved_att_name = ""
    att_size_str = "1 KB"
    if attachment_name and attachment_bytes:
        clean_name = Path(attachment_name).name
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', clean_name)
        save_path = DOWNLOADS_DIR / safe_name
        with open(save_path, "wb") as f:
            f.write(attachment_bytes)
        saved_att_name = safe_name
        att_size_str = f"{len(attachment_bytes) // 1024 + 1} KB"

    saved_quote_name = ""
    if quotation_name and quotation_bytes:
        clean_qname = Path(quotation_name).name
        safe_qname = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', clean_qname)
        q_path = DOWNLOADS_DIR / safe_qname
        with open(q_path, "wb") as f:
            f.write(quotation_bytes)
        saved_quote_name = safe_qname

    from_name, from_email = email.utils.parseaddr(sender)
    if not from_name:
        from_name = from_email.split("@")[0] if "@" in from_email else sender
    if not from_email:
        from_email = "vendor@accounts.com"

    resolved_date = date_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resolved_thread = thread_history if thread_history and len(thread_history) > 0 else _parse_thread_history(body, sender, resolved_date)

    if not saved_att_name:
        pdf_fname = f"ext_email_{new_id}.pdf"
        _generate_email_record_pdf(
            DOWNLOADS_DIR / pdf_fname,
            subject=subject,
            sender=sender,
            date_str=resolved_date,
            body_text=body,
            thread_history=resolved_thread
        )
        saved_att_name = pdf_fname
        att_size_str = "1 KB"

    amt_badge, curr = _extract_amount_and_currency_from_text(f"{subject} {body}")

    new_msg = {
        "id": new_id,
        "platform": "GMAIL",
        "from": sender,
        "from_sender": from_name,
        "sender_email": from_email,
        "recipient": GMAIL_CONFIG.get("email") or "ap-invoices@clearpay.ai",
        "subject": subject or "Inbound Gmail Invoice",
        "date": resolved_date,
        "snippet": body[:120] if body else f"Inbound Gmail extension push: {saved_att_name}",
        "body": body,
        "thread_history": resolved_thread,
        "has_attachment": True,
        "attachment_name": saved_att_name,
        "attachment_size": att_size_str,
        "quotation_attachment_name": saved_quote_name,
        "all_attachments": [saved_att_name] + ([saved_quote_name] if saved_quote_name else []),
        "amount_badge": amt_badge,
        "amount_display": amt_badge,
        "currency": curr,
        "processed": False,
        "status": "UNREAD",
        "run_id": None,
    }

    _GMAIL_MESSAGES_STATE.insert(0, new_msg)
    return new_msg


def add_inbound_email(
    from_sender: str,
    subject: str,
    body: str,
    attachment_filename: Optional[str] = None,
    attachment_bytes: Optional[bytes] = None,
    quotation_filename: Optional[str] = None,
    quotation_bytes: Optional[bytes] = None,
) -> Dict[str, Any]:
    """Adds a new inbound email to the Gmail AP Inbox queue with optional attachments."""
    _ensure_gmail_messages_loaded()
    global _GMAIL_MESSAGES_STATE

    new_id = f"eml-{len(_GMAIL_MESSAGES_STATE) + 1:03d}"
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    att_name = ""
    att_size = "0 KB"
    if attachment_filename and attachment_bytes:
        att_name = attachment_filename
        save_path = DOWNLOADS_DIR / att_name
        with open(save_path, "wb") as f:
            f.write(attachment_bytes)
        att_size = f"{len(attachment_bytes) // 1024 + 1} KB"

    if quotation_filename and quotation_bytes:
        q_path = DOWNLOADS_DIR / quotation_filename
        with open(q_path, "wb") as f:
            f.write(quotation_bytes)

    sender_email = "vendor@accounts.com"
    fn = from_sender
    if "<" in from_sender and ">" in from_sender:
        m = re.search(r"<([^>]+)>", from_sender)
        if m:
            sender_email = m.group(1)
        fn = re.sub(r"<.*?>", "", from_sender).strip()

    amt_badge, curr = _extract_amount_and_currency_from_text(f"{subject} {body}")

    new_message = {
        "id": new_id,
        "platform": "GMAIL",
        "from": from_sender if "<" in from_sender else f"{from_sender} <{sender_email}>",
        "from_sender": fn,
        "sender_email": sender_email,
        "recipient": GMAIL_CONFIG["email"],
        "subject": subject or "New Vendor Invoice & Quotation",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "snippet": body[:120] if body else f"Inbound email with attachment: {att_name}",
        "body": body or "Please find attached our quotation and invoice for processing.",
        "thread_history": [
            {
                "sender": f"{fn} <{sender_email}>",
                "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
                "body": body or "Please find attached document for your review and processing."
            }
        ],
        "has_attachment": bool(att_name),
        "attachment_name": att_name,
        "attachment_size": att_size,
        "quotation_attachment_name": quotation_filename or "",
        "amount_badge": amt_badge,
        "amount_display": amt_badge,
        "currency": curr,
        "processed": False,
        "status": "UNREAD",
        "run_id": None,
    }

    _GMAIL_MESSAGES_STATE.insert(0, new_message)
    return new_message


def pull_gmail_messages(message_ids: List[str]) -> List[InvoiceRunResult]:
    """Pulls selected messages and returns runs."""
    global _GMAIL_MESSAGES_STATE
    runs: List[InvoiceRunResult] = []

    for mid in message_ids:
        target_item = next((itm for itm in _GMAIL_MESSAGES_STATE if itm["id"] == mid), None)
        if not target_item:
            continue

        res = send_email_to_agent(mid)
        if res.get("run"):
            runs.append(res["run"])

    return runs


def pull_all_sources(platform_filter: Optional[str] = None) -> List[InvoiceRunResult]:
    """Pulls all unread messages from agent inbox."""
    global _GMAIL_MESSAGES_STATE
    unread_ids = [m["id"] for m in _GMAIL_MESSAGES_STATE if m.get("status") == "UNREAD"]
    if unread_ids:
        return pull_gmail_messages(unread_ids)
    return []
    if unread_ids:
        return pull_gmail_messages(unread_ids)
    return []


def _fetch_live_imap_messages(
    imap_host: Optional[str] = None,
    email_addr: Optional[str] = None,
    app_password: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetches real messages (read + unread) from connected live IMAP server."""
    messages = []
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

    target_email = (email_addr or GMAIL_CONFIG.get("email") or "").strip()
    target_pwd = (app_password or GMAIL_CONFIG.get("app_password") or "").replace(" ", "").strip()
    host = _detect_imap_host(target_email, imap_host or GMAIL_CONFIG.get("imap_host"))

    if not target_email or not target_pwd:
        return []

    mail = None
    try:
        mail = imaplib.IMAP4_SSL(host, port=993)
        mail.login(target_email, target_pwd)
        mail.select("INBOX")

        unseen_ids = set()
        try:
            status_unseen, unseen_data = mail.search(None, "UNSEEN")
            if status_unseen == "OK" and unseen_data and unseen_data[0]:
                unseen_ids = set(m.decode() for m in unseen_data[0].split())
        except Exception:
            pass

        status, data = mail.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return []

        all_mail_ids = data[0].split()
        selected_ids = list(reversed(all_mail_ids[-25:]))

        for mid_bytes in selected_ids:
            mid = mid_bytes.decode()
            status, msg_data = mail.fetch(mid_bytes, "(RFC822)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            if not isinstance(raw_email, (bytes, bytearray)):
                continue

            msg = email.message_from_bytes(raw_email)

            subject = _decode_header_str(msg.get("Subject", "Vendor Email"))
            from_header = _decode_header_str(msg.get("From", "vendor@accounts.com"))
            date_str = msg.get("Date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

            from_name, from_email = email.utils.parseaddr(from_header)
            if not from_name:
                from_name = from_email.split("@")[0] if "@" in from_email else from_header
            if not from_email:
                from_email = target_email

            plain_bodies = []
            html_bodies = []
            attachments: List[Tuple[str, int]] = []

            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                raw_fname = part.get_filename()

                is_att = bool(raw_fname) or ("attachment" in content_disposition.lower())
                if is_att:
                    fname = _decode_header_str(raw_fname) if raw_fname else f"email_file_{mid}.pdf"
                    clean_name = Path(fname).name
                    safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', clean_name)
                    ext = Path(safe_name).suffix.lower()
                    if ext in [".pdf", ".png", ".jpg", ".jpeg", ".xlsx", ".docx", ".txt", ".csv", ".html"]:
                        payload = part.get_payload(decode=True)
                        if payload:
                            save_path = DOWNLOADS_DIR / safe_name
                            with open(save_path, "wb") as f:
                                f.write(payload)
                            attachments.append((safe_name, len(payload)))
                elif content_type == "text/plain":
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            plain_bodies.append(payload.decode(charset, errors="ignore"))
                        except Exception:
                            plain_bodies.append(payload.decode("utf-8", errors="ignore"))
                elif content_type == "text/html":
                    charset = part.get_content_charset() or "utf-8"
                    payload = part.get_payload(decode=True)
                    if payload:
                        try:
                            html_bodies.append(payload.decode(charset, errors="ignore"))
                        except Exception:
                            html_bodies.append(payload.decode("utf-8", errors="ignore"))

            if plain_bodies:
                body_text = "\n\n".join(plain_bodies).strip()
            elif html_bodies:
                raw_html = "\n".join(html_bodies)
                cleaned = re.sub(r'(?i)<br\s*/?>', '\n', raw_html)
                cleaned = re.sub(r'(?i)</p>', '\n\n', cleaned)
                cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
                body_text = re.sub(r'[ \t]+', ' ', cleaned).strip()
            else:
                body_text = ""

            thread_history = _parse_thread_history(body_text, from_header, date_str)

            primary_att = ""
            quotation_att = ""
            all_att_names = [a[0] for a in attachments]
            for a_name in all_att_names:
                low = a_name.lower()
                if any(k in low for k in ["quote", "quotation", "qte", "est"]):
                    if not quotation_att:
                        quotation_att = a_name
                else:
                    if not primary_att:
                        primary_att = a_name
            if not primary_att and all_att_names:
                primary_att = all_att_names[0]

            if not primary_att:
                pdf_fname = f"imap_email_{mid}.pdf"
                _generate_email_record_pdf(
                    DOWNLOADS_DIR / pdf_fname,
                    subject=subject,
                    sender=from_header,
                    date_str=date_str,
                    body_text=body_text,
                    thread_history=thread_history,
                )
                primary_att = pdf_fname
                att_size_str = "1 KB"
            else:
                att_size_str = f"{(DOWNLOADS_DIR / primary_att).stat().st_size // 1024 + 1} KB"

            amt_badge, curr = _extract_amount_and_currency_from_text(f"{subject} {body_text}")
            is_unread = mid in unseen_ids

            messages.append({
                "id": f"imap-{mid}",
                "platform": "GMAIL",
                "from": from_header,
                "from_sender": from_name,
                "sender_email": from_email,
                "recipient": target_email,
                "subject": subject,
                "date": date_str,
                "snippet": (body_text[:120] if body_text else f"Email document: {primary_att}"),
                "body": body_text,
                "thread_history": thread_history,
                "has_attachment": True,
                "attachment_name": primary_att,
                "attachment_size": att_size_str,
                "quotation_attachment_name": quotation_att,
                "all_attachments": all_att_names,
                "amount_badge": amt_badge,
                "amount_display": amt_badge,
                "currency": curr,
                "processed": False,
                "status": "UNREAD" if is_unread else "READ",
                "run_id": None,
            })

        mail.logout()
    except Exception as e:
        if mail:
            try:
                mail.logout()
            except Exception:
                pass
        raise e

    return messages


def _fetch_live_oauth_messages(oauth_token: str) -> List[Dict[str, Any]]:
    """Fetches real Gmail messages via Google OAuth Bearer Token and Gmail REST API."""
    messages = []
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=25"
    headers = {
        "Authorization": f"Bearer {oauth_token.strip()}",
        "Accept": "application/json"
    }

    try:
        req = urllib.request.Request(list_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            list_data = json.loads(resp.read().decode())
    except Exception as e:
        raise ValueError(f"Google OAuth API request failed: {e}. Check that token is valid with https://www.googleapis.com/auth/gmail.readonly scope.")

    msg_items = list_data.get("messages", [])
    for itm in msg_items:
        mid = itm["id"]
        detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?format=full"
        try:
            d_req = urllib.request.Request(detail_url, headers=headers)
            with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                msg_json = json.loads(d_resp.read().decode())
        except Exception:
            continue

        headers_list = msg_json.get("payload", {}).get("headers", [])
        h_map = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

        subject = h_map.get("subject", "Vendor Email")
        from_str = h_map.get("from", "vendor@accounts.com")
        date_str = h_map.get("date", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        snippet = msg_json.get("snippet", "")

        from_name, from_email = email.utils.parseaddr(from_str)
        if not from_name:
            from_name = from_email.split("@")[0] if "@" in from_email else from_str

        body_text = snippet
        attachments: List[Tuple[str, int]] = []
        payload_obj = msg_json.get("payload", {})

        def _walk_gmail_parts(part_node):
            mime_type = part_node.get("mimeType", "")
            fname = part_node.get("filename", "")
            body_node = part_node.get("body", {})
            att_id = body_node.get("attachmentId")

            if fname and att_id:
                att_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}/attachments/{att_id}"
                try:
                    att_req = urllib.request.Request(att_url, headers=headers)
                    with urllib.request.urlopen(att_req, timeout=10) as att_resp:
                        att_json = json.loads(att_resp.read().decode())
                        raw_data = att_json.get("data", "")
                        file_bytes = base64.urlsafe_b64decode(raw_data.encode("UTF-8"))
                        safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', fname)
                        with open(DOWNLOADS_DIR / safe_name, "wb") as f:
                            f.write(file_bytes)
                        attachments.append((safe_name, len(file_bytes)))
                except Exception:
                    pass
            elif mime_type == "text/plain" and body_node.get("data"):
                try:
                    text_str = base64.urlsafe_b64decode(body_node["data"].encode("UTF-8")).decode("utf-8", errors="ignore")
                    nonlocal body_text
                    body_text = text_str
                except Exception:
                    pass

            for subpart in part_node.get("parts", []):
                _walk_gmail_parts(subpart)

        _walk_gmail_parts(payload_obj)

        thread_history = _parse_thread_history(body_text, from_str, date_str)

        primary_att = ""
        quotation_att = ""
        all_att_names = [a[0] for a in attachments]
        for a_name in all_att_names:
            low = a_name.lower()
            if any(k in low for k in ["quote", "quotation", "qte", "est"]):
                if not quotation_att:
                    quotation_att = a_name
            else:
                if not primary_att:
                    primary_att = a_name
        if not primary_att and all_att_names:
            primary_att = all_att_names[0]

        if not primary_att:
            pdf_fname = f"gmail_{mid}.pdf"
            _generate_email_record_pdf(
                DOWNLOADS_DIR / pdf_fname,
                subject=subject,
                sender=from_str,
                date_str=date_str,
                body_text=body_text,
                thread_history=thread_history,
            )
            primary_att = pdf_fname
            att_size_str = "1 KB"
        else:
            att_size_str = f"{(DOWNLOADS_DIR / primary_att).stat().st_size // 1024 + 1} KB"

        amt_badge, curr = _extract_amount_and_currency_from_text(f"{subject} {body_text}")

        messages.append({
            "id": f"oauth-{mid}",
            "platform": "GMAIL",
            "from": from_str,
            "from_sender": from_name,
            "sender_email": from_email,
            "recipient": GMAIL_CONFIG.get("email") or "ap-invoices@clearpay.ai",
            "subject": subject,
            "date": date_str,
            "snippet": snippet or (body_text[:120] if body_text else f"Email attachment: {primary_att}"),
            "body": body_text,
            "thread_history": thread_history,
            "has_attachment": True,
            "attachment_name": primary_att,
            "attachment_size": att_size_str,
            "quotation_attachment_name": quotation_att,
            "all_attachments": all_att_names,
            "amount_badge": amt_badge,
            "amount_display": amt_badge,
            "currency": curr,
            "processed": False,
            "status": "UNREAD",
            "run_id": None,
        })

    return messages


def connect_gmail(
    mode: str = "SIMULATED",
    email_addr: Optional[str] = None,
    app_password: Optional[str] = None,
    oauth_token: Optional[str] = None,
    imap_host: Optional[str] = None,
) -> Dict[str, Any]:
    """Configures Gmail connection to live IMAP, Google OAuth REST API, or Sandbox."""
    global _GMAIL_MESSAGES_STATE
    GMAIL_CONFIG["mode"] = mode
    if email_addr:
        GMAIL_CONFIG["email"] = email_addr.strip()
    if app_password:
        GMAIL_CONFIG["app_password"] = app_password.replace(" ", "").strip()
    if oauth_token:
        GMAIL_CONFIG["oauth_token"] = oauth_token.strip()
    if imap_host:
        GMAIL_CONFIG["imap_host"] = imap_host.strip()

    GMAIL_CONFIG["last_sync"] = datetime.utcnow().isoformat() + "Z"

    if mode == "IMAP":
        try:
            msgs = _fetch_live_imap_messages(
                imap_host=GMAIL_CONFIG.get("imap_host"),
                email_addr=GMAIL_CONFIG.get("email"),
                app_password=GMAIL_CONFIG.get("app_password")
            )
            GMAIL_CONFIG["connected"] = True
            _GMAIL_MESSAGES_STATE = msgs
            return {
                "status": "connected",
                "mode": "IMAP",
                "email": GMAIL_CONFIG["email"],
                "unread_count": sum(1 for m in msgs if m.get("status") == "UNREAD"),
                "total_count": len(msgs),
                "messages": msgs,
                "message": f"Successfully authenticated via IMAP and retrieved {len(msgs)} live emails from {GMAIL_CONFIG['email']}!",
            }
        except Exception as e:
            GMAIL_CONFIG["connected"] = False
            return {
                "status": "error",
                "mode": "IMAP",
                "email": GMAIL_CONFIG["email"],
                "message": f"IMAP authentication failed for {GMAIL_CONFIG['email']}: {str(e)}. If using Gmail, ensure 2-Step Verification is active and you use a 16-character App Password generated at https://myaccount.google.com/apppasswords.",
            }

    elif mode == "OAUTH":
        token = GMAIL_CONFIG.get("oauth_token") or oauth_token
        if not token:
            GMAIL_CONFIG["connected"] = False
            return {
                "status": "error",
                "mode": "OAUTH",
                "message": "Google OAuth Bearer Access Token is required.",
            }
        try:
            msgs = _fetch_live_oauth_messages(token)
            GMAIL_CONFIG["connected"] = True
            _GMAIL_MESSAGES_STATE = msgs
            return {
                "status": "connected",
                "mode": "OAUTH",
                "email": GMAIL_CONFIG.get("email", "me"),
                "unread_count": sum(1 for m in msgs if m.get("status") == "UNREAD"),
                "total_count": len(msgs),
                "messages": msgs,
                "message": f"Successfully connected via Google OAuth REST API and retrieved {len(msgs)} real Gmail messages!",
            }
        except Exception as e:
            GMAIL_CONFIG["connected"] = False
            return {
                "status": "error",
                "mode": "OAUTH",
                "message": f"Google OAuth REST API failed: {str(e)}. Please verify token and scopes.",
            }

    # SIMULATED Mode
    GMAIL_CONFIG["connected"] = True
    _load_sandbox_sample_emails()
    return {
        "status": "connected",
        "mode": "SIMULATED",
        "email": GMAIL_CONFIG["email"],
        "unread_count": sum(1 for m in _GMAIL_MESSAGES_STATE if m.get("status") == "UNREAD"),
        "total_count": len(_GMAIL_MESSAGES_STATE),
        "messages": _GMAIL_MESSAGES_STATE,
        "message": "Connected to Built-in Sandbox AP Inbox.",
    }


def install_extension_direct(
    email_addr: Optional[str] = None,
    app_password: Optional[str] = None,
    oauth_token: Optional[str] = None,
    imap_host: Optional[str] = None,
    use_sandbox: bool = False,
) -> Dict[str, Any]:
    """
    Directly installs and activates the ClearPay AP Extension.
    Supports real Gmail IMAP, Google OAuth, or Sandbox demo.
    """
    global _GMAIL_MESSAGES_STATE

    if use_sandbox:
        GMAIL_CONFIG["mode"] = "SIMULATED"
        GMAIL_CONFIG["email"] = "sandbox-demo@clearpay.ai"
        GMAIL_CONFIG["extension_installed"] = True
        GMAIL_CONFIG["connected"] = True
        GMAIL_CONFIG["last_sync"] = datetime.utcnow().isoformat() + "Z"
        _load_sandbox_sample_emails()
        status = get_gmail_status()
        status["messages"] = _GMAIL_MESSAGES_STATE
        status["message"] = f"Connected Sandbox Test Inbox with {len(_GMAIL_MESSAGES_STATE)} sample emails."
        return status

    if email_addr and app_password:
        res = connect_gmail(
            mode="IMAP",
            email_addr=email_addr,
            app_password=app_password,
            imap_host=imap_host
        )
        if res.get("status") == "error":
            return res
        GMAIL_CONFIG["extension_installed"] = True
        return res

    if oauth_token:
        res = connect_gmail(
            mode="OAUTH",
            email_addr=email_addr or "me",
            oauth_token=oauth_token
        )
        if res.get("status") == "error":
            return res
        GMAIL_CONFIG["extension_installed"] = True
        return res

    # Keep existing state or activate direct
    GMAIL_CONFIG["extension_installed"] = True
    GMAIL_CONFIG["connected"] = True
    GMAIL_CONFIG["last_sync"] = datetime.utcnow().isoformat() + "Z"
    status = get_gmail_status()
    status["messages"] = _GMAIL_MESSAGES_STATE
    return status


def uninstall_extension_direct() -> Dict[str, Any]:
    """Resets the direct website extension installation state."""
    global _GMAIL_MESSAGES_STATE
    GMAIL_CONFIG["extension_installed"] = False
    GMAIL_CONFIG["connected"] = False
    GMAIL_CONFIG["app_password"] = None
    GMAIL_CONFIG["oauth_token"] = None
    _GMAIL_MESSAGES_STATE = []
    GMAIL_CONFIG["last_sync"] = datetime.utcnow().isoformat() + "Z"
    return get_gmail_status()


def get_gmail_status() -> Dict[str, Any]:
    """Returns current Gmail connector status."""
    unread = sum(1 for m in _GMAIL_MESSAGES_STATE if m.get("status") == "UNREAD")
    return {
        "platform_id": "gmail",
        "name": "Unique AP Agent Email ID",
        "connected": True,
        "email": AGENT_EMAIL_CONFIG["company_agent_email"],
        "alias_email": AGENT_EMAIL_CONFIG.get("employee_agent_email", AGENT_EMAIL_CONFIG["company_agent_email"]),
        "agent_id": AGENT_EMAIL_CONFIG["company_agent_email"],
        "bot_base_email": AGENT_EMAIL_CONFIG.get("bot_base_email", "zamp.ap.agent@gmail.com"),
        "bot_imap_connected": bool(AGENT_EMAIL_CONFIG.get("bot_app_password")),
        "routing_mode": AGENT_EMAIL_CONFIG.get("routing_mode", "GMAIL_PLUS_SUBADDRESSING"),
        "mode": GMAIL_CONFIG["mode"],
        "extension_installed": True,
        "extension_version": GMAIL_CONFIG.get("extension_version", "3.0.0-agent-id"),
        "unread_count": unread,
        "total_count": len(_GMAIL_MESSAGES_STATE),
        "last_sync": GMAIL_CONFIG["last_sync"],
    }


def reset_gmail_inbox():
    """Resets Gmail messages state without re-loading sample emails."""
    global _GMAIL_MESSAGES_STATE
    _GMAIL_MESSAGES_STATE = []


def poll_and_process_bot_inbox() -> List[Dict[str, Any]]:
    """
    Autonomous background worker that polls the central agent bot Gmail inbox via IMAP (SSL:993).
    Extracts multi-tenant +tag routing information, downloads attachments, parses email bodies,
    and immediately passes invoices and quotations to the processing engine.
    """
    global _GMAIL_MESSAGES_STATE
    bot_email = (AGENT_EMAIL_CONFIG.get("bot_base_email") or os.getenv("AGENT_BOT_EMAIL", "")).strip()
    bot_pwd = (AGENT_EMAIL_CONFIG.get("bot_app_password") or os.getenv("AGENT_BOT_APP_PASSWORD", "")).strip()
    clean_pwd = bot_pwd.replace(" ", "").strip() if bot_pwd else ""

    if not clean_pwd or not bot_email:
        return []

    processed_ids = _load_processed_imap_ids()
    new_results = []

    ignored_senders = (
        "no-reply@accounts.google.com",
        "googlecommunityteam-noreply@google.com",
        "mailer-daemon@googlemail.com",
        "noreply@google.com",
    )
    ignored_subjects = (
        "security alert",
        "2-step verification",
        "app password",
        "finish setting up your new google account",
        "delivery status notification",
        "address not found",
        "undeliverable",
    )

    try:
        raw_msgs = _fetch_live_imap_messages(email_addr=bot_email, app_password=clean_pwd)
        for msg in raw_msgs:
            mid = msg.get("id")
            if not mid or mid in processed_ids:
                continue

            sender_low = (msg.get("sender_email") or msg.get("from") or "").lower()
            subj_low = (msg.get("subject") or "").lower()

            if any(ig in sender_low for ig in ignored_senders) or any(ig_s in subj_low for ig_s in ignored_subjects):
                processed_ids.add(mid)
                continue

            processed_ids.add(mid)
            if not any(m.get("id") == mid for m in _GMAIL_MESSAGES_STATE):
                _GMAIL_MESSAGES_STATE.insert(0, msg)

            try:
                res = send_email_to_agent(mid)
                new_results.append(res)
            except Exception:
                pass

        _save_processed_imap_ids(processed_ids)
    except Exception:
        pass

    return new_results
