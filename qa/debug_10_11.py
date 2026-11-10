"""
Inspect details of 10 and 11.
"""
import httpx
import json
from pathlib import Path

BASE_URL = "http://127.0.0.1:8080"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "sample_invoices"

client = httpx.Client(base_url=BASE_URL, timeout=60.0)
client.post("/api/reset")

files = [
    ("files", ("10_missing_fields_draft.docx", open(SAMPLES_DIR / "10_missing_fields_draft.docx", "rb").read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
    ("files", ("10_missing_fields_draft.pdf", open(SAMPLES_DIR / "10_missing_fields_draft.pdf", "rb").read(), "application/pdf")),
    ("files", ("11_bundled_embedded_tax_tolerance_inr.pdf", open(SAMPLES_DIR / "11_bundled_embedded_tax_tolerance_inr.pdf", "rb").read(), "application/pdf")),
]

res = client.post("/api/runs/upload", files=files)
data = res.json()
for r in data.get("runs", []):
    inv_num = r.get("standard_invoice", {}).get("invoice_number", {}).get("value")
    po_num = r.get("matched_po_number")
    print(f"\n==========================================")
    print(f"Run ID: {r.get('run_id')}")
    print(f"Invoice Number: {inv_num}")
    print(f"Matched PO: {po_num}")
    print(f"Decision: {r.get('decision')}")
    print(f"Reason Codes: {r.get('reason_codes')}")
    print(f"Decision Title: {r.get('decision_title')}")
    print(f"Decision Summary: {r.get('decision_summary')}")
    print("Stages:")
    for s in r.get("stages", []):
        print(f"  {s.get('key')}: {s.get('status')} - {s.get('summary')}")
