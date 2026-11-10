"""
ClearPay AP - Multi-Format Document Ingestion & Extraction Engine.

Supports:
- PDF (text layer extraction via pymupdf; scans detected if text is empty/minimal)
- Images (PNG, JPG, JPEG)
- Excel Spreadsheets (.xlsx via openpyxl)
- Word Documents (.docx via docx)

Provides:
- render_file_preview_png(filepath: str) -> bytes: Renders page 1 of PDF to PNG,
  converts images, or generates high-res visual document previews for XLSX and DOCX.
- extract_standard_invoice(filepath: str, source_type: str = "UPLOAD", ...) -> StandardInvoice:
  Multi-tier extraction supporting optional live Gemini/OpenAI API or rock-solid
  deterministic regex/table layout parser for all 11 core scenarios and arbitrary user files.
"""

import os
import re
import io
import json
import hashlib
import urllib.request
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

import pymupdf  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont
import openpyxl
import docx

from backend.schemas import (
    StandardInvoice,
    SourceInfo,
    ExtractedField,
    StandardLineItem,
)

import backend.llm as unified_llm
from backend.ocr import read_document

# Global runtime AI configuration (delegates to backend.llm)
AI_CONFIG = {
    "groq_api_key": os.getenv("GROQ_API_KEY", "").strip(),
    "groq_model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip(),
    "preferred_provider": "GEMINI" if os.getenv("GEMINI_API_KEY") else ("GROQ" if os.getenv("GROQ_API_KEY") else "NONE"),
    "gemini_api_key": os.getenv("GEMINI_API_KEY", "").strip(),
    "openai_api_key": os.getenv("OPENAI_API_KEY", "").strip(),
}


def set_ai_api_key(provider: str, api_key: str):
    """Sets AI API key at runtime and syncs with unified LLM module."""
    unified_llm.set_ai_api_key(provider, api_key)
    provider_upper = (provider or "").upper()
    key_val = (api_key or "").strip()
    if "GROQ" in provider_upper:
        AI_CONFIG["groq_api_key"] = key_val
        if key_val:
            AI_CONFIG["preferred_provider"] = "GROQ"
    elif "GEMINI" in provider_upper:
        AI_CONFIG["gemini_api_key"] = key_val
        if key_val:
            AI_CONFIG["preferred_provider"] = "GEMINI"
    elif "OPENAI" in provider_upper:
        AI_CONFIG["openai_api_key"] = key_val
        if key_val:
            AI_CONFIG["preferred_provider"] = "OPENAI"


def get_ai_config() -> Dict[str, Any]:
    """Returns AI configuration status (UI-safe)."""
    cfg = unified_llm.get_ai_config()
    st = unified_llm.get_ai_status()
    return {
        "groq_configured": cfg.get("groq_configured", False),
        "model": cfg.get("groq_model", "llama-3.3-70b-versatile"),
        "fallback": "Deterministic Regex & Layout Engine",
        "gemini_configured": cfg.get("gemini_configured", False),
        "openai_configured": bool(AI_CONFIG.get("openai_api_key")),
        "preferred_provider": "GEMINI" if cfg.get("gemini_configured") else ("GROQ" if cfg.get("groq_configured") else "NONE"),
        "enabled": st.get("enabled", True),
        "mode": st.get("mode", "rules"),
    }


def call_groq_llm(
    prompt: str,
    system_prompt: str = "You are an expert financial Accounts Payable audit AI. Respond strictly in valid JSON.",
) -> Optional[Dict[str, Any]]:
    """Calls unified LLM client with fallback to rules."""
    return unified_llm.call_llm_json(system=system_prompt, user=prompt, temperature=0.1)



def compute_sha256(filepath: str) -> str:
    """Computes SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Visual Document Preview Helpers
# ---------------------------------------------------------------------------

def _get_font(size: int = 16, bold: bool = False):
    """Safely loads Arial or Segoe UI font or default."""
    font_names = ["arialbd.ttf" if bold else "arial.ttf", "segoeuib.ttf" if bold else "segoeui.ttf"]
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def render_file_preview_png(filepath: str) -> bytes:
    """
    Renders a crisp PNG preview of any document format:
    - PDF: Page 1 rendered at 150 DPI via PyMuPDF.
    - PNG/JPG/JPEG: Image loaded and returned as PNG bytes.
    - XLSX: Clean spreadsheet grid card rendered with openpyxl + PIL.
    - DOCX: Clean formatted document card rendered with python-docx + PIL.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if not path.exists():
        # Generate missing file card
        return _render_placeholder_card("File Not Found", path.name, (220, 53, 69))

    if ext == ".pdf":
        try:
            doc = pymupdf.open(filepath)
            if len(doc) > 0:
                page = doc.load_page(0)
                pix = page.get_pixmap(dpi=150)
                return pix.tobytes("png")
            else:
                return _render_placeholder_card("Empty PDF Document", path.name, (108, 117, 125))
        except Exception as e:
            return _render_placeholder_card(f"PDF Render Error: {e}", path.name, (220, 53, 69))

    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
        try:
            with Image.open(filepath) as img:
                out = io.BytesIO()
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(out, format="PNG")
                return out.getvalue()
        except Exception as e:
            return _render_placeholder_card(f"Image Render Error: {e}", path.name, (220, 53, 69))

    elif ext == ".xlsx":
        try:
            return _render_xlsx_card(filepath)
        except Exception as e:
            return _render_placeholder_card(f"Excel Preview Error: {e}", path.name, (16, 124, 65))

    elif ext == ".docx":
        try:
            return _render_docx_card(filepath)
        except Exception as e:
            return _render_placeholder_card(f"Word Preview Error: {e}", path.name, (24, 90, 189))

    else:
        return _render_placeholder_card(f"Preview unavailable for {ext}", path.name, (108, 117, 125))


def _render_placeholder_card(title: str, subtitle: str, color_rgb: Tuple[int, int, int]) -> bytes:
    """Generates a neat fallback preview card."""
    width, height = 800, 600
    img = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle([0, 0, width, 80], fill=color_rgb)
    title_font = _get_font(24, bold=True)
    sub_font = _get_font(16, bold=False)

    draw.text((30, 26), "ClearPay Document Viewer", fill=(255, 255, 255), font=title_font)
    draw.text((width // 2, 280), title, fill=(33, 37, 41), font=title_font, anchor="mm")
    draw.text((width // 2, 320), subtitle, fill=(108, 117, 125), font=sub_font, anchor="mm")

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _render_xlsx_card(filepath: str) -> bytes:
    """Renders a spreadsheet visual preview table."""
    wb = openpyxl.load_workbook(filepath, data_only=True)
    sheet = wb.active
    rows = list(sheet.iter_rows(values_only=True))

    width, height = 1000, 750
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Excel Green Header
    excel_green = (16, 124, 65)
    draw.rectangle([0, 0, width, 70], fill=excel_green)

    title_font = _get_font(20, bold=True)
    body_font = _get_font(13, bold=False)
    header_cell_font = _get_font(13, bold=True)
    meta_font = _get_font(12, bold=False)

    draw.text((25, 22), f"Excel Spreadsheet: {Path(filepath).name}", fill=(255, 255, 255), font=title_font)
    draw.text((width - 180, 26), f"Sheet: {sheet.title}", fill=(230, 245, 235), font=meta_font)

    # Column layout
    start_y = 90
    max_cols = min(6, sheet.max_column if sheet.max_column else 4)
    col_width = (width - 40) // max_cols

    # Draw grid
    curr_y = start_y
    for r_idx, row in enumerate(rows[:18]):
        bg_color = (235, 245, 238) if r_idx == 0 else ((248, 249, 250) if r_idx % 2 == 1 else (255, 255, 255))
        draw.rectangle([20, curr_y, width - 20, curr_y + 32], fill=bg_color, outline=(220, 224, 230))

        for c_idx in range(max_cols):
            val = str(row[c_idx]) if c_idx < len(row) and row[c_idx] is not None else ""
            if len(val) > 28:
                val = val[:26] + "..."
            cell_x = 25 + c_idx * col_width
            f = header_cell_font if r_idx == 0 else body_font
            text_color = (16, 124, 65) if r_idx == 0 else (33, 37, 41)
            draw.text((cell_x, curr_y + 7), val, fill=text_color, font=f)

        curr_y += 32

    # Footer banner
    draw.rectangle([0, height - 35, width, height], fill=(240, 243, 246))
    draw.text((25, height - 25), "ClearPay AP Spreadsheet Engine • Native Cell Extractor", fill=(108, 117, 125), font=meta_font)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _render_docx_card(filepath: str) -> bytes:
    """Renders a Word document visual preview."""
    doc = docx.Document(filepath)

    width, height = 900, 1150
    img = Image.new("RGB", (width, height), (250, 250, 252))
    draw = ImageDraw.Draw(img)

    # White page area
    draw.rectangle([40, 40, width - 40, height - 40], fill=(255, 255, 255), outline=(218, 224, 233), width=2)

    # Word Blue Top Banner
    word_blue = (24, 90, 189)
    draw.rectangle([40, 40, width - 40, 110], fill=word_blue)

    title_font = _get_font(20, bold=True)
    h2_font = _get_font(15, bold=True)
    body_font = _get_font(13, bold=False)
    meta_font = _get_font(12, bold=False)

    draw.text((65, 62), f"Word Document Invoice: {Path(filepath).name}", fill=(255, 255, 255), font=title_font)

    curr_y = 135
    # Render paragraphs
    for p in doc.paragraphs:
        txt = p.text.strip()
        if not txt:
            curr_y += 10
            continue
        is_heading = len(txt) < 50 and any(keyword in txt.lower() for keyword in ["invoice", "bill to", "vendor", "total", "summary", "draft"])
        f = h2_font if is_heading else body_font
        color = (24, 90, 189) if is_heading else (33, 37, 41)
        draw.text((65, curr_y), txt[:85], fill=color, font=f)
        curr_y += 24
        if curr_y > 450:
            break

    # Render tables if present
    for table in doc.tables:
        if curr_y > height - 200:
            break
        curr_y += 15
        for r_idx, row in enumerate(table.rows[:12]):
            bg_color = (235, 240, 250) if r_idx == 0 else ((248, 249, 252) if r_idx % 2 == 1 else (255, 255, 255))
            draw.rectangle([65, curr_y, width - 65, curr_y + 28], fill=bg_color, outline=(220, 225, 235))
            col_w = (width - 130) // max(1, len(row.cells))
            for c_idx, cell in enumerate(row.cells):
                txt = cell.text.strip()
                if len(txt) > 24:
                    txt = txt[:22] + "..."
                f = h2_font if r_idx == 0 else body_font
                draw.text((70 + c_idx * col_w, curr_y + 6), txt, fill=(33, 37, 41), font=f)
            curr_y += 28

    # Bottom status badge
    draw.rectangle([40, height - 80, width - 40, height - 40], fill=(245, 247, 250))
    draw.text((65, height - 65), "ClearPay AP DOCX Parser • Visual Layout Preview", fill=(108, 117, 125), font=meta_font)

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Number & Date Normalization Parsers
# ---------------------------------------------------------------------------

def parse_amount(text: Any) -> Optional[float]:
    """
    Parses currency strings across global locales:
    - European: '5.900,00 €' -> 5900.0, '1.121,00' -> 1121.0
    - Indian: '₹2,36,000.00' -> 236000.0, '2,00,000' -> 200000.0
    - US/Standard: '$12,000.00' -> 12000.0, '1,950.00' -> 1950.0
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)

    s = str(text).strip()
    # Strip currency symbols and whitespace
    s = re.sub(r"[₹€$£S\sA-Za-z]", "", s)
    if not s:
        return None

    # Handle negative / brackets
    is_neg = False
    if s.startswith("(") and s.endswith(")"):
        is_neg = True
        s = s[1:-1].strip()
    elif s.startswith("-"):
        is_neg = True
        s = s[1:].strip()

    # Detect European formatting: e.g. 5.900,00 or 1.234.567,89
    # If both dot and comma are present:
    if "." in s and "," in s:
        last_dot = s.rfind(".")
        last_comma = s.rfind(",")
        if last_comma > last_dot:
            # European: dots are thousands, comma is decimal
            s = s.replace(".", "").replace(",", ".")
        else:
            # US/Indian: commas are thousands, dot is decimal
            s = s.replace(",", "")
    elif "," in s:
        # Only commas: could be European decimal (e.g. 5900,00) or thousands (e.g. 5,000)
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            # e.g. 5900,00 -> 5900.00
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        # Only dots: could be European thousands e.g. 5.900
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and int(parts[0]) > 0:
            # e.g. 5.000 or 10.000
            s = s.replace(".", "")
        # else normal decimal e.g. 5900.00

    try:
        val = float(s)
        return -val if is_neg else val
    except ValueError:
        return None


def parse_date(text: Any) -> Optional[str]:
    """
    Normalizes dates into ISO format YYYY-MM-DD:
    - European: '28.10.2026' -> '2026-10-28'
    - US: '10/28/2026' -> '2026-10-28'
    - ISO: '2026-10-28' -> '2026-10-28'
    - Natural: '28 October 2026' or 'Oct 28, 2026'
    """
    if not text:
        return None
    s = str(text).strip()

    # Match YYYY-MM-DD
    m_iso = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m_iso:
        y, m, d = m_iso.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Match DD.MM.YYYY (European) or DD-MM-YYYY
    m_eur = re.search(r"(\d{1,2})[.-](\d{1,2})[.-](\d{4})", s)
    if m_eur:
        d, m, y = m_eur.groups()
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Match MM/DD/YYYY
    m_us = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m_us:
        m, d, y = m_us.groups()
        # Disambiguate if month > 12: must be DD/MM/YYYY
        if int(m) > 12:
            return f"{int(y):04d}-{int(d):02d}-{int(m):02d}"
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    # Try dateutil or strptime formats
    date_formats = [
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
        "%d-%b-%Y", "%d-%b-%y", "%d/%b/%Y"
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


# ---------------------------------------------------------------------------
# Multi-Format Raw Ingestion
# ---------------------------------------------------------------------------

def ingest_raw_document(filepath: str) -> Tuple[str, str, Dict[str, Any]]:
    """
    Reads the document via layered OCR/text reader and returns (file_format, raw_text, structured_metadata).
    file_format: 'PDF_TEXT', 'PDF_SCANNED', 'IMAGE', 'XLSX', 'DOCX'
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    raw_text, ocr_method, ocr_conf, meta = read_document(filepath)
    meta["ocr_method"] = ocr_method
    meta["ocr_confidence"] = ocr_conf

    if ext == ".pdf":
        file_format = "PDF_SCANNED" if ocr_method in ["ocr", "vision"] else "PDF_TEXT"
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"]:
        file_format = "IMAGE"
    elif ext == ".xlsx":
        file_format = "XLSX"
    elif ext == ".docx":
        file_format = "DOCX"
    else:
        file_format = "PDF_TEXT"

    return file_format, raw_text, meta



# ---------------------------------------------------------------------------
# High Precision Deterministic & Layout Extraction
# ---------------------------------------------------------------------------

def _extract_deterministic(
    filepath: str,
    file_format: str,
    raw_text: str,
    metadata: Dict[str, Any],
    source_type: str = "UPLOAD",
    email_meta: Optional[Dict[str, str]] = None,
) -> StandardInvoice:
    """
    High-precision deterministic extractor.
    Extracts vendor, invoice number, dates, PO references, currency,
    line items (both itemised and bundled), subtotals, tax, and totals.
    """
    fname = Path(filepath).name.lower()
    file_hash = compute_sha256(filepath)
    email_meta = email_meta or {}

    valid_sources = ["GMAIL", "OUTLOOK", "DRIVE", "SLACK", "WHATSAPP", "UPLOAD", "WEBHOOK", "SAMPLE"]
    safe_source = source_type if source_type in valid_sources else "UPLOAD"

    source_info = SourceInfo(
        source_type=safe_source,
        filename=Path(filepath).name,
        file_format=file_format,
        file_hash=file_hash,
        email_subject=email_meta.get("subject"),
        email_from=email_meta.get("from"),
        email_date=email_meta.get("date"),
        extraction_engine="Deterministic Regex & Layout Parser",
    )

    # Initialize ExtractedField placeholders
    vendor_name = ExtractedField(confidence=0.98)
    vendor_tax_id = ExtractedField(confidence=0.98)
    vendor_country = ExtractedField(confidence=0.98)
    vendor_bank_account = ExtractedField(confidence=0.98)
    vendor_bank_code = ExtractedField(confidence=0.98)
    invoice_number = ExtractedField(confidence=0.99)
    invoice_date = ExtractedField(confidence=0.98)
    due_date = ExtractedField(confidence=0.95)
    po_reference = ExtractedField(confidence=0.98)
    currency = ExtractedField(confidence=0.99)
    subtotal = ExtractedField(confidence=0.98)
    tax_amount = ExtractedField(confidence=0.98)
    total = ExtractedField(confidence=0.99)
    tax_label = "Tax"
    line_items: List[StandardLineItem] = []

    text = raw_text

    # General Arbitrary Invoices: Layout + Regex Parsing
    # -------------------------------------------------------------------
    # 1. Extract Vendor Name: Check Master Registry FIRST (accent-insensitive)
    try:
        from backend.engine import load_vendors
        from backend.llm_review import _strip_accents
        clean_text_norm = _strip_accents(text).lower()

        # Check by Tax ID first if present
        for v_rec in load_vendors():
            v_tax = (v_rec.get("tax_id") or "").strip().upper()
            if v_tax and len(v_tax) >= 5 and v_tax in text.upper():
                v_name = v_rec.get("legal_name", "").strip()
                vendor_name = ExtractedField(value=v_name, raw=v_name, confidence=0.98, source_text=v_tax)
                vendor_country = ExtractedField(value=v_rec.get("country", "IN"), raw=v_rec.get("country", "IN"), confidence=0.98)
                vendor_tax_id = ExtractedField(value=v_tax, raw=v_tax, confidence=0.98)
                break

        if not vendor_name.value:
            for v_rec in load_vendors():
                v_name = v_rec.get("legal_name", "").strip()
                v_name_clean = _strip_accents(v_name).lower()
                if v_name_clean and v_name_clean in clean_text_norm:
                    vendor_name = ExtractedField(value=v_name, raw=v_name, confidence=0.98, source_text=v_name)
                    vendor_country = ExtractedField(value=v_rec.get("country", "IN"), raw=v_rec.get("country", "IN"), confidence=0.98)
                    if v_rec.get("tax_id"):
                        vendor_tax_id = ExtractedField(value=v_rec["tax_id"], raw=v_rec["tax_id"], confidence=0.98)
                    break
                for alias in v_rec.get("aliases", "").split("|"):
                    alias = alias.strip()
                    alias_clean = _strip_accents(alias).lower()
                    if alias_clean and len(alias_clean) >= 3 and alias_clean in clean_text_norm:
                        vendor_name = ExtractedField(value=v_name, raw=alias, confidence=0.98, source_text=alias)
                        vendor_country = ExtractedField(value=v_rec.get("country", "IN"), raw=v_rec.get("country", "IN"), confidence=0.98)
                        if v_rec.get("tax_id"):
                            vendor_tax_id = ExtractedField(value=v_rec["tax_id"], raw=v_rec["tax_id"], confidence=0.98)
                        break
                if vendor_name.value:
                    break
    except Exception:
        pass

    if not vendor_name.value:
        v_match = re.search(r"(?:ISSUED\s*BY(?:\s*\([^)]*\))?|Vendor|From|Supplier|Company|Billed By)[:\s]*\n?([^\n\r,()]+)", text, re.I)
        if v_match:
            v_val = v_match.group(1).strip()
            if v_val and v_val not in [")", ":", ""]:
                vendor_name = ExtractedField(value=v_val, raw=v_val, confidence=0.90, source_text=v_match.group(0))

    # 2. Extract Tax ID / GSTIN
    gstin_m = re.search(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1})\b", text)
    if gstin_m:
        vendor_tax_id = ExtractedField(value=gstin_m.group(1), raw=gstin_m.group(1), confidence=0.98, source_text=gstin_m.group(0))
        vendor_country = ExtractedField(value="IN", raw="India", confidence=0.98)
    else:
        de_vat = re.search(r"\b(DE\d{9})\b", text)
        if de_vat:
            vendor_tax_id = ExtractedField(value=de_vat.group(1), raw=de_vat.group(1), confidence=0.98, source_text=de_vat.group(0))
            vendor_country = ExtractedField(value="DE", raw="Germany", confidence=0.98)
        else:
            us_ein = re.search(r"\b(\d{2}-\d{7})\b", text)
            if us_ein:
                vendor_tax_id = ExtractedField(value=us_ein.group(1), raw=us_ein.group(1), confidence=0.98, source_text=us_ein.group(0))
                vendor_country = ExtractedField(value="US", raw="USA", confidence=0.98)
            else:
                sg_uen = re.search(r"\b(\d{9}[A-Z])\b", text)
                if sg_uen:
                    vendor_tax_id = ExtractedField(value=sg_uen.group(1), raw=sg_uen.group(1), confidence=0.98, source_text=sg_uen.group(0))
                    vendor_country = ExtractedField(value="SG", raw="Singapore", confidence=0.98)

    # 3. Extract Bank Account (Stop at line break so IFSC code on next line is not joined)
    bank_m = re.search(r"(?:Bank\s*Account|A/C\s*(?:No\.?|#)?|Account\s*#|IBAN)[^\n\r\w:]*[:\s]*([A-Z0-9 ]{6,34})", text, re.I)
    if bank_m:
        b_val = re.sub(r"\s+", "", bank_m.group(1).strip())
        b_val = re.sub(r"(?:IFSC|SWIFT|BIC).*", "", b_val, flags=re.I)
        vendor_bank_account = ExtractedField(value=b_val, raw=b_val, confidence=0.95, source_text=bank_m.group(0))

    # 4. Extract Bank Code
    code_m = re.search(r"\b(?:IFSC|BIC|SWIFT|Routing\s*#?)[:\s]*([A-Z0-9]+)\b", text, re.I)
    if code_m:
        vendor_bank_code = ExtractedField(value=code_m.group(1).strip(), raw=code_m.group(1).strip(), confidence=0.95, source_text=code_m.group(0))

    # 5. Extract Invoice Number (Never capture 'OICE' from 'TAX INVOICE')
    inv_m = re.search(r"\b(INV[-_/][A-Z0-9\-_/]+)\b", text, re.I)
    if not inv_m:
        inv_m = re.search(r"\b(QTE[-_/][A-Z0-9\-_/]+)\b", text, re.I)
    if not inv_m:
        inv_m = re.search(r"\b(RE[-_/][A-Z0-9\-_/]+)\b", text, re.I)
    if not inv_m:
        inv_m = re.search(r"\b(?:Invoice\s*(?:No\.?|Number|#)|Inv\s*#?|Bill\s*(?:No\.?|#)|Rechnung\s*(?:Nr)?|Rechnungs-Nr\.?)[:\s|]+([A-Z0-9\-_/]+)", text, re.I)
    if inv_m:
        raw_inv = inv_m.group(1).strip()
        invalid_inv_tokens = ["INVOICE", "OICE", "TAX", "TO", "RECIPIENT", "TBD", "BLANK", "NONE", "NULL", "DRAFT", "UNASSIGNED", "ASSIGNMENT", "PENDING", "COPY", "VERIFICATION"]
        if raw_inv.upper() not in invalid_inv_tokens and re.search(r"\d", raw_inv):
            invoice_number = ExtractedField(value=raw_inv, raw=raw_inv, confidence=0.96, source_text=inv_m.group(0))




    # 6. Extract Dates
    date_m = re.search(r"\b(?:Invoice\s*Date|Date|Datum)[:\s]*([^\n\r]+)", text, re.I)
    if date_m:
        d_parsed = parse_date(date_m.group(1).strip())
        if d_parsed:
            invoice_date = ExtractedField(value=d_parsed, raw=date_m.group(1).strip(), confidence=0.96, source_text=date_m.group(0))

    due_m = re.search(r"\b(?:Due\s*Date|Payment\s*Due|Fälligkeit)[:\s]*([^\n\r]+)", text, re.I)
    if due_m:
        due_parsed = parse_date(due_m.group(1).strip())
        if due_parsed:
            due_date = ExtractedField(value=due_parsed, raw=due_m.group(1).strip(), confidence=0.92, source_text=due_m.group(0))

    # 7. Extract PO / Quotation Reference
    po_m = re.search(r"\b(QTE[-_/][A-Z0-9\-_/]+)\b", text, re.I)
    if not po_m:
        po_m = re.search(r"\b(PO[-_/][A-Z0-9\-_/]+)\b", text, re.I)
    if not po_m:
        po_m = re.search(r"\b(?:PO\s*(?:No\.?|Number|#|Ref)?|Purchase\s*Order|Quotation\s*(?:Ref|No\.?|#)?|Quote\s*(?:Ref|#)?)[:\s]+([A-Z0-9\-_/]+)", text, re.I)
    if po_m:
        po_val = po_m.group(1).strip()
        po_reference = ExtractedField(value=po_val, raw=po_val, confidence=0.96, source_text=po_m.group(0))

    # 8. Extract Currency
    if "₹" in text or "INR" in text:
        currency = ExtractedField(value="INR", raw="INR", confidence=0.98)
    elif "€" in text or "EUR" in text:
        currency = ExtractedField(value="EUR", raw="EUR", confidence=0.98)
    elif "SGD" in text or "S$" in text:
        currency = ExtractedField(value="SGD", raw="SGD", confidence=0.98)
    elif "$" in text or "USD" in text:
        currency = ExtractedField(value="USD" if "USD" in text else "$", raw="$", confidence=0.92)

    # 9. Extract Grand Total, Subtotal, Tax (handles European and global number formats)
    num_pattern = re.compile(r"([\d]{1,3}(?:[\.,]\d{2,3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})?)")
    lines_list = [l.strip() for l in text.splitlines() if l.strip()]

    # Extract declared tax rate if present
    doc_tax_rate = None
    rate_m = re.search(r"(?:GST|VAT|Tax|MwSt|Umsatzsteuer)[^\n\r\d]*\(?(\d+(?:\.\d+)?)\s*%\)?", text, re.I)
    if rate_m:
        doc_tax_rate = float(rate_m.group(1)) / 100.0

    parsed_tot_val = None
    parsed_sub_val = None
    parsed_tax_val = None

    for i, line in enumerate(lines_list):
        if any(k in line.lower() for k in ['unit price', 'description of', 'quantity', 'item code', 'line #', 'artikel-nr']):
            continue

        cells = [c.strip() for c in line.split('|')]
        for c_idx, cell in enumerate(cells):
            clean_c = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', cell, flags=re.I)
            clean_c = re.sub(r'\d+(?:\.\d+)?\s*%', '', clean_c)


            # Total
            if re.search(r'\b(?:GRAND\s*TOTAL|Total\s*Invoice\s*(?:Amount|Value)|Invoice\s*Total|Total\s*Amount\s*(?:Due)?|Gesamtbetrag)\b', cell, re.I):
                m_nums = num_pattern.findall(clean_c)
                vals = [parse_amount(n) for n in m_nums if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                if vals:
                    parsed_tot_val = vals[0]
                elif c_idx + 1 < len(cells):
                    next_c = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', cells[c_idx+1], flags=re.I)
                    next_m = num_pattern.findall(next_c)
                    vals = [parse_amount(n) for n in next_m if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                    if vals:
                        parsed_tot_val = vals[0]
                elif i + 1 < len(lines_list):
                    next_l = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', lines_list[i+1], flags=re.I)
                    next_m = num_pattern.findall(next_l)
                    vals = [parse_amount(n) for n in next_m if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                    if vals:
                        parsed_tot_val = vals[0]

            # Subtotal
            if re.search(r'\b(?:Subtotal\s*\(Taxable\s*Value\)|Subtotal|Sub\s*Total|Net\s*Amount|Nettobetrag|Zwischensumme|Base\s*Value)\b', cell, re.I):
                m_nums = num_pattern.findall(clean_c)
                vals = [parse_amount(n) for n in m_nums if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                if vals:
                    parsed_sub_val = vals[0]
                elif c_idx + 1 < len(cells):
                    next_c = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', cells[c_idx+1], flags=re.I)
                    next_m = num_pattern.findall(next_c)
                    vals = [parse_amount(n) for n in next_m if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                    if vals:
                        parsed_sub_val = vals[0]
                elif i + 1 < len(lines_list):
                    next_l = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', lines_list[i+1], flags=re.I)
                    next_m = num_pattern.findall(next_l)
                    vals = [parse_amount(n) for n in next_m if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                    if vals:
                        parsed_sub_val = vals[0]

            # Tax
            if re.search(r'\b(?:Taxes?\s*/\s*GST|Tax\s*\(GST\s*/\s*VAT\)|Total\s*Tax|Tax\s*Amount|VAT\s*Amount|Umsatzsteuer|MwSt|Embedded\s*IGST|IGST|CGST|SGST)\b', cell, re.I):
                m_nums = num_pattern.findall(clean_c)
                vals = [parse_amount(n) for n in m_nums if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                if vals:
                    parsed_tax_val = vals[0]
                elif c_idx + 1 < len(cells):
                    next_c = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', cells[c_idx+1], flags=re.I)
                    next_m = num_pattern.findall(next_c)
                    vals = [parse_amount(n) for n in next_m if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                    if vals:
                        parsed_tax_val = vals[0]
                elif i + 1 < len(lines_list):
                    if not re.search(r'\b(?:Bank|IBAN|SWIFT|Gesamtbetrag|Total|BANKVERBINDUNG)\b', lines_list[i+1], re.I):
                        next_l = re.sub(r'\b(?:IBAN|SWIFT|BIC|Account\s*No|Bank|BANKVERBINDUNG)\b.*', '', lines_list[i+1], flags=re.I)
                        next_m = num_pattern.findall(next_l)
                        vals = [parse_amount(n) for n in next_m if len(re.sub(r'\D', '', n)) <= 12 and parse_amount(n) is not None]
                        if vals:
                            parsed_tax_val = vals[0]


    # Regex fallbacks if line-by-line missed
    if parsed_tot_val is None:
        tot_m = re.search(r"(?:GRAND\s*TOTAL|Total\s*Invoice\s*(?:Amount|Value)|Invoice\s*Total|Total\s*Amount\s*(?:Due)?|Gesamtbetrag(?:\s*\([^)]*\))?)[\s:\(\)EUR$₹SGD]*\n?[^\d\n\r]*([\d]{1,3}(?:[\.,]\d{2,3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})?)", text, re.I)
        if tot_m:
            parsed_tot_val = parse_amount(tot_m.group(1))

    if parsed_sub_val is None:
        sub_m = re.search(r"(?:Subtotal\s*\(Taxable\s*Value\)|Subtotal|Sub\s*Total|Net\s*Amount|Nettobetrag|Zwischensumme(?:\s*\([^)]*\))?|Base\s*Value)[\s:\(\)EUR$₹SGD]*\n?[^\d\n\r]*([\d]{1,3}(?:[\.,]\d{2,3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})?)", text, re.I)
        if sub_m:
            parsed_sub_val = parse_amount(sub_m.group(1))

    if parsed_tax_val is None:
        clean_text_no_pct = re.sub(r"\d+(?:\.\d+)?\s*%", "", text)
        tax_m = re.search(r"(?:Taxes?\s*/\s*GST|Tax\s*\(GST\s*/\s*VAT\)|Total\s*Tax|Tax\s*Amount|VAT\s*Amount|Umsatzsteuer|MwSt|Embedded\s*IGST|IGST|CGST|SGST)[\s:\(\)EUR$₹SGD]*\n?[^\d\n\r]*([\d]{1,3}(?:[\.,]\d{2,3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})?)", clean_text_no_pct, re.I)
        if tax_m:
            parsed_tax_val = parse_amount(tax_m.group(1))


    # Derive tax mathematically only if missing from document
    if parsed_tot_val is not None and parsed_sub_val is not None and parsed_tax_val is None:
        calc_tax = round(parsed_tot_val - parsed_sub_val, 2)
        if calc_tax >= 0:
            parsed_tax_val = calc_tax


    if parsed_tot_val is not None:
        total = ExtractedField(value=parsed_tot_val, raw=str(parsed_tot_val), confidence=0.96)
    if parsed_sub_val is not None:
        subtotal = ExtractedField(value=parsed_sub_val, raw=str(parsed_sub_val), confidence=0.95)
    if parsed_tax_val is not None:
        tax_amount = ExtractedField(value=parsed_tax_val, raw=str(parsed_tax_val), confidence=0.95)

    # Derive missing totals
    if total.value is not None and subtotal.value is None:
        if tax_amount.value is not None:
            subtotal = ExtractedField(value=round(total.value - tax_amount.value, 2), raw=str(round(total.value - tax_amount.value, 2)), confidence=0.88)
        else:
            subtotal = ExtractedField(value=total.value, raw=str(total.value), confidence=0.88)

    if total.value is not None and tax_amount.value is None:
        if subtotal.value is not None and subtotal.value < total.value:
            tax_amount = ExtractedField(value=round(total.value - subtotal.value, 2), raw=str(round(total.value - subtotal.value, 2)), confidence=0.88)
        else:
            tax_amount = ExtractedField(value=0.0, raw="0.00", confidence=0.85)

    if total.value is None and subtotal.value is not None:
        t_amt = tax_amount.value or 0.0
        total = ExtractedField(value=round(subtotal.value + t_amt, 2), raw=str(round(subtotal.value + t_amt, 2)), confidence=0.90)

    # Derive tax rate
    if doc_tax_rate is None:
        if tax_amount.value is not None and subtotal.value is not None and subtotal.value > 0:
            doc_tax_rate = round(tax_amount.value / subtotal.value, 2)
        else:
            doc_tax_rate = 0.0

    # 10. Extract Line Items
    # A: Pipe-separated spreadsheet format
    for l in lines_list:
        if "|" in l:
            parts = [p.strip() for p in l.split("|")]
            if len(parts) >= 6 and parts[0].isdigit():
                ln_no = int(parts[0])
                code = parts[1]
                desc = parts[2]
                qty = parse_amount(parts[3]) or 1.0
                rate = parse_amount(parts[4]) or 0.0
                amt = parse_amount(parts[5]) or 0.0
                line_items.append(
                    StandardLineItem(
                        line_no=ln_no,
                        item_code=code,
                        description=desc,
                        qty=qty,
                        unit_price=rate,
                        amount=amt,
                        tax_rate=doc_tax_rate,
                    )
                )

    # B: Tabular multi-line block
    if not line_items:
        tbl_pattern = re.compile(
            r"(\d{1,2})\n([A-Z0-9\-_]{3,25})\n([^\n]+)\n(\d+(?:\.\d+)?)\n[^\d\n\r]*([\d,]+(?:\.\d+)?)\n[^\d\n\r]*([\d,]+(?:\.\d+)?)"
        )
        for m in tbl_pattern.finditer(text):
            ln_no = int(m.group(1))
            code = m.group(2).strip()
            desc = m.group(3).strip()
            qty = float(m.group(4))
            rate = parse_amount(m.group(5)) or 0.0
            amt = parse_amount(m.group(6)) or 0.0
            line_items.append(
                StandardLineItem(
                    line_no=ln_no,
                    item_code=code,
                    description=desc,
                    qty=qty,
                    unit_price=rate,
                    amount=amt,
                    tax_rate=doc_tax_rate,
                )
            )

    # C: Horizontal row format (e.g. German invoices or standard tabular prints)
    if not line_items:
        horiz_pattern = re.compile(
            r"^\s*([A-Z0-9\-_]{2,20})\s+([A-Za-z0-9\s\-_,\(\)\.]+?)\s+(\d+(?:\.\d+)?)\s+([\d]{1,3}(?:[\.,]\d{2,3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})?)\s+([\d]{1,3}(?:[\.,]\d{2,3})*(?:[\.,]\d{2})|\d+(?:[\.,]\d{2})?)(?:\s*[A-Z]{3}|\s*€|\s*\$|\s*₹)?\s*$",
            re.M
        )
        for idx, m in enumerate(horiz_pattern.finditer(text)):
            c_val = m.group(1).strip()
            if c_val.upper() in ["TAX", "TOTAL", "SUBTOTAL", "BANK", "IBAN", "SWIFT", "INVOICE", "DATUM", "ACME"]:
                continue
            qty_val = float(m.group(3))
            rate_val = parse_amount(m.group(4)) or 0.0
            amt_val = parse_amount(m.group(5)) or 0.0
            line_items.append(
                StandardLineItem(
                    line_no=idx + 1,
                    item_code=c_val,
                    description=m.group(2).strip(),
                    qty=qty_val,
                    unit_price=rate_val,
                    amount=amt_val,
                    tax_rate=doc_tax_rate,
                )
            )

    # D: Match by known PO line item codes if lines still empty (e.g. noisy OCR scans)
    if not line_items and vendor_name.value:
        try:
            from backend.engine import load_po_lines, load_purchase_orders, load_vendors
            v_id = None
            for v_rec in load_vendors():
                if v_rec.get("legal_name") == vendor_name.value:
                    v_id = v_rec.get("vendor_id")
                    break
            if v_id:
                vendor_po_numbers = [p["po_number"] for p in load_purchase_orders() if p.get("vendor_id") == v_id]
                candidate_lines = [pl for pl in load_po_lines() if pl["po_number"] in vendor_po_numbers]
                for pl in candidate_lines:
                    c_code = pl["item_code"]
                    if c_code and c_code in text:
                        line_items.append(
                            StandardLineItem(
                                line_no=len(line_items) + 1,
                                item_code=c_code,
                                description=pl["description"],
                                qty=float(pl["qty"]),
                                unit_price=float(pl["unit_price"]),
                                amount=float(pl["amount"]),
                                tax_rate=float(pl.get("tax_rate", 0.0)),
                            )
                        )
        except Exception:
            pass

    # E: Fallback single line item if none parsed
    if not line_items and total.value is not None:
        line_items.append(
            StandardLineItem(
                line_no=1,
                item_code=None,
                description="General Invoice Line Item",
                qty=1.0,
                unit_price=subtotal.value or total.value,
                amount=subtotal.value or total.value,
                tax_rate=doc_tax_rate,
            )
        )

    # Reconcile line items with subtotal and tax if lines were parsed
    if line_items and total.value is not None:
        lines_sum = round(sum(l.amount for l in line_items), 2)
        if subtotal.value is None or abs(subtotal.value - lines_sum) > 1.0:
            if lines_sum <= total.value:
                subtotal = ExtractedField(value=lines_sum, raw=str(lines_sum), confidence=0.95)
                tax_amount = ExtractedField(value=round(total.value - lines_sum, 2), raw=str(round(total.value - lines_sum, 2)), confidence=0.95)
                if lines_sum > 0:
                    doc_tax_rate = round(tax_amount.value / lines_sum, 2)
                    for l in line_items:
                        l.tax_rate = doc_tax_rate




    return StandardInvoice(
        document_type="INVOICE",
        source_info=source_info,
        vendor_name=vendor_name,
        vendor_tax_id=vendor_tax_id,
        vendor_country=vendor_country,
        vendor_bank_account=vendor_bank_account,
        vendor_bank_code=vendor_bank_code,
        matched_vendor_id=None,
        invoice_number=invoice_number,
        normalized_invoice_number=None,
        invoice_date=invoice_date,
        due_date=due_date,
        po_reference=po_reference,
        inferred_po=False,
        currency=currency,
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax_amount,
        tax_label=tax_label,
        total=total,
        raw_text_preview=raw_text[:2000] if raw_text else f"Preview generated for {Path(filepath).name}",
    )


# ---------------------------------------------------------------------------
# AI LLM Extractor (Groq Llama-3.3-70B / Fallbacks)
# ---------------------------------------------------------------------------

def _extract_via_ai(filepath: str, file_format: str, raw_text: str) -> Optional[StandardInvoice]:
    """
    Attempts extraction via unified LLM client (Gemini -> Groq -> None).
    """
    from backend.llm import llm_available, call_llm_json

    if not llm_available() or not raw_text.strip():
        return None

    prompt = (
        "Extract all invoice fields strictly into JSON with keys:\n"
        "- vendor_name (string)\n"
        "- vendor_tax_id (string, e.g. GSTIN, VAT, or EIN)\n"
        "- vendor_country (2-letter ISO code e.g. IN, US)\n"
        "- vendor_bank_account (string)\n"
        "- vendor_bank_code (string, IFSC/SWIFT)\n"
        "- invoice_number (string)\n"
        "- invoice_date (string in YYYY-MM-DD format)\n"
        "- due_date (string in YYYY-MM-DD format)\n"
        "- po_reference (string)\n"
        "- currency (3-letter ISO code e.g. INR, USD, EUR)\n"
        "- subtotal (numeric float)\n"
        "- tax_amount (numeric float)\n"
        "- tax_label (string e.g. GST, VAT, Tax)\n"
        "- total (numeric float)\n"
        "- line_items (list of objects with: line_no, item_code, description, qty, unit_price, amount, tax_rate)\n"
        "- ai_summary (concise 2-sentence executive summary of the document)\n"
        "- ai_flaws (list of strings describing any flaws, missing fields, tax math issues, or risks in the document)\n\n"
        f"Document text:\n{raw_text[:4000]}"
    )
    data = call_llm_json(
        system="You are an expert financial Accounts Payable audit AI. Respond strictly in valid JSON.",
        user=prompt,
        temperature=0.0,
    )
    if data and isinstance(data, dict):
        engine_label = "AI Extraction Layer"
        return _dict_to_standard_invoice(data, filepath, file_format, raw_text, engine_label)

    return None


def _dict_to_standard_invoice(
    data: Dict[str, Any], filepath: str, file_format: str, raw_text: str, engine_name: str
) -> StandardInvoice:
    """Helper to convert LLM JSON output to StandardInvoice."""
    source_info = SourceInfo(
        source_type="UPLOAD",
        filename=Path(filepath).name,
        file_format=file_format,
        file_hash=compute_sha256(filepath),
        extraction_engine=f"Hybrid AI ({engine_name})",
    )

    def ef(key: str, conf: float = 0.98) -> ExtractedField:
        val = data.get(key)
        return ExtractedField(value=val, raw=str(val) if val is not None else None, confidence=conf)

    lines = []
    for item in data.get("line_items", []):
        lines.append(
            StandardLineItem(
                line_no=int(item.get("line_no", len(lines) + 1)),
                item_code=item.get("item_code"),
                description=str(item.get("description", "Line item")),
                qty=float(item.get("qty", 1.0)),
                unit_price=float(item.get("unit_price", 0.0)),
                amount=float(item.get("amount", 0.0)),
                tax_rate=float(item.get("tax_rate", 0.0)) if item.get("tax_rate") is not None else None,
            )
        )

    ai_sum = data.get("ai_summary")
    if ai_sum and not isinstance(ai_sum, str):
        ai_sum = str(ai_sum)

    ai_flws_raw = data.get("ai_flaws", [])
    ai_flws = []
    if isinstance(ai_flws_raw, list):
        ai_flws = [str(f).strip() for f in ai_flws_raw if str(f).strip()]
    elif isinstance(ai_flws_raw, str) and ai_flws_raw.strip():
        ai_flws = [re.sub(r"^[\-\*\d\.\s]+", "", l).strip() for l in re.split(r"[\n;]+", ai_flws_raw) if l.strip()]

    return StandardInvoice(
        document_type="INVOICE",
        source_info=source_info,
        vendor_name=ef("vendor_name"),
        vendor_tax_id=ef("vendor_tax_id"),
        vendor_country=ef("vendor_country"),
        vendor_bank_account=ef("vendor_bank_account"),
        vendor_bank_code=ef("vendor_bank_code"),
        invoice_number=ef("invoice_number", 0.99),
        invoice_date=ef("invoice_date"),
        due_date=ef("due_date"),
        po_reference=ef("po_reference"),
        currency=ef("currency"),
        line_items=lines,
        subtotal=ef("subtotal"),
        tax_amount=ef("tax_amount"),
        tax_label=str(data.get("tax_label", "Tax")),
        total=ef("total", 0.99),
        raw_text_preview=raw_text[:2000] if raw_text else "AI extracted text",
        ai_summary=ai_sum,
        ai_flaws=ai_flws,
    )


def _merge_invoices(det_inv: StandardInvoice, ai_inv: StandardInvoice) -> StandardInvoice:
    """Merges AI extraction into deterministic baseline, preserving deterministic fields if AI missed them."""
    def pick_field(ai_f: ExtractedField, det_f: ExtractedField) -> ExtractedField:
        if ai_f and ai_f.value is not None and str(ai_f.value).strip() != "":
            return ai_f
        return det_f

    det_inv.vendor_name = pick_field(ai_inv.vendor_name, det_inv.vendor_name)
    det_inv.vendor_tax_id = pick_field(ai_inv.vendor_tax_id, det_inv.vendor_tax_id)
    det_inv.vendor_country = pick_field(ai_inv.vendor_country, det_inv.vendor_country)
    det_inv.vendor_bank_account = pick_field(ai_inv.vendor_bank_account, det_inv.vendor_bank_account)
    det_inv.vendor_bank_code = pick_field(ai_inv.vendor_bank_code, det_inv.vendor_bank_code)
    det_inv.invoice_number = pick_field(ai_inv.invoice_number, det_inv.invoice_number)
    det_inv.invoice_date = pick_field(ai_inv.invoice_date, det_inv.invoice_date)
    det_inv.due_date = pick_field(ai_inv.due_date, det_inv.due_date)
    det_inv.po_reference = pick_field(ai_inv.po_reference, det_inv.po_reference)
    det_inv.currency = pick_field(ai_inv.currency, det_inv.currency)
    det_inv.subtotal = pick_field(ai_inv.subtotal, det_inv.subtotal)
    det_inv.tax_amount = pick_field(ai_inv.tax_amount, det_inv.tax_amount)
    det_inv.total = pick_field(ai_inv.total, det_inv.total)
    if ai_inv.line_items and len(ai_inv.line_items) > 0:
        det_inv.line_items = ai_inv.line_items
    if ai_inv.tax_label:
        det_inv.tax_label = ai_inv.tax_label
    if ai_inv.ai_summary:
        det_inv.ai_summary = ai_inv.ai_summary
    if ai_inv.ai_flaws:
        det_inv.ai_flaws = ai_inv.ai_flaws

    det_inv.source_info.extraction_engine = "Groq Llama-3.3-70B AI + Deterministic Fallback"
    return det_inv


# ---------------------------------------------------------------------------
# Main Extraction Entrypoint
# ---------------------------------------------------------------------------

def extract_standard_invoice(
    filepath: str,
    source_type: str = "UPLOAD",
    email_meta: Optional[Dict[str, str]] = None,
) -> StandardInvoice:
    """
    Main extraction pipeline:
    1. Ingests raw document and detects format (PDF_TEXT, PDF_SCANNED, IMAGE, XLSX, DOCX).
    2. Runs high-precision deterministic extraction as baseline det_inv.
    3. If raw_text is non-empty, calls Groq LLM in _extract_via_ai(filepath, file_format, raw_text).
    4. If Groq returns valid data, merges it with det_inv, setting
       extraction_engine = "Groq Llama-3.3-70B AI + Deterministic Fallback".
    5. If Groq fails or is unreachable, gracefully falls back to det_inv
       (extraction_engine = "Deterministic Engine (Fallback)").
    """
    file_format, raw_text, meta = ingest_raw_document(filepath)

    # Baseline deterministic parser is rock-solid and fast (<100ms)
    det_inv = _extract_deterministic(
        filepath=filepath,
        file_format=file_format,
        raw_text=raw_text,
        metadata=meta,
        source_type=source_type,
        email_meta=email_meta,
    )

    if raw_text and raw_text.strip():
        ai_res = _extract_via_ai(filepath, file_format, raw_text)
        if ai_res is not None:
            return _merge_invoices(det_inv, ai_res)

    det_inv.source_info.extraction_engine = "Deterministic Engine (Fallback)"
    return det_inv


# ---------------------------------------------------------------------------
# AI Executive Summary & Risk Flaws Generator (Groq LLM + Fallback)
# ---------------------------------------------------------------------------

def generate_document_summary_and_flaws(
    std_inv: StandardInvoice,
    expected_quotation: Optional[Any] = None,
    reason_codes: Optional[List[str]] = None,
    doc_type: str = "INVOICE",
) -> Tuple[str, List[str], str]:
    """
    Calls Groq LLM with extracted fields, line items, quotation comparison, and reason codes.
    Returns: (ai_summary, ai_flaws, brain_used)
    Falls back gracefully to comprehensive deterministic rules if LLM call is unavailable.
    """
    reason_codes = reason_codes or []
    v_name = str(std_inv.vendor_name.value or "Vendor")
    inv_no = str(std_inv.invoice_number.value or "N/A")
    inv_date = str(std_inv.invoice_date.value or "N/A")
    due_date = str(std_inv.due_date.value or "N/A")
    curr = str(std_inv.currency.value or "INR")
    total_val = float(std_inv.total.value or 0.0)
    subtotal_val = float(std_inv.subtotal.value or 0.0)
    tax_val = float(std_inv.tax_amount.value or 0.0)
    items_cnt = len(std_inv.line_items)
    po_ref = str(std_inv.po_reference.value or "None")

    q_info = "None"
    if expected_quotation:
        q_status = getattr(expected_quotation, "match_status", "UNKNOWN")
        q_num = getattr(expected_quotation, "quotation_number", "N/A")
        q_total = getattr(expected_quotation, "total", 0.0)
        q_discrepancies = getattr(expected_quotation, "discrepancies", [])
        q_info = f"Status: {q_status}, Quotation#: {q_num}, Total: {q_total}, Discrepancies: {q_discrepancies}"

    prompt = (
        f"You are evaluating a financial {doc_type}.\n"
        f"Document details:\n"
        f"- Vendor: {v_name}\n"
        f"- Document Number: {inv_no}\n"
        f"- Issue Date: {inv_date}\n"
        f"- Due Date: {due_date}\n"
        f"- Currency: {curr}\n"
        f"- Subtotal: {subtotal_val}\n"
        f"- Tax Amount: {tax_val}\n"
        f"- Total Amount: {total_val}\n"
        f"- Line Items Count: {items_cnt}\n"
        f"- Purchase Order Ref: {po_ref}\n"
        f"- Linked Expected Quotation / Bill: {q_info}\n"
        f"- Rule Engine Flag Codes: {reason_codes}\n\n"
        f"Instructions:\n"
        f"Generate a JSON object with strictly two keys:\n"
        f"1. 'ai_summary': A crisp 2-3 sentence executive audit summary of this document (vendor, total, scope of items, billing terms, match status). IMPORTANT: Do NOT mention any AI model names, LLM names, or technology providers (such as Groq, Llama, OpenAI, ChatGPT, Claude, etc.). Write purely as an objective AP financial controller.\n"
        f"2. 'ai_flaws': A JSON list of concise strings detailing all flaws, missing fields (e.g. tax id, due date, bank info), price/qty variances against quotation, tax math errors, or fraud alerts. If completely clean and valid, return an empty list []. Do NOT mention any AI model or technology names."
    )

    llm_res = call_groq_llm(prompt)
    if llm_res and isinstance(llm_res, dict):
        summary = llm_res.get("ai_summary")
        flaws = llm_res.get("ai_flaws")
        model_name = llm_res.get("_llm_model_used", "Llama-3.3-70B")
        brain_used = f"Groq {model_name}"

        flaws_list = []
        if isinstance(flaws, list):
            flaws_list = [str(f).strip() for f in flaws if str(f).strip()]
        elif isinstance(flaws, str) and flaws.strip():
            lines = re.split(r"[\n;]+", flaws.strip())
            flaws_list = [re.sub(r"^[\-\*\d\.\s]+", "", l).strip() for l in lines if l.strip()]

        if summary and isinstance(summary, str) and summary.strip():
            # Strip out any model jargon from summary
            clean_summary = summary.strip()
            clean_summary = re.sub(r"\bGroq\s+(?:Llama(?:-[0-9\.]+[a-zA-Z\-]*)?|[a-zA-Z0-9\.\-]+)\b", "", clean_summary, flags=re.IGNORECASE)
            clean_summary = re.sub(r"\bLlama(?:-[0-9\.]+[a-zA-Z\-]*)?\b", "", clean_summary, flags=re.IGNORECASE)
            clean_summary = re.sub(r"\bGroq\b", "", clean_summary, flags=re.IGNORECASE)
            clean_summary = re.sub(r"\b(?:OpenAI|ChatGPT|GPT-[0-9a-zA-Z\.]+|Claude|Gemini)\b", "", clean_summary, flags=re.IGNORECASE)
            clean_summary = re.sub(r"\s{2,}", " ", clean_summary).strip()
            return (clean_summary, flaws_list, brain_used)

    # -------------------------------------------------------------
    # Deterministic Fallback Logic
    # -------------------------------------------------------------
    brain_used = "Deterministic Fallback"
    flaws_list = []

    code_descriptions = {
        "PRICE_VARIANCE_WARNING": "Unit price on invoice exceeds quotation/PO approved rate.",
        "EXACT_DUPLICATE_BLOCK": "Duplicate invoice detected matching prior submitted run.",
        "BANK_ACCOUNT_MISMATCH": "Bank account on invoice does not match master vendor record.",
        "TAX_MATH_MISMATCH": "Calculated tax does not match stated subtotal and tax percentage.",
        "LINE_ITEM_QTY_OVERAGE": "Invoiced item quantity exceeds purchase order authorized quantity.",
        "UNAUTHORIZED_VENDOR": "Vendor is not present in approved ERP vendor master list.",
        "PO_CONSUMPTION_EXCEEDED": "Invoice total exceeds remaining balance of linked Purchase Order.",
        "LINE_ITEM_UNORDERED": "Invoice contains items not found in linked quotation or PO.",
        "SCANNED_DOCUMENT": "Scanned raster document; optical character recognition applied.",
    }
    for code in reason_codes:
        if code in code_descriptions:
            flaws_list.append(code_descriptions[code])

    if not std_inv.invoice_number or not std_inv.invoice_number.value:
        flaws_list.append("Invoice number is missing or illegible.")
    if not std_inv.vendor_tax_id or not std_inv.vendor_tax_id.value:
        flaws_list.append("Vendor Tax/GST identification number is missing.")
    if not std_inv.due_date or not std_inv.due_date.value:
        flaws_list.append("Payment due date is missing from document.")
    if not std_inv.vendor_bank_account or not std_inv.vendor_bank_account.value:
        flaws_list.append("Vendor bank account details are missing.")
    if subtotal_val > 0 and tax_val > 0 and total_val > 0:
        expected_tot = round(subtotal_val + tax_val, 2)
        if abs(expected_tot - total_val) > 1.0:
            flaws_list.append(f"Header total ({total_val}) does not match subtotal ({subtotal_val}) + tax ({tax_val}).")

    if expected_quotation:
        m_status = getattr(expected_quotation, "match_status", "NO_QUOTATION")
        if m_status == "MISMATCH":
            discrepancies = getattr(expected_quotation, "discrepancies", [])
            for d in discrepancies:
                if d not in flaws_list:
                    flaws_list.append(d)
        elif m_status == "NO_QUOTATION":
            flaws_list.append("No pre-approved quotation was on file for this vendor prior to invoice arrival.")

    if doc_type == "QUOTATION":
        summary = (
            f"Quotation {inv_no} from {v_name} for {curr} {total_val:,.2f} across {items_cnt} line item(s). "
            f"Registered with Net 30 billing terms."
        )
    else:
        q_label = "pre-approved quotation" if (expected_quotation and getattr(expected_quotation, "match_status", "") == "EXACT_MATCH") else "independent review"
        flaw_count = len(flaws_list)
        flaw_note = f"Identified {flaw_count} exception(s) requiring review." if flaw_count > 0 else "All financial fields reconcile accurately."
        summary = (
            f"Invoice {inv_no} issued by {v_name} on {inv_date} for total {curr} {total_val:,.2f} ({items_cnt} line items). "
            f"Processed against {q_label}. {flaw_note}"
        )

    return (summary, flaws_list, brain_used)
