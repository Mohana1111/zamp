"""
Step 2: Upload every file in backend/data/sample_invoices via
POST /api/runs/upload-stream (SSE) and POST /api/runs/upload.
Verify:
- Event order: file_start -> stage* -> run_complete -> done
- Expected decisions:
  01: approve (AUTO_APPROVE)
  02: approve (AUTO_APPROVE)
  03: approve (AUTO_APPROVE)
  04: reject overbill (REJECT)
  05: reject duplicate (REJECT)
  06: review (NEEDS_REVIEW)
  07: reject bank change (REJECT)
  08: review currency (NEEDS_REVIEW)
  09: review price variance (NEEDS_REVIEW)
  10: hold (ON_HOLD)
  11: approve (AUTO_APPROVE)
- Dashboard numbers equal the runs count and statuses.
"""

import os
import sys
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

def parse_sse_events(text: str):
    """Parses raw SSE stream text into a list of parsed JSON objects."""
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    events.append(json.loads(payload))
                except Exception as e:
                    print(f"Failed to parse SSE payload: {payload[:100]}... Error: {e}")
    return events


def test_upload_stream(client: httpx.Client):
    print("\n=== Testing POST /api/runs/upload-stream (SSE) ===")
    failures = []

    # Reset state first
    r_reset = client.post("/api/reset")
    if r_reset.status_code != 200:
        failures.append(f"Reset before upload-stream failed: {r_reset.status_code}")
        return failures

    files_to_upload = []
    for filename in ORDERED_SAMPLES:
        p = SAMPLES_DIR / filename
        if not p.exists():
            failures.append(f"Sample file {filename} does not exist at {p}")
            continue
        # Read content
        with open(p, "rb") as f:
            content = f.read()
        # mime type
        mime = "application/pdf"
        if filename.endswith(".png"):
            mime = "image/png"
        elif filename.endswith(".xlsx"):
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif filename.endswith(".docx"):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        files_to_upload.append(("files", (filename, content, mime)))

    print(f"Uploading {len(files_to_upload)} files via /api/runs/upload-stream...")
    response = client.post(
        "/api/runs/upload-stream",
        files=files_to_upload,
        timeout=180.0,
    )

    if response.status_code != 200:
        failures.append(f"upload-stream returned status {response.status_code}: {response.text[:300]}")
        return failures

    events = parse_sse_events(response.text)
    print(f"Received {len(events)} SSE events.")

    # Verify event order: file_start -> stage* -> run_complete -> done
    event_types = [e.get("type") for e in events if e.get("type") != "ping"]
    if not event_types or event_types[-1] != "done":
        failures.append(f"SSE stream did not terminate with 'done'. Last event: {event_types[-1] if event_types else 'None'}")

    # Track sequence per file
    file_events = {}
    completed_runs = {}

    for ev in events:
        ev_type = ev.get("type")
        fname = ev.get("file")
        if not fname:
            continue
        if fname not in file_events:
            file_events[fname] = []
        file_events[fname].append(ev_type)

        if ev_type == "run_complete":
            run = ev.get("run", {})
            completed_runs[fname] = run

    print("\nChecking event order per file:")
    for fname in ORDERED_SAMPLES:
        seq = file_events.get(fname, [])
        prefix = fname[:2]
        if not seq:
            failures.append(f"No events received for file: {fname}")
            continue

        has_file_start = "file_start" in seq
        has_stages = "stage" in seq
        has_run_complete = "run_complete" in seq

        # Check order
        start_idx = seq.index("file_start") if has_file_start else -1
        stage_indices = [i for i, x in enumerate(seq) if x == "stage"]
        comp_idx = seq.index("run_complete") if has_run_complete else -1

        valid_order = (
            start_idx != -1
            and len(stage_indices) > 0
            and comp_idx != -1
            and start_idx < stage_indices[0]
            and stage_indices[-1] < comp_idx
        )

        if not valid_order:
            failures.append(f"Invalid event sequence for {fname}: {seq}")
            print(f"  [FAIL] {fname}: sequence {seq}")
        else:
            print(f"  [PASS] {fname}: file_start -> {len(stage_indices)} stages -> run_complete")

        # Check decision
        run = completed_runs.get(fname, {})
        actual_decision = run.get("decision")
        expected_decision = EXPECTED_DECISIONS.get(prefix)

        if actual_decision != expected_decision:
            failures.append(
                f"File {fname} decision mismatch: expected {expected_decision}, got {actual_decision}. "
                f"Reason: {run.get('decision_reason')}"
            )
            print(f"  [FAIL] {fname}: expected {expected_decision}, got {actual_decision} (Reason: {run.get('decision_reason')})")
        else:
            print(f"  [PASS] {fname}: decision={actual_decision} (Reason: {run.get('decision_reason')})")

    # Check dashboard numbers vs runs
    dash_res = client.get("/api/dashboard")
    if dash_res.status_code != 200:
        failures.append(f"Dashboard endpoint returned {dash_res.status_code}")
    else:
        dash_data = dash_res.json()
        total_invoices = dash_data.get("total_invoices") or dash_data.get("total_runs", 0)
        auto_approved = dash_data.get("auto_approved", 0)
        flagged_review = dash_data.get("flagged_review", 0)
        rejected = dash_data.get("rejected", 0)
        on_hold = dash_data.get("on_hold", 0)

        # Count actual from runs
        actual_total = len(completed_runs)
        actual_approved = sum(1 for r in completed_runs.values() if r.get("decision") in ("AUTO_APPROVE", "APPROVE"))
        actual_review = sum(1 for r in completed_runs.values() if r.get("decision") == "NEEDS_REVIEW")
        actual_rejected = sum(1 for r in completed_runs.values() if r.get("decision") == "REJECT")
        actual_hold = sum(1 for r in completed_runs.values() if r.get("decision") == "ON_HOLD")

        print(f"\nDashboard vs Runs Verification:")
        print(f"  Total: dashboard={total_invoices}, actual={actual_total}")
        print(f"  Auto-approved: dashboard={auto_approved}, actual={actual_approved}")
        print(f"  Review: dashboard={flagged_review}, actual={actual_review}")
        print(f"  Rejected: dashboard={rejected}, actual={actual_rejected}")
        print(f"  On Hold: dashboard={on_hold}, actual={actual_hold}")

        if total_invoices != actual_total:
            failures.append(f"Dashboard total_invoices ({total_invoices}) != completed runs ({actual_total})")
        if auto_approved != actual_approved:
            failures.append(f"Dashboard auto_approved ({auto_approved}) != actual ({actual_approved})")
        if flagged_review != actual_review:
            failures.append(f"Dashboard flagged_review ({flagged_review}) != actual ({actual_review})")
        if rejected != actual_rejected:
            failures.append(f"Dashboard rejected ({rejected}) != actual ({actual_rejected})")
        if on_hold != actual_hold:
            failures.append(f"Dashboard on_hold ({on_hold}) != actual ({actual_hold})")

    return failures


def test_upload_sync(client: httpx.Client):
    print("\n=== Testing POST /api/runs/upload (Sync) ===")
    failures = []

    # Reset state first
    r_reset = client.post("/api/reset")
    if r_reset.status_code != 200:
        failures.append(f"Reset before upload sync failed: {r_reset.status_code}")
        return failures

    files_to_upload = []
    for filename in ORDERED_SAMPLES:
        p = SAMPLES_DIR / filename
        with open(p, "rb") as f:
            content = f.read()
        mime = "application/pdf"
        if filename.endswith(".png"):
            mime = "image/png"
        elif filename.endswith(".xlsx"):
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif filename.endswith(".docx"):
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        files_to_upload.append(("files", (filename, content, mime)))

    print(f"Uploading {len(files_to_upload)} files via POST /api/runs/upload...")
    response = client.post(
        "/api/runs/upload",
        files=files_to_upload,
        timeout=180.0,
    )

    if response.status_code != 200:
        failures.append(f"upload returned status {response.status_code}: {response.text[:300]}")
        return failures

    data = response.json()
    runs = data.get("runs", [])
    print(f"Received {len(runs)} runs in sync response.")

    run_by_filename = {}
    for r in runs:
        # extract filename from file_path or metadata
        src = r.get("source_info", {})
        fp = src.get("file_name") or Path(src.get("file_path", "")).name
        run_by_filename[fp] = r

    for filename in ORDERED_SAMPLES:
        prefix = filename[:2]
        run = run_by_filename.get(filename)
        if not run:
            failures.append(f"Missing run result for {filename} in sync upload")
            continue
        actual_decision = run.get("decision")
        expected_decision = EXPECTED_DECISIONS.get(prefix)
        if actual_decision != expected_decision:
            failures.append(f"Sync upload {filename}: expected {expected_decision}, got {actual_decision}")
            print(f"  [FAIL] {filename}: expected {expected_decision}, got {actual_decision}")
        else:
            print(f"  [PASS] {filename}: decision={actual_decision}")

    return failures


if __name__ == "__main__":
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        stream_failures = test_upload_stream(client)
        sync_failures = test_upload_sync(client)

    all_failures = stream_failures + sync_failures
    print(f"\n==========================================")
    print(f"Step 2 Completed with {len(all_failures)} failure(s)")
    if all_failures:
        for f in all_failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL Step 2 checks PASSED cleanly!")
        sys.exit(0)
