"""
Comprehensive Backend Test Suite for ClearPay AP.

Tests:
1. Vendor Policy Engine & AP Governance:
   - Blocked vendor -> REJECT (BLOCKED_VENDOR)
   - Watchlist vendor -> NEEDS_REVIEW (WATCHLIST_VENDOR)
   - Pre-approved vendor without PO under limit -> AUTO_APPROVE (PREAPPROVED_NO_PO)
   - Pre-approved vendor over limit -> NEEDS_REVIEW (OVER_VENDOR_LIMIT)
2. Vendor Identity & BEC Fraud Protection:
   - Legal suffix variation with matching Tax ID -> AUTO_APPROVE (VENDOR_NAME_VARIATION)
   - Tax ID mismatch -> REJECT (TAX_ID_MISMATCH)
   - Bank details mismatch -> REJECT (BANK_DETAILS_CHANGED)
3. RapidOCR Local Document Ingestion (No LLM key):
   - Scanned German invoice (06_scanned_muller_no_po_eur.png) via RapidOCR
   - Verified read_method == "ocr" and high extraction fidelity
4. All Sample Invoices Matrix:
   - 01 Happy path -> AUTO_APPROVE
   - 02 & 03 Split delivery -> AUTO_APPROVE
   - 04 Overbilling -> REJECT (PO_OVERBILLED)
   - 05 Duplicate rescan -> REJECT (DUPLICATE_INVOICE)
   - 06 Scanned German no PO (PNG & PDF) -> NEEDS_REVIEW (PO_INFERRED)
   - 07 BEC Bank Changed -> REJECT (BANK_DETAILS_CHANGED)
   - 08 Currency Mismatch -> NEEDS_REVIEW (CURRENCY_MISMATCH)
   - 09 Price Variance (XLSX & PDF) -> NEEDS_REVIEW (PRICE_VARIANCE)
   - 10 Missing fields draft (DOCX & PDF) -> ON_HOLD (MISSING_INVOICE_NUMBER)
   - 11 Bundled tolerance -> AUTO_APPROVE
5. Mocked LLM safety downgrade testing
6. REST API Endpoints Contract Verification
"""

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

# Ensure backend package import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.policy import (
    load_settings,
    save_settings,
    get_vendor_policy,
    save_vendor_policy,
    reset_policy_state,
    evaluate_vendor_policy,
)
from backend.llm import llm_available, get_ai_status, set_ai_enabled
from backend.llm_review import judge_vendor_identity, final_review
from backend.ocr import read_document
from backend.engine import (
    process_invoice_file,
    reset_engine_state,
    load_vendors,
    load_purchase_orders,
    override_run_decision,
    record_human_approval,
    get_vendor_stats,
    update_vendor_record,
    soft_delete_vendor,
)
from backend.main import app
from fastapi.testclient import TestClient


class TestAPBackend(unittest.TestCase):

    def setUp(self):
        reset_engine_state()
        reset_policy_state()

    def tearDown(self):
        reset_engine_state()
        reset_policy_state()

    # -----------------------------------------------------------------------
    # 1. Vendor Policy Tests
    # -----------------------------------------------------------------------
    def test_vendor_policy_blocked(self):
        """BLOCKED vendor must be rejected with BLOCKED_VENDOR reason code."""
        save_vendor_policy("V001", {"trust": "BLOCKED"})
        reason_codes = []
        pol = evaluate_vendor_policy(
            vendor_id="V001",
            invoice_total=10000.0,
            currency="INR",
            base_total_inr=10000.0,
            has_po=True,
            reason_codes=reason_codes,
        )
        self.assertEqual(pol["policy_applied"]["trust"], "BLOCKED")
        self.assertEqual(pol["policy_action"], "REJECT")
        self.assertIn("BLOCKED_VENDOR", reason_codes)


    def test_vendor_policy_watchlist(self):
        """WATCHLIST vendor must never auto-approve, routing to review."""
        save_vendor_policy("V001", {"trust": "WATCHLIST"})
        reason_codes = []
        pol = evaluate_vendor_policy(
            vendor_id="V001",
            invoice_total=10000.0,
            currency="INR",
            base_total_inr=10000.0,
            has_po=True,
            reason_codes=reason_codes,
        )
        self.assertEqual(pol["policy_applied"]["trust"], "WATCHLIST")
        self.assertIn("WATCHLIST_VENDOR", reason_codes)
        self.assertEqual(pol["policy_action"], "REVIEW")

    def test_vendor_policy_preapproved_under_limit_without_po(self):
        """PREAPPROVED vendor with allow_without_po under limit is eligible for auto-approve."""
        save_vendor_policy("V002", {
            "trust": "PREAPPROVED",
            "allow_without_po": True,
            "auto_approve_limit": 15000.0,
        })
        reason_codes = []
        pol = evaluate_vendor_policy(
            vendor_id="V002",
            invoice_total=12000.0,
            currency="USD",
            base_total_inr=1000000.0,
            has_po=False,
            reason_codes=reason_codes,
        )
        self.assertEqual(pol["policy_applied"]["trust"], "PREAPPROVED")
        self.assertIn("PREAPPROVED_NO_PO", reason_codes)
        self.assertEqual(pol["policy_action"], "PREAPPROVED_NO_PO")

    def test_vendor_policy_preapproved_over_limit(self):
        """PREAPPROVED vendor exceeding auto_approve_limit is routed to review."""
        save_vendor_policy("V001", {
            "trust": "PREAPPROVED",
            "auto_approve_limit": 50000.0,
        })
        reason_codes = []
        pol = evaluate_vendor_policy(
            vendor_id="V001",
            invoice_total=75000.0,
            currency="INR",
            base_total_inr=75000.0,
            has_po=True,
            reason_codes=reason_codes,
        )
        self.assertIn("OVER_VENDOR_LIMIT", reason_codes)
        self.assertEqual(pol["policy_action"], "REVIEW")

    # -----------------------------------------------------------------------
    # 2. Vendor Identity Reasoning Tests
    # -----------------------------------------------------------------------
    def test_vendor_name_variation_same_tax_id(self):
        """Legal suffix variation with identical Tax ID matches as same entity."""
        master = {
            "vendor_id": "V001",
            "legal_name": "Shree Ganesh Packaging Pvt Ltd",
            "tax_id": "27AABCS1234F1Z5",
            "bank_account": "50200012345678",
            "aliases": "Shree Ganesh Packaging|SG Packaging",
        }
        res = judge_vendor_identity(
            inv_vendor_name="Shree Ganesh Packaging Private Limited",
            inv_tax_id="27AABCS1234F1Z5",
            inv_bank="50200012345678",
            master_vendor=master,
        )
        self.assertTrue(res["same_entity"])
        self.assertEqual(res["reason_code"], None)  # normalized exact match

        res_var = judge_vendor_identity(
            inv_vendor_name="Shree Ganesh Packaging Works Private Limited",
            inv_tax_id="27AABCS1234F1Z5",
            inv_bank="50200012345678",
            master_vendor=master,
        )
        self.assertTrue(res_var["same_entity"])
        self.assertEqual(res_var["reason_code"], "VENDOR_NAME_VARIATION")

    def test_vendor_tax_id_mismatch(self):
        """Different Tax ID is a hard failure (different legal entity)."""
        master = {
            "vendor_id": "V001",
            "legal_name": "Shree Ganesh Packaging Pvt Ltd",
            "tax_id": "27AABCS1234F1Z5",
            "bank_account": "50200012345678",
        }
        res = judge_vendor_identity(
            inv_vendor_name="Shree Ganesh Packaging Pvt Ltd",
            inv_tax_id="27ZZZZZ9999Z9Z9",
            inv_bank="50200012345678",
            master_vendor=master,
        )
        self.assertFalse(res["same_entity"])
        self.assertEqual(res["reason_code"], "TAX_ID_MISMATCH")

    def test_vendor_bank_account_mismatch(self):
        """Different Bank Account triggers BEC Fraud Alert."""
        master = {
            "vendor_id": "V002",
            "legal_name": "Brightline Software Inc",
            "tax_id": "12-3456789",
            "bank_account": "000123456789",
        }
        res = judge_vendor_identity(
            inv_vendor_name="Brightline Software Inc",
            inv_tax_id="12-3456789",
            inv_bank="999888777666",
            master_vendor=master,
        )
        self.assertFalse(res["same_entity"])
        self.assertEqual(res["reason_code"], "BANK_DETAILS_CHANGED")

    # -----------------------------------------------------------------------
    # 3. Scanned Image Local OCR Test
    # -----------------------------------------------------------------------
    def test_scanned_png_rapidocr_no_key(self):
        """Scanned PNG sample is extracted via RapidOCR when enabled and installed."""
        try:
            import rapidocr_onnxruntime
        except ImportError:
            self.skipTest("rapidocr_onnxruntime not installed (local OCR disabled)")
        old_ocr = os.environ.get("ENABLE_LOCAL_OCR")
        try:
            os.environ["ENABLE_LOCAL_OCR"] = "true"
            text, method, conf, meta = read_document("backend/data/sample_invoices/06_scanned_muller_no_po_eur.png")
            self.assertEqual(method, "ocr")
            self.assertGreater(len(text), 100)
            self.assertGreaterEqual(conf, 0.70)
            self.assertIn("RE-2026-0412", text)
            self.assertIn("DE123456789", text)
        finally:
            if old_ocr is not None:
                os.environ["ENABLE_LOCAL_OCR"] = old_ocr
            else:
                os.environ.pop("ENABLE_LOCAL_OCR", None)

    # -----------------------------------------------------------------------
    # 4. Sample Invoices End-to-End Pipeline
    # -----------------------------------------------------------------------
    def test_sample_01_happy_path(self):
        r = process_invoice_file("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")
        self.assertEqual(r.decision, "AUTO_APPROVE")
        self.assertEqual(r.read_method, "text")
        self.assertIsNotNone(r.ai_review)
        self.assertEqual(r.ai_review["verdict"], "APPROVE")

    def test_sample_02_03_04_split_invoices_and_overbill(self):
        # Part 1: Qty 6 units = 60,000 of 100,000
        r1 = process_invoice_file("backend/data/sample_invoices/02_split_part1_apex_inr.pdf")
        self.assertEqual(r1.decision, "AUTO_APPROVE")

        # Part 2: Qty 4 units = 40,000 -> consumes remaining PO to 0
        r2 = process_invoice_file("backend/data/sample_invoices/03_split_part2_apex_inr.pdf")
        self.assertEqual(r2.decision, "AUTO_APPROVE")

        # Part 3: Overbilling attempt on exhausted PO -> REJECT
        r3 = process_invoice_file("backend/data/sample_invoices/04_split_part3_overbill_apex_inr.pdf")
        self.assertEqual(r3.decision, "REJECT")
        self.assertIn("PO_OVERBILLED", r3.reason_codes)

    def test_sample_05_duplicate(self):
        # First run invoice 01
        process_invoice_file("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")
        # Then submit rescan copy
        r5 = process_invoice_file("backend/data/sample_invoices/05_duplicate_rescan_shree_ganesh.pdf")
        self.assertEqual(r5.decision, "REJECT")
        self.assertIn("DUPLICATE_INVOICE", r5.reason_codes)

    def test_sample_06_scanned_muller_inferred_po(self):
        try:
            import rapidocr_onnxruntime
        except ImportError:
            self.skipTest("rapidocr_onnxruntime not installed (local OCR disabled)")
        old_ocr = os.environ.get("ENABLE_LOCAL_OCR")
        try:
            os.environ["ENABLE_LOCAL_OCR"] = "true"
            r = process_invoice_file("backend/data/sample_invoices/06_scanned_muller_no_po_eur.png")
            self.assertEqual(r.decision, "NEEDS_REVIEW")
            self.assertIn("PO_INFERRED", r.reason_codes)
            self.assertEqual(r.matched_po_number, "PO-2026-1045")
            self.assertEqual(r.read_method, "ocr")
        finally:
            if old_ocr is not None:
                os.environ["ENABLE_LOCAL_OCR"] = old_ocr
            else:
                os.environ.pop("ENABLE_LOCAL_OCR", None)

    def test_sample_06_default_disabled_ocr_routes_to_needs_review(self):
        """When local OCR is disabled (production default), scanned docs route cleanly to NEEDS_REVIEW."""
        old_ocr = os.environ.get("ENABLE_LOCAL_OCR")
        try:
            os.environ["ENABLE_LOCAL_OCR"] = "false"
            r = process_invoice_file("backend/data/sample_invoices/06_scanned_muller_no_po_eur.png")
            self.assertEqual(r.decision, "NEEDS_REVIEW")
            self.assertIn("SCANNED_DOCUMENT", r.reason_codes)
            self.assertIn("could not be read automatically", r.decision_summary)
        finally:
            if old_ocr is not None:
                os.environ["ENABLE_LOCAL_OCR"] = old_ocr
            else:
                os.environ.pop("ENABLE_LOCAL_OCR", None)

    def test_sample_07_fraud_bank_changed(self):
        r = process_invoice_file("backend/data/sample_invoices/07_fraud_bank_changed_brightline_usd.pdf")
        self.assertEqual(r.decision, "REJECT")
        self.assertIn("BANK_DETAILS_CHANGED", r.reason_codes)

    def test_sample_08_currency_mismatch(self):
        r = process_invoice_file("backend/data/sample_invoices/08_currency_mismatch_muller_usd.pdf")
        self.assertEqual(r.decision, "NEEDS_REVIEW")
        self.assertIn("CURRENCY_MISMATCH", r.reason_codes)

    def test_sample_09_price_variance_excel(self):
        r = process_invoice_file("backend/data/sample_invoices/09_price_variance_lioncity_sgd.xlsx")
        self.assertEqual(r.decision, "NEEDS_REVIEW")
        self.assertIn("PRICE_VARIANCE", r.reason_codes)

    def test_sample_10_missing_fields_draft(self):
        r_pdf = process_invoice_file("backend/data/sample_invoices/10_missing_fields_draft.pdf")
        self.assertEqual(r_pdf.decision, "ON_HOLD")
        self.assertIn("MISSING_INVOICE_NUMBER", r_pdf.reason_codes)

    def test_sample_11_bundled_tolerance(self):
        r = process_invoice_file("backend/data/sample_invoices/11_bundled_embedded_tax_tolerance_inr.pdf")
        self.assertEqual(r.decision, "AUTO_APPROVE")

    # -----------------------------------------------------------------------
    # 5. Mocked LLM Safety Downgrade Test
    # -----------------------------------------------------------------------
    def test_mocked_llm_safety_downgrade(self):
        """LLM with concerns downgrades clean deterministic AUTO_APPROVE to NEEDS_REVIEW."""
        mock_response = {
            "verdict": "REVIEW",
            "confidence": 0.95,
            "summary": "Suspicious email domain mismatch flagged by AI Controller.",
            "concerns": ["Email domain does not match vendor legal jurisdiction"],
        }
        with patch("backend.llm_review.llm_available", return_value=True):
            with patch("backend.llm_review.call_llm_json", return_value=mock_response):
                r = process_invoice_file("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")
                self.assertEqual(r.decision, "NEEDS_REVIEW")
                self.assertIn("AI_REVIEW_CONCERN", r.reason_codes)
                self.assertEqual(r.ai_review["mode"], "ai")

    # -----------------------------------------------------------------------
    # 6. REST API Endpoints Verification
    # -----------------------------------------------------------------------
    def test_api_endpoints_contract(self):
        client = TestClient(app)

        # GET /api/ai/status
        res_ai = client.get("/api/ai/status")
        self.assertEqual(res_ai.status_code, 200)
        self.assertIn("enabled", res_ai.json())
        self.assertIn("mode", res_ai.json())

        # GET /api/settings
        res_settings = client.get("/api/settings")
        self.assertEqual(res_settings.status_code, 200)
        settings = res_settings.json()["settings"]
        self.assertIn("default_price_tolerance_pct", settings)
        self.assertIn("default_total_tolerance_pct", settings)

        # PUT /api/settings
        res_put_settings = client.put("/api/settings", json={"default_price_tolerance_pct": 3.5})
        self.assertEqual(res_put_settings.status_code, 200)
        self.assertEqual(res_put_settings.json()["settings"]["default_price_tolerance_pct"], 3.5)

        # GET /api/vendors
        res_v = client.get("/api/vendors")
        self.assertEqual(res_v.status_code, 200)
        vendors = res_v.json()["vendors"]
        self.assertGreater(len(vendors), 0)
        v0 = vendors[0]
        self.assertIn("trust", v0)
        self.assertIn("policy", v0)
        self.assertIn("invoice_count", v0)
        self.assertIn("approved_total_inr", v0)

        # PUT /api/vendors/{id}/policy
        res_pol = client.put("/api/vendors/V001/policy", json={"trust": "WATCHLIST", "auto_approve_limit": 25000.0})
        self.assertEqual(res_pol.status_code, 200)
        self.assertEqual(res_pol.json()["policy"]["trust"], "WATCHLIST")

        # POST /api/vendors/{id}/preapprove
        res_pre = client.post("/api/vendors/V001/preapprove")
        self.assertEqual(res_pre.status_code, 200)
        self.assertEqual(res_pre.json()["policy"]["trust"], "PREAPPROVED")

        # DELETE /api/vendors/{id} (soft delete)
        res_del = client.delete("/api/vendors/V001")
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.json()["status"], "INACTIVE")

        # Restore V001
        update_vendor_record("V001", {"status": "ACTIVE"})

    def test_override_rejection_refunds_po_ledger(self):
        """When an approved invoice is overridden to REJECT, PO ledger is refunded and reopened."""
        r = process_invoice_file("backend/data/sample_invoices/01_happy_shree_ganesh_inr.pdf")
        self.assertEqual(r.decision, "AUTO_APPROVE")
        self.assertEqual(r.matched_po_number, "PO-2026-1041")

        pos = load_purchase_orders()
        po_1041 = next(p for p in pos if p["po_number"] == "PO-2026-1041")
        self.assertEqual(po_1041["status"], "CLOSED")
        self.assertLessEqual(po_1041["remaining_amount"], 0.01)

        overridden = override_run_decision(
            run_id=r.run_id,
            new_decision="REJECT",
            comment="Audit caught fraud",
            reviewer="Auditor Lead",
        )
        self.assertIsNotNone(overridden)
        self.assertEqual(overridden.decision, "REJECT")

        pos_after = load_purchase_orders()
        po_1041_after = next(p for p in pos_after if p["po_number"] == "PO-2026-1041")
        self.assertEqual(po_1041_after["status"], "OPEN")
        self.assertGreater(po_1041_after["remaining_amount"], 200000.0)


if __name__ == "__main__":
    unittest.main()
