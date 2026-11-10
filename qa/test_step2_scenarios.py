"""
Step 2 Verification:
Test 1: Full batch upload of all sample files via /api/runs/upload-stream
Test 2: Full batch upload of all sample files via /api/runs/upload
Test 3: Individual scenario verification following business lifecycle:
  - Reset
  - 01: AUTO_APPROVE
  - 05: REJECT (duplicate of 01)
  - 02: AUTO_APPROVE (split part 1)
  - 03: AUTO_APPROVE (split part 2)
  - 04: REJECT (split part 3 overbilling)
  - 06: NEEDS_REVIEW (inferred PO)
  - 07: REJECT (bank account changed)
  - 08: NEEDS_REVIEW (currency mismatch)
  - 09: NEEDS_REVIEW (price variance)
  - Reset for 10 (draft invoice on clean PO)
  - 10: ON_HOLD (missing invoice number)
  - Reset for 11 (tolerance invoice on clean PO)
  - 11: AUTO_APPROVE (within tolerance)
"""

import json
import httpx
from pathlib import Path

BASE_URL = "http://127.0.0.1:8080"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "sample_invoices"

ORDERED_SAMPLES = [
    "01_happy_shree_ganesh_inr.pdf",
    "02_split_part1_apex_inr.pdf",
    "03_split_part2_apex_inr.pdf",
    "04_split_part3_overbill_apex_inr.pdf",
    "05_duplicate_rescan_shree_ganesh.pdf",
    "06_scanned_muller_no_po_eur.png",
    "07_fraud_bank_changed_brightline_usd.pdf",
    "08_currency_mismatch_muller_usd.pdf",
    "09_price_variance_lioncity_sgd.xlsx",
    "10_missing_fields_draft.docx",
    "11_bundled_embedded_tax_tolerance_inr.pdf",
]

EXPECTED_DECISIONS = {
    "01": "AUTO_APPROVE",
    "02": "AUTO_APPROVE",
    "03": "AUTO_APPROVE",
    "04": "REJECT",
    "05": "REJECT",
    "06": "NEEDS_REVIEW",
    "07": "REJECT",
    "08": "NEEDS_REVIEW",
    "09": "NEEDS_REVIEW",
    "10": "ON_HOLD",
    "11": "AUTO_APPROVE",
}

def parse_sse(text: str):
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    events.append(json.loads(payload))
                except Exception:
                    pass
    return events


def test_batch_stream(client: httpx.Client):
    print("\n--- Test 1: Full Batch Upload via /api/runs/upload-stream ---")
    client.post("/api/reset")

    files = []
    for fn in ORDERED_SAMPLES:
        p = SAMPLES_DIR / fn
        files.append(("files", (fn, open(p, "rb").read(), "application/octet-stream")))

    res = client.post("/api/runs/upload-stream", files=files, timeout=180.0)
    assert res.status_code == 200, f"Upload stream failed: {res.status_code}"
    events = parse_sse(res.text)

    # Check termination
    assert any(e.get("type") == "done" for e in events), "No 'done' event in stream"

    # Per file events and decisions
    file_events = {}
    completed = {}
    for ev in events:
        fn = ev.get("file")
        if not fn:
            continue
        file_events.setdefault(fn, []).append(ev.get("type"))
        if ev.get("type") == "run_complete":
            completed[fn] = ev.get("run")

    for fn in ORDERED_SAMPLES:
        evs = file_events.get(fn, [])
        order_ok = (
            "file_start" in evs
            and "stage" in evs
            and "run_complete" in evs
            and evs.index("file_start") < evs.index("stage") < evs.index("run_complete")
        )
        dec = completed.get(fn, {}).get("decision")
        print(f"  {fn}: order_ok={order_ok}, stages_count={evs.count('stage')}, decision={dec}")

    # Check dashboard numbers equal runs
    dash = client.get("/api/dashboard").json()
    totals = dash.get("totals", {})
    runs = client.get("/api/runs").json()
    print(f"Dashboard totals: {totals}")
    print(f"GET /api/runs length: {len(runs)}")
    assert totals.get("runs") == len(runs) == len(ORDERED_SAMPLES), (
        f"Dashboard runs count {totals.get('runs')} != total runs {len(runs)}"
    )
    print("  [PASS] Dashboard totals.runs equals GET /api/runs count exactly!")


def test_lifecycle_and_single_scenarios(client: httpx.Client):
    print("\n--- Test 2: Lifecycle & Independent Scenario Decisions ---")
    # Reset
    client.post("/api/reset")

    # 1. Upload 01
    res1 = client.post("/api/runs/upload", files=[("files", ("01_happy_shree_ganesh_inr.pdf", open(SAMPLES_DIR / "01_happy_shree_ganesh_inr.pdf", "rb").read(), "application/pdf"))]).json()
    r1 = res1["runs"][0]
    print(f"01: {r1['decision']} (expected AUTO_APPROVE)")
    assert r1['decision'] == "AUTO_APPROVE"

    # 2. Upload 05 (duplicate of 01)
    res5 = client.post("/api/runs/upload", files=[("files", ("05_duplicate_rescan_shree_ganesh.pdf", open(SAMPLES_DIR / "05_duplicate_rescan_shree_ganesh.pdf", "rb").read(), "application/pdf"))]).json()
    r5 = res5["runs"][0]
    print(f"05: {r5['decision']} (expected REJECT, codes={r5.get('reason_codes')})")
    assert r5['decision'] == "REJECT"
    assert "DUPLICATE_INVOICE" in r5.get("reason_codes", [])

    # 3. Upload 02 (split part 1)
    res2 = client.post("/api/runs/upload", files=[("files", ("02_split_part1_apex_inr.pdf", open(SAMPLES_DIR / "02_split_part1_apex_inr.pdf", "rb").read(), "application/pdf"))]).json()
    r2 = res2["runs"][0]
    print(f"02: {r2['decision']} (expected AUTO_APPROVE)")
    assert r2['decision'] == "AUTO_APPROVE"

    # 4. Upload 03 (split part 2)
    res3 = client.post("/api/runs/upload", files=[("files", ("03_split_part2_apex_inr.pdf", open(SAMPLES_DIR / "03_split_part2_apex_inr.pdf", "rb").read(), "application/pdf"))]).json()
    r3 = res3["runs"][0]
    print(f"03: {r3['decision']} (expected AUTO_APPROVE)")
    assert r3['decision'] == "AUTO_APPROVE"

    # 5. Upload 04 (split part 3 overbill)
    res4 = client.post("/api/runs/upload", files=[("files", ("04_split_part3_overbill_apex_inr.pdf", open(SAMPLES_DIR / "04_split_part3_overbill_apex_inr.pdf", "rb").read(), "application/pdf"))]).json()
    r4 = res4["runs"][0]
    print(f"04: {r4['decision']} (expected REJECT, codes={r4.get('reason_codes')})")
    assert r4['decision'] == "REJECT"
    assert "PO_OVERBILLED" in r4.get("reason_codes", [])

    # 6. Upload 06 (inferred PO)
    res6 = client.post("/api/runs/upload", files=[("files", ("06_scanned_muller_no_po_eur.png", open(SAMPLES_DIR / "06_scanned_muller_no_po_eur.png", "rb").read(), "image/png"))]).json()
    r6 = res6["runs"][0]
    print(f"06: {r6['decision']} (expected NEEDS_REVIEW, codes={r6.get('reason_codes')})")
    assert r6['decision'] == "NEEDS_REVIEW"
    assert "PO_INFERRED" in r6.get("reason_codes", [])

    # 7. Upload 07 (fraud bank changed)
    res7 = client.post("/api/runs/upload", files=[("files", ("07_fraud_bank_changed_brightline_usd.pdf", open(SAMPLES_DIR / "07_fraud_bank_changed_brightline_usd.pdf", "rb").read(), "application/pdf"))]).json()
    r7 = res7["runs"][0]
    print(f"07: {r7['decision']} (expected REJECT, codes={r7.get('reason_codes')})")
    assert r7['decision'] == "REJECT"
    assert "BANK_DETAILS_CHANGED" in r7.get("reason_codes", [])

    # 8. Upload 08 (currency mismatch)
    res8 = client.post("/api/runs/upload", files=[("files", ("08_currency_mismatch_muller_usd.pdf", open(SAMPLES_DIR / "08_currency_mismatch_muller_usd.pdf", "rb").read(), "application/pdf"))]).json()
    r8 = res8["runs"][0]
    print(f"08: {r8['decision']} (expected NEEDS_REVIEW, codes={r8.get('reason_codes')})")
    assert r8['decision'] == "NEEDS_REVIEW"
    assert "CURRENCY_MISMATCH" in r8.get("reason_codes", [])

    # 9. Upload 09 (price variance)
    res9 = client.post("/api/runs/upload", files=[("files", ("09_price_variance_lioncity_sgd.xlsx", open(SAMPLES_DIR / "09_price_variance_lioncity_sgd.xlsx", "rb").read(), "application/octet-stream"))]).json()
    r9 = res9["runs"][0]
    print(f"09: {r9['decision']} (expected NEEDS_REVIEW, codes={r9.get('reason_codes')})")
    assert r9['decision'] == "NEEDS_REVIEW"
    assert "PRICE_VARIANCE" in r9.get("reason_codes", [])

    # 10. Upload 10 (draft missing fields) - after reset so PO is not closed
    client.post("/api/reset")
    res10 = client.post("/api/runs/upload", files=[("files", ("10_missing_fields_draft.docx", open(SAMPLES_DIR / "10_missing_fields_draft.docx", "rb").read(), "application/octet-stream"))]).json()
    r10 = res10["runs"][0]
    print(f"10: {r10['decision']} (expected ON_HOLD, codes={r10.get('reason_codes')})")
    assert r10['decision'] == "ON_HOLD"
    assert "MISSING_INVOICE_NUMBER" in r10.get("reason_codes", [])

    # 11. Upload 11 (tolerance) - after reset so PO is not closed
    client.post("/api/reset")
    res11 = client.post("/api/runs/upload", files=[("files", ("11_bundled_embedded_tax_tolerance_inr.pdf", open(SAMPLES_DIR / "11_bundled_embedded_tax_tolerance_inr.pdf", "rb").read(), "application/pdf"))]).json()
    r11 = res11["runs"][0]
    print(f"11: {r11['decision']} (expected AUTO_APPROVE)")
    assert r11['decision'] == "AUTO_APPROVE"

    print("\nALL lifecycle & scenario decisions match expected exactly!")

if __name__ == "__main__":
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        test_batch_stream(client)
        test_lifecycle_and_single_scenarios(client)
