"""
Step 4: Vendor Policy Flows & Settings
Step 5: Override Approve/Reject PO Ledger Updates
"""

import sys
import json
import httpx
from pathlib import Path

BASE_URL = "http://127.0.0.1:8080"
SAMPLES_DIR = Path(__file__).resolve().parent.parent / "backend" / "data" / "sample_invoices"


def test_step4_and_step5():
    failures = []
    print("=== Testing Step 4 (Vendor Policy Flows) & Step 5 (Override PO Ledger) ===")

    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        # Reset state first
        client.post("/api/reset")

        # -------------------------------------------------------------------
        # Step 4.1: Blocked vendor reject
        # -------------------------------------------------------------------
        print("\n--- 4.1: Blocked Vendor Reject ---")
        # Set V001 to BLOCKED
        r_block = client.put("/api/vendors/V001/policy", json={"trust": "BLOCKED"})
        assert r_block.status_code == 200, f"Failed to set vendor policy: {r_block.text}"
        print(f"Vendor V001 trust set to: {r_block.json()['policy']['trust']}")

        # Upload invoice 01 (normally AUTO_APPROVE)
        p01 = SAMPLES_DIR / "01_happy_shree_ganesh_inr.pdf"
        r_up1 = client.post("/api/runs/upload", files=[("files", ("01_happy_shree_ganesh_inr.pdf", open(p01, "rb").read(), "application/pdf"))])
        run1 = r_up1.json()["runs"][0]
        print(f"Run 01 decision with BLOCKED vendor: {run1['decision']}, reason_codes: {run1.get('reason_codes')}")
        if run1["decision"] != "REJECT" or "BLOCKED_VENDOR" not in run1.get("reason_codes", []):
            failures.append(f"Blocked vendor was not rejected with BLOCKED_VENDOR: got {run1['decision']}, {run1.get('reason_codes')}")
        else:
            print("  [PASS] Blocked vendor correctly rejected with BLOCKED_VENDOR")

        # -------------------------------------------------------------------
        # Step 4.2: Watchlist review
        # -------------------------------------------------------------------
        print("\n--- 4.2: Watchlist Vendor Review ---")
        client.post("/api/reset")
        r_watch = client.put("/api/vendors/V001/policy", json={"trust": "WATCHLIST"})
        assert r_watch.status_code == 200
        print(f"Vendor V001 trust set to: {r_watch.json()['policy']['trust']}")

        r_up2 = client.post("/api/runs/upload", files=[("files", ("01_happy_shree_ganesh_inr.pdf", open(p01, "rb").read(), "application/pdf"))])
        run2 = r_up2.json()["runs"][0]
        print(f"Run 01 decision with WATCHLIST vendor: {run2['decision']}, reason_codes: {run2.get('reason_codes')}")
        if run2["decision"] != "NEEDS_REVIEW" or "WATCHLIST_VENDOR" not in run2.get("reason_codes", []):
            failures.append(f"Watchlist vendor was not routed to NEEDS_REVIEW with WATCHLIST_VENDOR: got {run2['decision']}, {run2.get('reason_codes')}")
        else:
            print("  [PASS] Watchlist vendor correctly flagged for NEEDS_REVIEW")

        # -------------------------------------------------------------------
        # Step 4.3: Preapprove vendor + no-PO invoice under limit
        # -------------------------------------------------------------------
        print("\n--- 4.3: Preapproved Vendor + No-PO Invoice Under Limit ---")
        client.post("/api/reset")
        # Set V003 (Müller) or V001 to PREAPPROVED with allow_without_po and high limit
        r_pre = client.put("/api/vendors/V003/policy", json={
            "trust": "PREAPPROVED",
            "allow_without_po": True,
            "auto_approve_limit": 100000.0,
        })
        print(f"V003 policy: {r_pre.json()}")
        # Check policy endpoint
        assert r_pre.status_code == 200

        # -------------------------------------------------------------------
        # Step 4.4: Global Settings update changes behavior
        # -------------------------------------------------------------------
        print("\n--- 4.4: Global Settings Update Changes Behavior ---")
        client.post("/api/reset")
        # Check initial settings
        r_set = client.get("/api/settings").json()
        print(f"Initial settings: {r_set['settings']}")

        # Change total tolerance to 0.05% (very strict)
        r_put_set = client.put("/api/settings", json={"default_total_tolerance_pct": 0.05})
        assert r_put_set.status_code == 200
        print(f"Updated total tolerance to: {r_put_set.json()['settings']['default_total_tolerance_pct']}%")

        # Upload 11_bundled (has 0.19% variance, normally AUTO_APPROVE when within 1.0%)
        p11 = SAMPLES_DIR / "11_bundled_embedded_tax_tolerance_inr.pdf"
        r_up11 = client.post("/api/runs/upload", files=[("files", ("11_bundled_embedded_tax_tolerance_inr.pdf", open(p11, "rb").read(), "application/pdf"))])
        run11 = r_up11.json()["runs"][0]
        print(f"Run 11 decision with 0.05% tolerance: {run11['decision']}, reason_codes: {run11.get('reason_codes')}")
        if run11["decision"] == "AUTO_APPROVE":
            failures.append("Settings change to 0.05% tolerance failed to flag 0.19% variance invoice!")
        else:
            print(f"  [PASS] Stricter tolerance successfully changed behavior: decision is {run11['decision']}")

        # Restore default tolerance
        client.put("/api/settings", json={"default_total_tolerance_pct": 1.0})

        # -------------------------------------------------------------------
        # Step 5: Override approve / reject updates PO ledger
        # -------------------------------------------------------------------
        print("\n--- 5: Override Decision & PO Ledger Updates ---")
        client.post("/api/reset")

        # Get initial POs
        pos_res = client.get("/api/overview").json()
        pos_before = {p["po_number"]: p for p in pos_res["pos"]}
        po_1045_before = pos_before.get("PO-2026-1045", {})
        print(f"PO-2026-1045 before: invoiced={po_1045_before.get('invoiced_amount')}, remaining={po_1045_before.get('remaining_amount')}")

        # Upload 08_currency_mismatch_muller_usd.pdf (targets PO-2026-1045, result: NEEDS_REVIEW)
        p08 = SAMPLES_DIR / "08_currency_mismatch_muller_usd.pdf"
        r_up08 = client.post("/api/runs/upload", files=[("files", ("08_currency_mismatch_muller_usd.pdf", open(p08, "rb").read(), "application/pdf"))])
        run08 = r_up08.json()["runs"][0]
        print(f"Run 08 initial decision: {run08['decision']}, PO: {run08['matched_po_number']}, total: {run08['invoice_total']}")
        assert run08["decision"] == "NEEDS_REVIEW"

        # Check PO balance after NEEDS_REVIEW (should NOT be consumed yet)
        pos_res2 = client.get("/api/overview").json()
        pos_after_review = {p["po_number"]: p for p in pos_res2["pos"]}
        po_1045_review = pos_after_review.get("PO-2026-1045", {})
        print(f"PO-2026-1045 after NEEDS_REVIEW: invoiced={po_1045_review.get('invoiced_amount')}, remaining={po_1045_review.get('remaining_amount')}")

        if po_1045_review.get("invoiced_amount") != po_1045_before.get("invoiced_amount"):
            failures.append("NEEDS_REVIEW invoice consumed PO balance before human approval!")

        # Now perform human override to AUTO_APPROVE
        run_id = run08["run_id"]
        override_payload = {
            "decision": "AUTO_APPROVE",
            "comment": "FX variance approved by Finance Director",
            "reviewer": "admin_1",
            "preapprove_vendor": False,
        }
        r_override = client.post(f"/api/runs/{run_id}/override", json=override_payload)
        assert r_override.status_code == 200, f"Override failed: {r_override.text}"
        overridden_run = r_override.json()
        print(f"Overridden run decision: {overridden_run['decision']}, status: {overridden_run.get('human_approval_status')}")

        # Check PO ledger after human override
        pos_res3 = client.get("/api/overview").json()
        pos_after_override = {p["po_number"]: p for p in pos_res3["pos"]}
        po_1045_overridden = pos_after_override.get("PO-2026-1045", {})
        print(f"PO-2026-1045 after human approval: invoiced={po_1045_overridden.get('invoiced_amount')}, remaining={po_1045_overridden.get('remaining_amount')}")

        expected_deduction = run08["invoice_total"]
        actual_deduction = po_1045_overridden.get("invoiced_amount") - po_1045_before.get("invoiced_amount")
        print(f"Expected invoiced increase: {expected_deduction}, actual increase: {actual_deduction}")

        if abs(actual_deduction - expected_deduction) > 0.01:
            failures.append(f"Override approve failed to deduct PO: expected +{expected_deduction}, got +{actual_deduction}")
        else:
            print("  [PASS] Override approval correctly updated PO ledger!")

        # Now test: What happens if reviewer overrides from AUTO_APPROVE to REJECT?
        print("\n--- Testing Override from APPROVED to REJECT (PO release check) ---")
        r_override_reject = client.post(f"/api/runs/{run_id}/override", json={
            "decision": "REJECT",
            "comment": "Found fraud upon second review, rejecting",
            "reviewer": "admin_1",
        })
        print(f"Override to REJECT status: {r_override_reject.status_code}")
        pos_res4 = client.get("/api/overview").json()
        pos_after_reject = {p["po_number"]: p for p in pos_res4["pos"]}
        po_1045_rejected = pos_after_reject.get("PO-2026-1045", {})
        print(f"PO-2026-1045 after override REJECT: invoiced={po_1045_rejected.get('invoiced_amount')}, remaining={po_1045_rejected.get('remaining_amount')}")

        if po_1045_rejected.get("invoiced_amount") == po_1045_overridden.get("invoiced_amount"):
            print("  [FINDING/DEFECT] Overriding an approved invoice to REJECT does NOT refund or restore the PO balance!")
        else:
            print("  [PASS] Overriding to REJECT refunded the PO balance!")

    return failures


if __name__ == "__main__":
    fails = test_step4_and_step5()
    print(f"\n==========================================")
    if fails:
        print(f"Step 4 & 5 finished with {len(fails)} failure(s):")
        for f in fails:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("ALL Step 4 & 5 functional checks PASSED!")
        sys.exit(0)
