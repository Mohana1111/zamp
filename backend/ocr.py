"""
Document Ingestion & Optical Character Recognition (OCR) Layer.

Production & Memory-Safe Architecture:
1. Native text layer via PyMuPDF. If text >= 40 chars/page -> use "text-layer" (0.98 confidence).
2. Production default: ENABLE_LOCAL_OCR='false' to stay strictly under Render's 512MB RAM limit.
3. When ENABLE_LOCAL_OCR='false', scans and images are read via Gemini Vision if GEMINI_API_KEY is present;
   otherwise returns a clean low-confidence result routed to NEEDS_REVIEW with the plain message:
   'Scanned document could not be read automatically — please review manually' without crashing.
4. When ENABLE_LOCAL_OCR='true' and rapidocr-onnxruntime is installed, runs local OCR with downscaling
   (max 1600px long side), max 5 pages, 1 thread, and immediate engine deletion + gc.collect().
5. Returns: (text, ocr_method, ocr_confidence, metadata)
   where ocr_method is "text-layer" | "ocr" | "vision".
"""

import os
import gc
import io
from typing import Tuple, Dict, Any, List, Optional
from pathlib import Path
from PIL import Image

PLAIN_MANUAL_REVIEW_MSG = "Scanned document could not be read automatically — please review manually"


def is_local_ocr_enabled() -> bool:
    """Checks whether local OCR engine (RapidOCR) is permitted to run. Defaults to 'false'."""
    val = os.getenv("ENABLE_LOCAL_OCR", "false").strip().lower()
    return val in ("true", "1", "yes", "on", "enable", "enabled")


def _get_rapid_ocr():
    """Lazily instantiate RapidOCR engine if permitted and installed."""
    if not is_local_ocr_enabled():
        return None
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except Exception:
        return None


def _downscale_image(image_input, max_long_side: int = 1600) -> Tuple[bytes, Image.Image]:
    """
    Downscales images whose long side exceeds max_long_side (default ~1600px)
    to protect the 512MB RAM budget while preserving crisp OCR fidelity.
    Returns (image_bytes_png, PIL_Image).
    """
    if isinstance(image_input, Image.Image):
        img = image_input.copy()
    elif isinstance(image_input, (bytes, bytearray, memoryview)):
        img = Image.open(io.BytesIO(image_input))
    elif isinstance(image_input, (str, Path)):
        img = Image.open(str(image_input))
    else:
        raise ValueError(f"Unsupported image type: {type(image_input)}")

    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGB")

    w, h = img.size
    max_dim = max(w, h)
    if max_dim > max_long_side:
        scale = float(max_long_side) / float(max_dim)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resample_filter = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
        img = img.resize((new_w, new_h), resample=resample_filter)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), img


def _free_engine(engine=None):
    """Explicitly deletes OCR engine reference and triggers garbage collection."""
    if engine is not None:
        try:
            del engine
        except Exception:
            pass
    try:
        gc.collect()
    except Exception:
        pass


def _run_ocr_with_engine(engine, image_bytes: bytes) -> Tuple[str, float]:
    """Runs an active RapidOCR engine instance on image bytes."""
    if not engine or not image_bytes:
        return "", 0.0

    try:
        results, elapse = engine(image_bytes)
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


def _run_ocr_on_image(image_input) -> Tuple[str, float]:
    """Runs RapidOCR on an image with downscaling, lazy initialization, and immediate memory freeing."""
    if not is_local_ocr_enabled():
        return "", 0.0

    engine = _get_rapid_ocr()
    if not engine:
        return "", 0.0

    try:
        img_bytes, _ = _downscale_image(image_input, max_long_side=1600)
        return _run_ocr_with_engine(engine, img_bytes)
    except Exception:
        return "", 0.0
    finally:
        _free_engine(engine)


def _extract_via_vision(filepath: str, images: List[Any]) -> Tuple[str, float, Optional[Dict[str, Any]]]:
    """Extracts document data via Gemini Vision if available."""
    try:
        from backend.llm import llm_available, call_llm_json
        if not llm_available():
            return "", 0.0, None
    except Exception:
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

            # Scanned PDF: limit processing to at most 5 pages for memory safety
            max_pages = 5
            pages_to_process = min(page_count, max_pages)
            meta["pages_processed"] = pages_to_process
            if page_count > max_pages:
                meta["truncated_pages"] = True

            # If local OCR is disabled (default in production)
            if not is_local_ocr_enabled():
                rendered_images = []
                for idx in range(pages_to_process):
                    try:
                        pix = doc[idx].get_pixmap(dpi=150)
                        _, pil_img = _downscale_image(pix.tobytes("png"), max_long_side=1600)
                        rendered_images.append(pil_img)
                    except Exception:
                        pass

                # Attempt vision fallback if LLM key is configured
                if rendered_images:
                    v_text, v_conf, v_data = _extract_via_vision(filepath, rendered_images)
                    if v_text:
                        meta["vision_data"] = v_data
                        return v_text, "vision", v_conf, meta

                # No vision LLM key -> mark low-confidence for review, NEVER crash
                meta["review_required"] = True
                meta["ocr_skipped"] = PLAIN_MANUAL_REVIEW_MSG
                meta["message"] = PLAIN_MANUAL_REVIEW_MSG
                fallback_text = full_text or PLAIN_MANUAL_REVIEW_MSG
                return fallback_text, "ocr", 0.30, meta

            # Local OCR is enabled: lazy-load on-demand and process pages
            engine = _get_rapid_ocr()
            if not engine:
                meta["ocr_engine_error"] = "RapidOCR engine could not be initialized or is not installed"
                # Fallback to vision or manual review
                rendered_images = []
                for idx in range(pages_to_process):
                    try:
                        pix = doc[idx].get_pixmap(dpi=150)
                        _, pil_img = _downscale_image(pix.tobytes("png"), max_long_side=1600)
                        rendered_images.append(pil_img)
                    except Exception:
                        pass
                if rendered_images:
                    v_text, v_conf, v_data = _extract_via_vision(filepath, rendered_images)
                    if v_text:
                        meta["vision_data"] = v_data
                        return v_text, "vision", v_conf, meta

                meta["review_required"] = True
                meta["ocr_skipped"] = PLAIN_MANUAL_REVIEW_MSG
                meta["message"] = PLAIN_MANUAL_REVIEW_MSG
                return full_text or PLAIN_MANUAL_REVIEW_MSG, "ocr", 0.30, meta

            ocr_text_parts: List[str] = []
            ocr_scores: List[float] = []
            rendered_images = []

            try:
                for idx in range(pages_to_process):
                    page = doc[idx]
                    pix = page.get_pixmap(dpi=150)
                    img_bytes, pil_img = _downscale_image(pix.tobytes("png"), max_long_side=1600)
                    rendered_images.append(pil_img)

                    p_text, p_score = _run_ocr_with_engine(engine, img_bytes)
                    if p_text:
                        ocr_text_parts.append(p_text)
                        ocr_scores.append(p_score)
            finally:
                _free_engine(engine)
                engine = None

            ocr_full_text = "\n".join(ocr_text_parts).strip()
            avg_conf = (sum(ocr_scores) / len(ocr_scores)) if ocr_scores else 0.0

            if ocr_full_text and len(ocr_full_text) >= 30 and avg_conf >= 0.60:
                meta["ocr_engine"] = "RapidOCR (ONNX)"
                return ocr_full_text, "ocr", avg_conf, meta

            # Fallback to vision if available
            if rendered_images:
                v_text, v_conf, v_data = _extract_via_vision(filepath, rendered_images)
                if v_text:
                    meta["vision_data"] = v_data
                    return v_text, "vision", v_conf, meta

            fallback_text = ocr_full_text or full_text or PLAIN_MANUAL_REVIEW_MSG
            return fallback_text, "ocr", max(0.30, avg_conf), meta

        except Exception as e:
            meta["error"] = str(e)
            return "", "ocr", 0.0, meta

    # 2. Image formats (PNG, JPG, JPEG, WEBP, TIFF)
    elif ext in [".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"]:
        meta["format"] = ext[1:].upper()

        try:
            img_bytes, pil_img = _downscale_image(filepath, max_long_side=1600)
        except Exception as e:
            meta["error"] = str(e)
            return "", "ocr", 0.0, meta

        # If local OCR disabled (production default)
        if not is_local_ocr_enabled():
            v_text, v_conf, v_data = _extract_via_vision(filepath, [pil_img])
            if v_text:
                meta["vision_data"] = v_data
                return v_text, "vision", v_conf, meta

            meta["review_required"] = True
            meta["ocr_skipped"] = PLAIN_MANUAL_REVIEW_MSG
            meta["message"] = PLAIN_MANUAL_REVIEW_MSG
            return PLAIN_MANUAL_REVIEW_MSG, "ocr", 0.30, meta

        # Local OCR enabled
        engine = _get_rapid_ocr()
        ocr_text = ""
        avg_conf = 0.0

        if not engine:
            # Fallback to vision if available
            v_text, v_conf, v_data = _extract_via_vision(filepath, [pil_img])
            if v_text:
                meta["vision_data"] = v_data
                return v_text, "vision", v_conf, meta

            meta["review_required"] = True
            meta["ocr_skipped"] = PLAIN_MANUAL_REVIEW_MSG
            meta["message"] = PLAIN_MANUAL_REVIEW_MSG
            return PLAIN_MANUAL_REVIEW_MSG, "ocr", 0.30, meta

        try:
            ocr_text, avg_conf = _run_ocr_with_engine(engine, img_bytes)
        finally:
            _free_engine(engine)
            engine = None

        if ocr_text and len(ocr_text) >= 20 and avg_conf >= 0.60:
            meta["ocr_engine"] = "RapidOCR (ONNX)"
            return ocr_text, "ocr", avg_conf, meta

        # Fallback to vision if available
        try:
            v_text, v_conf, v_data = _extract_via_vision(filepath, [pil_img])
            if v_text:
                meta["vision_data"] = v_data
                return v_text, "vision", v_conf, meta
        except Exception:
            pass

        return ocr_text or PLAIN_MANUAL_REVIEW_MSG, "ocr", max(0.30, avg_conf), meta

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
