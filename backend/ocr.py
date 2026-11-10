"""
Document Ingestion & Optical Character Recognition (OCR) Layer.

Layered reading:
1. Native text layer via PyMuPDF. If text < ~40 chars/page -> treat as scanned.
2. Scanned PDF / image -> render pages at 200-300 dpi -> local OCR with rapidocr-onnxruntime.
3. If LLM has vision (Gemini) and OCR text is poor/empty -> send page images to Gemini for structured extraction.
4. Returns: (text, ocr_method, ocr_confidence, metadata)
   where ocr_method is "text-layer" | "ocr" | "vision".
"""

import os
import re
from typing import Tuple, Dict, Any, List, Optional
from pathlib import Path

# Lazy RapidOCR singleton
_RAPID_OCR_INSTANCE = None


def _get_rapid_ocr():
    """Lazily load RapidOCR engine."""
    global _RAPID_OCR_INSTANCE
    if _RAPID_OCR_INSTANCE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _RAPID_OCR_INSTANCE = RapidOCR()
        except Exception:
            _RAPID_OCR_INSTANCE = False
    return _RAPID_OCR_INSTANCE if _RAPID_OCR_INSTANCE is not False else None


def _run_ocr_on_image(image_input) -> Tuple[str, float]:
    """
    Runs RapidOCR on an image path, bytes, or numpy array.
    Returns: (extracted_text, average_confidence)
    """
    engine = _get_rapid_ocr()
    if not engine:
        return "", 0.0

    try:
        results, elapse = engine(image_input)
        if not results:
            return "", 0.0

        lines: List[str] = []
        scores: List[float] = []
        for item in results:
            if len(item) >= 2:
                txt = str(item[1]).strip()
                if txt:
                    lines.append(txt)
            if len(item) >= 3 and item[2] is not None:
                try:
                    scores.append(float(item[2]))
                except (ValueError, TypeError):
                    pass

        avg_score = round(sum(scores) / len(scores), 3) if scores else 0.85
        full_text = "\n".join(lines).strip()
        return full_text, avg_score
    except Exception:
        return "", 0.0


def _extract_via_vision(filepath: str, images: List[Any]) -> Tuple[str, float, Optional[Dict[str, Any]]]:
    """
    Extracts document data via Gemini Vision if available.
    Returns: (text_representation, confidence, structured_data)
    """
    from backend.llm import llm_available, call_llm_json

    if not llm_available():
        return "", 0.0, None

    system_prompt = (
        "You are an expert financial document vision parser. Examine the provided invoice image(s). "
        "Extract all fields strictly in JSON format with fields: "
        "vendor_name, vendor_tax_id, vendor_country, vendor_bank_account, vendor_bank_code, "
        "invoice_number, invoice_date, due_date, po_reference, currency, "
        "subtotal, tax_amount, total, raw_text, line_items (list of objects with line_no, item_code, description, qty, unit_price, amount, tax_rate)."
    )
    user_prompt = "Parse this invoice document image carefully. Extract all header values, tax details, and line items."

    try:
        data = call_llm_json(system=system_prompt, user=user_prompt, images=images, temperature=0.0)
        if data and isinstance(data, dict):
            # Synthesize text representation from extracted fields
            lines = [
                f"Vendor: {data.get('vendor_name', '')}",
                f"Tax ID: {data.get('vendor_tax_id', '')}",
                f"Invoice Number: {data.get('invoice_number', '')}",
                f"Invoice Date: {data.get('invoice_date', '')}",
                f"Due Date: {data.get('due_date', '')}",
                f"PO Reference: {data.get('po_reference', '')}",
                f"Currency: {data.get('currency', '')}",
                f"Subtotal: {data.get('subtotal', '')}",
                f"Tax: {data.get('tax_amount', '')}",
                f"Total: {data.get('total', '')}",
                f"Bank Account: {data.get('vendor_bank_account', '')}",
            ]
            raw_text = data.get("raw_text") or "\n".join(lines)
            return raw_text, 0.92, data
    except Exception:
        pass
    return "", 0.0, None


def read_document(filepath: str) -> Tuple[str, str, float, Dict[str, Any]]:
    """
    High-level layered document reader.

    Returns:
    (text, ocr_method, ocr_confidence, metadata)
    ocr_method is one of: "text-layer", "ocr", "vision"
    """
    path = Path(filepath)
    ext = path.suffix.lower()
    meta: Dict[str, Any] = {}

    # 1. PDF Documents
    if ext == ".pdf":
        import pymupdf
        try:
            doc = pymupdf.open(filepath)
            page_count = len(doc)
            meta["page_count"] = page_count

            # Extract native text layer
            page_texts = [page.get_text() for page in doc]
            full_text = "\n".join(p for p in page_texts if p).strip()
            chars_per_page = len(full_text) / max(1, page_count)

            # If native text is adequate (> 40 chars/page), use text layer
            if chars_per_page >= 40:
                return full_text, "text-layer", 0.98, meta

            # Otherwise, render pages and perform local OCR
            ocr_text_parts = []
            ocr_scores = []
            rendered_images = []

            for page in doc:
                pix = page.get_pixmap(dpi=250)
                img_bytes = pix.tobytes("png")
                p_text, p_score = _run_ocr_on_image(img_bytes)
                if p_text:
                    ocr_text_parts.append(p_text)
                    ocr_scores.append(p_score)

                # Keep PIL image for fallback vision
                try:
                    from PIL import Image
                    import io
                    rendered_images.append(Image.open(io.BytesIO(img_bytes)))
                except Exception:
                    pass

            ocr_full_text = "\n".join(ocr_text_parts).strip()
            avg_conf = (sum(ocr_scores) / len(ocr_scores)) if ocr_scores else 0.0

            if ocr_full_text and len(ocr_full_text) >= 30 and avg_conf >= 0.60:
                meta["ocr_engine"] = "RapidOCR (ONNX)"
                return ocr_full_text, "ocr", avg_conf, meta

            # If OCR was weak or empty, try Gemini vision if available
            if rendered_images:
                v_text, v_conf, v_data = _extract_via_vision(filepath, rendered_images)
                if v_text:
                    meta["vision_data"] = v_data
                    return v_text, "vision", v_conf, meta

            # Fallback to whatever OCR or native text we had
            fallback_text = ocr_full_text or full_text
            return fallback_text, "ocr", max(0.50, avg_conf), meta

        except Exception as e:
            meta["error"] = str(e)
            return "", "ocr", 0.0, meta

    # 2. Image formats (PNG, JPG, JPEG, WEBP, TIFF)
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"]:
        meta["format"] = ext[1:].upper()
        # Run RapidOCR directly on the image
        ocr_text, avg_conf = _run_ocr_on_image(filepath)
        if ocr_text and len(ocr_text) >= 20 and avg_conf >= 0.60:
            meta["ocr_engine"] = "RapidOCR (ONNX)"
            return ocr_text, "ocr", avg_conf, meta

        # Fallback to vision if available
        try:
            from PIL import Image
            img = Image.open(filepath)
            v_text, v_conf, v_data = _extract_via_vision(filepath, [img])
            if v_text:
                meta["vision_data"] = v_data
                return v_text, "vision", v_conf, meta
        except Exception:
            pass

        return ocr_text, "ocr", max(0.50, avg_conf), meta

    # 3. Excel Spreadsheets (.xlsx)
    elif ext == ".xlsx":
        import openpyxl
        try:
            wb = openpyxl.load_workbook(filepath, data_only=True)
            sheet = wb.active
            lines = []
            structured_rows = []
            for row in sheet.iter_rows(values_only=True):
                vals = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if vals:
                    lines.append(" | ".join(vals))
                    structured_rows.append(list(row))
            full_text = "\n".join(lines)
            meta["sheet_name"] = sheet.title
            meta["rows"] = structured_rows
            return full_text, "text-layer", 0.99, meta
        except Exception as e:
            meta["error"] = str(e)
            return "", "text-layer", 0.0, meta

    # 4. Word Documents (.docx)
    elif ext == ".docx":
        import docx
        try:
            d = docx.Document(filepath)
            lines = []
            for p in d.paragraphs:
                if p.text.strip():
                    lines.append(p.text.strip())
            for table in d.tables:
                for row in table.rows:
                    cell_vals = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cell_vals:
                        lines.append(" | ".join(cell_vals))
            full_text = "\n".join(lines)
            meta["paragraph_count"] = len(d.paragraphs)
            return full_text, "text-layer", 0.99, meta
        except Exception as e:
            meta["error"] = str(e)
            return "", "text-layer", 0.0, meta

    # 5. Plain Text / Fallback
    else:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return content, "text-layer", 0.95, meta
        except Exception:
            return "", "text-layer", 0.0, meta
