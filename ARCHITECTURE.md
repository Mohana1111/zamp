# ClearPay AP — Architecture & API Contract

## Overview
ClearPay AP is an automated Invoice-to-Decision system built for PS-1 (Finance / AP).
Core Pillars:
1. **Multi-Source Direct Pull**: Pull invoices directly from **Gmail** (Live IMAP or pre-loaded Simulated AP Inbox `ap-invoices@acmemfg.in`), Shared Drive, or Multi-Format File Drop (PDF, Scanned Image, XLSX, DOCX).
2. **Multi-Format -> Standard Invoice Template**: Every messy vendor invoice across locales (India INR/GST, Germany EUR/VAT, US USD, Singapore SGD) is normalized into our canonical `StandardInvoice` template.
3. **Compare & Highlight Workbench (Main Differentiator)**:
   - Side-by-side **Invoice vs PO** header & line-item diff with color-coded status (`MATCH`, `WARN`, `PRICE_VARIANCE`, `QTY_VARIANCE`, `UNORDERED_ITEM`, `MISMATCH`).
   - **PO Consumption Timeline** showing split invoices consuming a PO and highlighting overbilling.
   - **Invoice vs Invoice Duplicate Diff** showing exact vs normalized matches (`INV/2026/0081` vs `INV-2026-0081`).
4. **AI Reads, Deterministic Rules Decide**: 8 visible execution stages with full auditability.

---

## Reference Data (`backend/data/`)

### 1. `vendors.csv`
Columns: `vendor_id,legal_name,aliases,country,tax_id,default_currency,bank_account,bank_code,status,payment_terms`
- `V001`: `Shree Ganesh Packaging Pvt Ltd`, aliases `Shree Ganesh Packaging|SG Packaging`, `IN`, `27AABCS1234F1Z5`, `INR`, `50200012345678`, `HDFC0001234`, `ACTIVE`, `NET30`
- `V002`: `Brightline Software Inc`, aliases `Brightline|Brightline Software|Brightline Cloud`, `US`, `12-3456789`, `USD`, `000123456789`, `021000021`, `ACTIVE`, `NET45`
- `V003`: `Müller Industrietechnik GmbH`, aliases `Muller Industrietechnik|Müller GmbH|Muller GmbH`, `DE`, `DE123456789`, `EUR`, `DE89370400440532013000`, `DEUTDEFF`, `ACTIVE`, `NET30`
- `V004`: `Lion City Logistics Pte Ltd`, aliases `Lion City Logistics|LionCity Logistics`, `SG`, `201912345K`, `SGD`, `0123456789`, `DBSSSGSG`, `ACTIVE`, `NET30`
- `V005`: `Apex Industrial Components Pvt Ltd`, aliases `Apex Industrial|Apex Components`, `IN`, `27AAECA9876B1Z2`, `INR`, `91827364501234`, `ICIC0000451`, `ACTIVE`, `NET30`

### 2. `purchase_orders.csv`
Columns: `po_number,vendor_id,currency,po_date,subtotal,tax_amount,total_amount,invoiced_amount,remaining_amount,status,approver`
- `PO-2026-1041`: `V001`, `INR`, `2026-10-01`, `200000.00`, `36000.00`, `236000.00`, `0.00`, `236000.00`, `OPEN`, `Rahul Sharma` (Used for Happy Path exact match: ₹2,36,000 incl 18% GST)
- `PO-2026-1042`: `V005`, `INR`, `2026-10-05`, `100000.00`, `0.00`, `100000.00`, `0.00`, `100000.00`, `OPEN`, `Rahul Sharma` (Used for Split Invoices E1: Part 1 ₹60,000 -> Part 2 ₹40,000 -> Part 3 ₹15,000 Overbill!)
- `PO-2026-1043`: `V002`, `USD`, `2026-10-10`, `12000.00`, `0.00`, `12000.00`, `0.00`, `12000.00`, `OPEN`, `Rahul Sharma` (Used for E4 Fraud Bank Account Changed: amounts match $12,000, but bank account is `999888777666` instead of `000123456789`)
- `PO-2026-1045`: `V003`, `EUR`, `2026-10-12`, `5900.00`, `1121.00`, `7021.00`, `0.00`, `7021.00`, `OPEN`, `Rahul Sharma` (Used for E3 Scanned German invoice with NO PO reference & European numbers `5.900,00 €` + `1.121,00 €` = `7.021,00 €`; and E9 Currency Mismatch where invoice is billed in USD $7,650 instead of EUR)
- `PO-2026-1047`: `V004`, `SGD`, `2026-10-15`, `8500.00`, `0.00`, `8500.00`, `0.00`, `8500.00`, `OPEN`, `Rahul Sharma` (Used for XLSX spreadsheet invoice with +6.5% price variance on line 2)

### 3. `po_lines.csv`
Columns: `po_number,line_no,item_code,description,qty,unit_price,amount,tax_rate`
- `PO-2026-1041`:
  - Line 1: `PKG-BOX-L`, `Corrugated Export Cartons (Double Wall)`, `2000`, `75.00`, `150000.00`, `0.18`
  - Line 2: `PKG-TAPE-HD`, `Heavy Duty Strapping Rolls`, `500`, `100.00`, `50000.00`, `0.18`
- `PO-2026-1042`:
  - Line 1: `CNC-SPINDLE`, `High-Torque CNC Spindle Assembly`, `10`, `10000.00`, `100000.00`, `0.00`
- `PO-2026-1043`:
  - Line 1: `SAAS-ENT`, `Brightline Enterprise Cloud License (Annual)`, `1`, `12000.00`, `12000.00`, `0.00`
- `PO-2026-1045`:
  - Line 1: `HP-200`, `Hydraulic Pump HP-200`, `4`, `1250.00`, `5000.00`, `0.19`
  - Line 2: `SK-10`, `Precision Seal Kit SK-10`, `20`, `45.00`, `900.00`, `0.19`
- `PO-2026-1047`:
  - Line 1: `FRT-SEA-20`, `20ft Container Sea Freight (SG to JNPT)`, `2`, `3500.00`, `7000.00`, `0.00`
  - Line 2: `PORT-THC`, `Terminal Handling & Documentation Charges`, `1`, `1500.00`, `1500.00`, `0.00`

### 4. `fx_rates.csv`
Columns: `currency,rate_to_inr,symbol,updated_at`
- `INR,1.00,₹,2026-10-28`
- `USD,84.10,$,2026-10-28`
- `EUR,91.60,€,2026-10-28`
- `GBP,109.30,£,2026-10-28`
- `SGD,64.20,S$,2026-10-28`

### 5. Sample Invoices (`backend/data/sample_invoices/`)
1. `01_happy_shree_ganesh_inr.pdf` — Clean PDF, `INV-2026-0081`, Vendor `Shree Ganesh Packaging Pvt Ltd`, `PO-2026-1041`, Subtotal ₹2,00,000 + IGST 18% ₹36,000 = ₹2,36,000. Bank `50200012345678`. Outcome: `AUTO_APPROVE`.
2. `02_split_part1_apex_inr.pdf` — Clean PDF, `APEX-26-101`, Vendor `Apex Industrial Components Pvt Ltd`, `PO-2026-1042`, Qty 6 × ₹10,000 = ₹60,000 (Partial delivery 1 of PO ₹1,00,000). Outcome: `AUTO_APPROVE` (Remaining PO balance becomes ₹40,000).
3. `03_split_part2_apex_inr.pdf` — Clean PDF, `APEX-26-102`, Vendor `Apex Industrial Components Pvt Ltd`, `PO-2026-1042`, Qty 4 × ₹10,000 = ₹40,000 (Partial delivery 2 of PO ₹1,00,000). Outcome: `AUTO_APPROVE` (Remaining PO balance becomes ₹0).
4. `04_split_part3_overbill_apex_inr.pdf` — Clean PDF, `APEX-26-103`, Vendor `Apex Industrial Components Pvt Ltd`, `PO-2026-1042`, Qty 1.5 / 2 units = ₹15,000. Outcome: `REJECT` (`PO_OVERBILLED` — PO-2026-1042 is 100% consumed; ₹15,000 exceeds remaining ₹0).
5. `05_duplicate_rescan_shree_ganesh.pdf` — Disguised duplicate of #1! Invoice number formatted as `INV/2026/0081` (slashes instead of hyphens), rendered as a slightly tilted/scanned image inside a PDF, same vendor & amount ₹2,36,000. Outcome: `REJECT` (`DUPLICATE_INVOICE` — matches `INV-2026-0081`).
6. `06_scanned_muller_no_po_eur.png` — Scanned/noisy image invoice from `Müller Industrietechnik GmbH` (Germany), Invoice `RE-2026-0412`, **missing PO number**, European formatting (`5.900,00 €` + VAT 19% `1.121,00 €` = `7.021,00 €`), IBAN `DE89370400440532013000`. System OCRs image, normalizes European decimals, infers `PO-2026-1045` (100% line match), routes to `NEEDS_REVIEW` (`PO_INFERRED`, `SCANNED_DOCUMENT`) so human can confirm the inferred PO in 1 click!
7. `07_fraud_bank_changed_brightline_usd.pdf` — Clean PDF from `Brightline Software Inc`, `BL-2026-990`, `PO-2026-1043`, USD `$12,000.00`. Line items match 100%, BUT payment bank account on invoice is `999888777666` (Routing `099999999`) instead of master `000123456789`! Outcome: `REJECT` (`BANK_DETAILS_CHANGED` — critical BEC fraud alert).
8. `08_currency_mismatch_muller_usd.pdf` — PDF from `Müller Industrietechnik GmbH`, `RE-2026-0499`, references `PO-2026-1045` (which is a EUR 7,021.00 PO), but billed in `USD 7,650.00`! Outcome: `NEEDS_REVIEW` (`CURRENCY_MISMATCH` — shows FX equivalent comparison).
9. `09_price_variance_lioncity_sgd.xlsx` — Excel (`.xlsx`) invoice from `Lion City Logistics Pte Ltd`, `LCL-SG-882`, `PO-2026-1047`, Currency `$` (inferred as `SGD` via Vendor Master!). Line 1 matches (`2 × 3,500 = 7,000`), Line 2 billed at `1,950.00` instead of `1,500.00` (+30% line variance, +5.3% total invoice variance: SGD 8,950 vs PO SGD 8,500). Outcome: `NEEDS_REVIEW` (`PRICE_VARIANCE`, `CURRENCY_INFERRED`).
10. `10_missing_fields_draft.docx` — Word (`.docx`) invoice from `Shree Ganesh Packaging Pvt Ltd` with **missing Invoice Number** and **math error** (lines sum to ₹50,000, subtotal says ₹50,000, GST ₹9,000, total says ₹64,000!). Outcome: `ON_HOLD` (`MISSING_INVOICE_NUMBER`, `ARITHMETIC_MISMATCH`).

---

## FastAPI Endpoints (`backend/main.py` on port `8000`)

- `GET /api/health` -> `{"status": "ok"}`
- `GET /api/overview` -> returns dashboard KPIs, runs list, POs, vendors, FX rates, and sample scenarios list.
- `GET /api/runs` -> list of all `InvoiceRunResult` (newest first).
- `GET /api/runs/{run_id}` -> single `InvoiceRunResult`.
- `POST /api/runs/upload` -> accepts `multipart/form-data` with `files: List[UploadFile]` (supports single or batch upload of PDF, PNG, JPG, XLSX, DOCX) and optional `source_type`. Processes each file and returns `{"runs": List[InvoiceRunResult]}`.
- `POST /api/runs/sample/{sample_id}` -> runs one of the 10 built-in scenarios (or `"batch_demo"` to run a curated set) and returns `{"runs": List[InvoiceRunResult]}`.
- `POST /api/runs/{run_id}/override` -> body `{"decision": "AUTO_APPROVE" | "REJECT", "comment": str, "reviewer": str}` -> updates run decision (and updates PO ledger if approved) and returns updated `InvoiceRunResult`.
- `GET /api/sources/gmail/messages` -> returns emails in the connected Gmail inbox (simulated AP inbox `ap-invoices@acmemfg.in` by default, or live IMAP if configured).
- `POST /api/sources/gmail/connect` -> body `{"mode": "SIMULATED" | "IMAP", "email": str, "app_password": Optional[str]}` -> tests/saves connection and returns inbox messages.
- `POST /api/sources/gmail/pull` -> body `{"message_ids": List[str]}` -> pulls the selected email attachments directly from Gmail/Inbox, runs them through the 8-stage pipeline, marks them processed, and returns `{"runs": List[InvoiceRunResult]}`.
- `GET /api/files/{filename}` -> serves the raw invoice file (PDF/PNG/XLSX/DOCX) from `backend/data/sample_invoices/` or uploaded temp dir so the UI can preview or download the original document!
- `GET /api/files/{filename}/preview-image` -> renders page 1 of a PDF (or returns the image) as a PNG using PyMuPDF so the Frontend can display a crisp visual preview of ANY PDF or image side-by-side with the Standardized Invoice Template without browser PDF iframe issues!
- `POST /api/reset` -> resets `purchase_orders.csv` balances to initial state, clears run history (or restores clean initial state), and resets inbox unread statuses for a fresh live demo.
