"""
Diagnostic script to investigate:
1. Structure of run dict from /api/runs/upload
2. Why /api/dashboard returned 0
3. Failure reasons for 10 and 11
"""
import httpx
import json
from pathlib import Path

BASE_URL = "http://127.0.0.1:8080"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "sample_invoices"

client = httpx.Client(base_url=BASE_URL, timeout=60.0)

print("1. Resetting...")
client.post("/api/reset")

print("\n2. Uploading 01, 10, 11 via POST /api/runs/upload...")
test_files = [
    "01_happy_shree_ganesh_inr.pdf",
    "10_missing_fields_draft.docx",
    "10_missing_fields_draft.pdf",
    "11_bundled_embedded_tax_tolerance_inr.pdf",
]

files = []
for tf in test_files:
    p = SAMPLES_DIR / tf
    files.append(("files", (tf, open(p, "rb").read(), "application/octet-stream")))

res = client.post("/api/runs/upload", files=files)
data = res.json()
runs = data.get("runs", [])
print(f"Returned {len(runs)} runs.")

for r in runs:
    print(f"\n--- Run ID: {r.get('run_id')} ---")
    print(f"Decision: {r.get('decision')}")
    print(f"Decision reason: {r.get('decision_reason')}")
    print(f"Policy flags: {r.get('policy_flags')}")
    print(f"Source info: {r.get('source_info')}")
    print(f"Top-level keys in run: {list(r.keys())}")

print("\n3. Checking /api/runs...")
r_runs = client.get("/api/runs")
print(f"GET /api/runs returned {len(r_runs.json())} items.")

print("\n4. Checking /api/dashboard...")
r_dash = client.get("/api/dashboard")
print(f"GET /api/dashboard response:")
print(json.dumps(r_dash.json(), indent=2))
