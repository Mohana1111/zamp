# Production QA Simulation Report — ClearPay AP

**Test Run Date:** November 10, 2026  
**Environment:** Windows (x64), Python 3.13.5, Node v22.16.0, Chromium Headless  
**Target Host:** Production mode on `http://127.0.0.1:8080` (FastAPI + Vite single-origin bundle)  
**QA Engine:** Antigravity Autonomous QA Suite  

---

## Executive Summary

ClearPay AP was subjected to end-to-end production simulation testing covering:
1. Production single-origin serving (SPA routing & API endpoints)
2. Real-time Server-Sent Events (SSE) streaming and batch invoice processing
3. Edge-case and adversarial file uploads (empty, corrupted, huge, non-invoice, unicode, concurrent)
4. Vendor policy flows and AP governance settings
5. PO ledger consumption and human reviewer overrides
6. Memory profiling during large document and OCR ingestion against Render's 512 MB free-tier limit
7. Full headless browser verification with Playwright (authentication, dashboard, invoices list, detail drawer)

Overall system stability is strong: zero HTTP 500 crashes were encountered across all tests, the UI operates with zero browser console errors, and deterministic 8-stage verification accurately matches policy specifications. However, **1 Critical/High memory issue** (Render free tier OOM vulnerability) and **2 Medium logic issues** (ledger rollback missing on rejection override, and sample PO collisions in batch upload) were uncovered.

---

## Test Results by Step

| Step | Verification Area | Status | Key Metrics / Findings |
|---|---|---|---|
| **Step 1** | Production Serving & Assets | **PASS** | `/` serves `index.html` (200), CSS (45.6KB) and JS (306.1KB) load cleanly, all `/api/*` endpoints respond with 200 JSON. |
| **Step 2** | Sample Invoices (SSE & Sync) | **PASS / FINDING** | SSE event sequence `file_start` &rarr; `stage*` (10 stages) &rarr; `run_complete` &rarr; `done` verified. All 11 scenarios match expected decisions individually. PO exhaustion causes scenarios 10 & 11 to reject in full batch mode. |
| **Step 3** | Edge Cases & Malformed Files | **PASS** | 0-byte PDF, empty TXT, corrupt PDF, 17.9MB huge image, 4.5MB non-invoice PDF, `.exe`, `.xyz`, unicode filename, and concurrent uploads all returned clean HTTP 200 results with zero 500s or hangs. |
| **Step 4** | Vendor Policy & Governance | **PASS** | `BLOCKED` &rarr; `REJECT` (`BLOCKED_VENDOR`), `WATCHLIST` &rarr; `NEEDS_REVIEW` (`WATCHLIST_VENDOR`), `PREAPPROVED` with `allow_without_po`, tightening tolerance to 0.05% correctly changes invoice 11 decision. |
| **Step 5** | Human Override & PO Ledger | **PASS / DEFECT** | Overriding `NEEDS_REVIEW` to `AUTO_APPROVE` deducts PO balance as expected. **Defect**: Overriding an approved invoice to `REJECT` does NOT restore or refund the PO ledger. |
| **Step 6** | Server RSS Memory Profile | **FAIL (vs 512MB)** | Baseline: 177.69 MB. Peak during Big PDF: 181.05 MB (+3.91 MB). **Peak during Scanned PNG: 572.90 MB (+395.21 MB, 111.9% of limit)**. Exceeds 512MB by **60.90 MB**. |
| **Step 7** | Playwright Headless Browser | **PASS** | Auth view login (`admin_1`), dashboard rendering, sample analysis, invoice table navigation, and detail drawer opening completed with **0 console errors, 0 page errors, and 0 failed requests**. |

---

## Detailed Findings and Actionable Issue List

### Issue 1: [HIGH / PRODUCTION OOM] Peak RSS Memory Exceeds 512MB Free Tier Container Limit
- **Component**: `backend/ocr.py` / RapidOCR runtime
- **Severity**: HIGH (Production deployment failure on Render Free Tier)
- **Measurement**:
  - Baseline Memory: `177.69 MB`
  - Big PDF (4.52 MB): `181.05 MB`
  - Scanned PNG (`06_scanned_muller_no_po_eur.png`, 3.25 MB): **`572.90 MB`** (Delta: `+395.21 MB`)
  - Render Free Tier Limit: `512.00 MB`
  - Headroom: **`-60.90 MB` (OOM Trigger)**
- **Repro**:
  ```powershell
  python qa/test_step6_memory_profile.py
  ```
- **Root Cause**:
  RapidOCR (ONNXRuntime) instantiates full-size tensor buffers and uncompressed image matrices in RAM during text detection and angle classification for large scanned images.
- **Suggested Fix**:
  1. Downsample high-resolution scanned images before OCR inference if width or height exceeds 1600px:
     ```python
     if max(img.shape[:2]) > 1600:
         scale = 1600.0 / max(img.shape[:2])
         img = cv2.resize(img, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
     ```
  2. Restrict ONNXRuntime thread concurrency to 1 thread in `backend/ocr.py` to prevent multi-core tensor memory ballooning.
  3. Explicitly trigger `import gc; gc.collect()` after OCR execution completes.

---

### Issue 2: [MEDIUM / LEDGER INTEGRITY] Overriding Approved Invoice to REJECT Does Not Refund PO Balance
- **Component**: `backend/engine.py` (lines 2764–2775)
- **Severity**: MEDIUM (Financial ledger drift / permanent PO lock)
- **Repro**:
  1. Submit or approve an invoice referencing `PO-2026-1045` (e.g., $7,650).
  2. Notice `invoiced_amount` increases by $7,650 and `remaining_amount` drops to $0.00.
  3. As a reviewer, call `POST /api/runs/{run_id}/override` with `{"decision": "REJECT", "comment": "Audit failed"}`.
  4. Query `GET /api/overview`: `invoiced_amount` remains $7,650 and `remaining_amount` remains $0.00. The PO is locked as CLOSED despite the invoice being rejected.
- **Root Cause**:
  `override_run_decision` in `backend/engine.py` only updates the ledger when `new_decision in ["AUTO_APPROVE", "APPROVED"]`:
  ```python
  if new_decision in ["AUTO_APPROVE", "APPROVED"]:
      if old_decision != "AUTO_APPROVE" and run.matched_po_number and run.invoice_total:
          update_po_ledger(run.matched_po_number, run.invoice_total)
  elif new_decision == "REJECT":
      # Missing refund logic!
  ```
- **Suggested Fix**:
  In `backend/engine.py:2771`:
  ```python
  elif new_decision in ["REJECT", "ON_HOLD"]:
      run.human_approval_status = "REJECTED_BY_HUMAN"
      run.decision_title = f"Manually Rejected by {reviewer}"
      if old_decision in ["AUTO_APPROVE", "APPROVED"] and run.matched_po_number and run.invoice_total:
          update_po_ledger(run.matched_po_number, -run.invoice_total)
  ```
  Ensure `update_po_ledger` handles negative adjustments to restore `remaining_amount` and reopen `CLOSED` POs.

---

### Issue 3: [MEDIUM / DEMO COLLISION] Shared PO-2026-1041 Causes False Rejections in Batch Uploads
- **Component**: `backend/engine.py` (lines 2141–2146) & `backend/data/sample_invoices/`
- **Severity**: MEDIUM (Demo / Ingestion UX variance)
- **Description**:
  In the sample dataset, invoices 01, 05, 10, and 11 all target the exact same purchase order `PO-2026-1041` (total ₹2,36,000).
  - Invoice 01 consumes 100% of PO-2026-1041.
  - When a user uploads the entire sample folder at once (via `/api/runs/upload-stream` or `/api/runs/upload`), invoice 10 (draft) and invoice 11 (tolerance) fail with `PO_OVERBILLED` (`REJECT`) instead of `ON_HOLD` and `AUTO_APPROVE`.
  - In `engine.py:2144`, `PO_OVERBILLED` is appended without checking `is_draft_or_invalid`, causing draft validation errors to be escalated to critical PO rejection.
- **Suggested Fix**:
  1. In `backend/engine.py:2141`:
     ```python
     elif remaining_before <= 0.01:
         if not is_draft_or_invalid:
             consumption_status = "PO_CLOSED"
             overbilled_amount = this_invoice
             reason_codes.append("PO_OVERBILLED")
             s6_status = "FAIL"
             s6_details.append("CRITICAL: PO has zero remaining balance.")
     ```
  2. For demonstration runs, consider assigning dedicated sample PO numbers (e.g. `PO-2026-1041` for 01/05, `PO-2026-1046` for 10, `PO-2026-1047` for 11).

---

### Issue 4: [LOW / STABILITY] PyMuPDF ValueError When Converting Empty Lines to PDF
- **Component**: `backend/connectors.py` (line 311)
- **Severity**: LOW (Internal warning/exception in email-to-PDF ingestion)
- **Traceback**:
  ```
  File "pymupdf/__init__.py", line 15419, in insert_text
      maxcode = max([ord(c) for c in " ".join(text)])
  ValueError: max() iterable argument is empty
  ```
- **Root Cause**:
  `page.insert_text((45, y), line[:115], fontsize=9)` is called when `line` is an empty string `""`. PyMuPDF expects at least one character to compute font encoding.
- **Suggested Fix**:
  ```python
  if line and line.strip():
      page.insert_text((45, y), line[:115], fontsize=9)
  ```

---

### Issue 5: [LOW / CODE HYGIENE] Unimported `Tuple` Type Hint in `main.py`
- **Component**: `backend/main.py` (line 1033)
- **Severity**: LOW (Linter / runtime typing inspection warning)
- **Description**:
  Line 1033 declares `saved_files: List[Tuple[str, str]] = []`. However, `Tuple` is not imported from `typing` at line 25.
- **Suggested Fix**:
  Add `Tuple` to `from typing import ...` at line 25 of `backend/main.py`, or use Python 3.9+ builtin `list[tuple[str, str]]`.

---

## Test Artifacts Created

The automated QA suite produced the following test assets located under `qa/`:
- `qa/test_step1_production_serving.py`: Verifies production SPA and API health contract.
- `qa/test_step2_sample_uploads.py`: Tests SSE streaming order and sync batch uploads.
- `qa/test_step2_scenarios.py`: Validates deterministic decisions across all 11 business scenarios.
- `qa/test_step3_edge_cases.py`: Adversarial edge case upload suite (8 scenarios).
- `qa/test_step4_policy_and_step5_override.py`: Policy evaluation & PO ledger override tests.
- `qa/test_step6_memory_profile.py`: Server process memory profiling with `psutil`.
- `qa/test_step7_playwright.py`: End-to-end headless browser regression suite.
- `qa/memory_results.json`: Raw memory telemetry during large file ingestion.
- `qa/browser_audit.json`: UI console log audit, network status, and visual captures.
- `qa/screens/01_dashboard.png`: Browser capture of executive AP dashboard.
- `qa/screens/02_invoices.png`: Browser capture of verified invoices queue.
- `qa/screens/03_detail_drawer.png`: Browser capture of invoice side-by-side inspection drawer.
