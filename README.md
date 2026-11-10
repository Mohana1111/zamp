# ClearPay AP — Autonomous Invoice-to-Decision Engine

ClearPay AP (Zamp AP Automation) is a production-ready, autonomous Accounts Payable processing pipeline. It automates end-to-end document intake, layered perception (native text layer + Gemini Vision fallback / optional local OCR), 2-way and 3-way PO matching, quotation comparison, vendor banking validation, policy enforcement, and decision routing (`AUTO_APPROVE`, `FLAG_FOR_REVIEW`, `REJECT`).

---

## Features & Highlights

- **8-Stage Deterministic Pipeline**: INTAKE → PERCEPTION → VENDOR RESOLUTION → PO MATCHING → QUOTATION COMPARISON → POLICY CHECKS → AI CROSS-REVIEW → DECISION ROUTING.
- **Memory-Safe for Render Free Tier (512MB RAM)**: Production default `ENABLE_LOCAL_OCR=false` eliminates heavy ONNX model memory overhead entirely. Scans and images are read via Gemini Vision when `GEMINI_API_KEY` is provided; if unset, documents route cleanly to `NEEDS_REVIEW` with clear guidance. For offline environments, optional local OCR (`requirements-ocr.txt`) includes image downscaling (1600px max side) and immediate garbage collection.
- **Dual Persistence Architecture**: MongoDB Atlas primary persistence (`kv_files` collection) with secondary PostgreSQL and local filesystem fallback. Uploads and run histories survive restarts.
- **Dual AI Review**: Optional Gemini Vision multimodal verification + Groq high-speed text analysis; operates 100% deterministically via rule engine when no AI keys are present.
- **Enterprise Security**: Configurable CORS, 15MB file upload limit (max 10 files per batch) with 413/400 errors, strict path-traversal prevention on file serving, expiring sessions, and per-install random password salt.

---

## Default Credentials

The system includes a pre-seeded administrator account for initial access:
- **Username**: `admin_1`
- **Password**: `pass@admin`

> **Security Note**: For production deployments, set `AUTH_SALT` in your environment and update credentials via the `/api/auth/register` or user management endpoints.

---

## Local Development

### 1. Backend (FastAPI)
```bash
# Install core production dependencies
pip install -r requirements.txt

# (Optional) Install local OCR dependencies for offline OCR:
# pip install -r requirements-ocr.txt

# Start backend server (port 8000)
uvicorn backend.main:app --reload --port 8000
```
API Documentation is available at `http://localhost:8000/docs`.

### 2. Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` to access the interactive AP workbench.

### 3. Run Automated Tests
```bash
# Run backend pytest suite
python -m pytest backend -q

# Build frontend production bundle
cd frontend && npm run build
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `PORT` | HTTP port for Uvicorn server (Render automatically sets this) | `10000` |
| `ENABLE_LOCAL_OCR` | Local RapidOCR engine control: `'false'` (production default: memory-safe, uses Gemini Vision if key provided, else flags for review), `'true'` (runs local RapidOCR from `requirements-ocr.txt`) | `false` |
| `MONGODB_URI` | MongoDB Atlas connection string for persistent cloud state | *(Optional)* |
| `MONGODB_DB` | MongoDB database name | `zamp_ap` |
| `DATABASE_URL` | PostgreSQL connection URL (secondary persistence fallback) | *(Optional)* |
| `GEMINI_API_KEY` | Google Gemini API key for multimodal vision extraction and cross-check | *(Optional)* |
| `GROQ_API_KEY` | Groq API key for high-speed executive summaries and anomaly reasoning | *(Optional)* |
| `AGENT_BOT_EMAIL` | Optional central Gmail address for autonomous IMAP email ingestion | *(Optional)* |
| `AGENT_BOT_APP_PASSWORD` | Optional 16-character Google App Password for IMAP access (if unset, built-in sample inbox is used) | *(Optional)* |
| `CORS_ORIGINS` | Permitted CORS origins (comma-separated list or `*`) | `*` |
| `AUTH_SALT` | Cryptographic salt for password hashing (auto-generated per install if empty) | *(Auto)* |
| `SESSION_TTL_SECONDS` | Session duration before expiration in seconds (default: 7 days) | `604800` |

---

## Render Free Tier Deployment

The repository is pre-configured with a multi-stage `Dockerfile` and `render.yaml` blueprint. The multi-stage build compiles the React frontend into static assets served directly by FastAPI on a single port.

### Deployment Steps:
1. **Push code to GitHub**: Commit and push changes to your repository.
2. **Create Render Blueprint**:
   - In the [Render Dashboard](https://dashboard.render.com), click **New** → **Blueprint**.
   - Connect your GitHub repository.
   - Render reads `render.yaml` automatically, configuring the Docker service and health check (`/api/health`).
3. **Configure Environment Variables in Render**:
   - Set `MONGODB_URI` to your MongoDB Atlas connection string (e.g. free M0 cluster).
   - *(Optional)* Set `GEMINI_API_KEY` and/or `GROQ_API_KEY`.
   - *(Optional)* Set `AGENT_BOT_EMAIL` and `AGENT_BOT_APP_PASSWORD` for live email polling.
   - `ENABLE_LOCAL_OCR` is pre-set to `false` for 512MB RAM safety.
4. **Deploy**:
   - Render builds the frontend, packages the lean Python runtime, and launches Uvicorn on `${PORT}`.
   - Health check probes `/api/health`.

---

## Demo Sample Invoices

The `backend/data/sample_invoices/` directory contains realistic multi-format test documents covering core accounts payable scenarios:

1. **`01_happy_shree_ganesh_inr.pdf`**: Standard happy path matching PO-2026-1041. Decision: `AUTO_APPROVE`.
2. **`02_bank_mismatch_shree_ganesh.pdf`**: Invoice bank account differs from registered vendor master. Flags vendor banking fraud.
3. **`03_line_item_overbilling_shree_ganesh.pdf`**: Unit price exceeds PO line item price tolerance. Decision: `HUMAN_REVIEW`.
4. **`04_po_budget_exceeded_shree_ganesh.pdf`**: Invoice total exceeds the remaining line quantity/budget on the PO.
5. **`05_duplicate_rescan_shree_ganesh.pdf`**: Duplicate invoice number / SHA-256 hash detection.
6. **`06_scanned_muller_no_po_eur.png` & `.pdf`**: Raster scanned German invoice without PO. Validates OCR / Vision perception and vendor policy tolerance.
7. **`07_fraud_bank_changed_brightline_usd.pdf`**: High-value USD invoice with altered remittance credentials.
8. **`08_currency_mismatch_muller_usd.pdf`**: Invoice billed in USD against EUR PO reference.
9. **`09_price_variance_lioncity_sgd.xlsx` & `.pdf`**: Multi-format Excel spreadsheet intake with line item variances.
10. **`10_missing_fields_draft.docx` & `.pdf`**: Word document draft with missing mandatory invoice fields.
11. **`11_bundled_embedded_tax_tolerance_inr.pdf`**: Complex bundled tax tolerance edge case.
