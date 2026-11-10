"""
LLM Reasoning & AP Controller Review Layer.

Provides:
- judge_vendor_identity: Evaluates entity matching with exact tax ID/bank validation and name suffix tolerance.
- final_review: Conservative AP safety review returning structured checks and business concerns.
- explain_decision: Plain English 2-3 sentence executive decision explanation.
"""

import re
import difflib
import unicodedata
from typing import Dict, Any, Optional, List, Tuple

from backend.llm import llm_available, call_llm_json


def _strip_accents(text: str) -> str:
    """Removes diacritics and accents (e.g., Müller -> Muller)."""
    if not text:
        return ""
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c))


def _normalize_vendor_name(name: str) -> str:
    """Normalizes vendor name by stripping accents, punctuation, and expanding legal suffixes."""
    if not name:
        return ""
    s = _strip_accents(name).lower()
    # Strip punctuation
    s = re.sub(r"[^\w\s]", " ", s)
    # Common suffix substitutions
    s = re.sub(r"\bprivate\s+limited\b", "pvt ltd", s)
    s = re.sub(r"\bpvt\s+ltd\b", "pvt ltd", s)
    s = re.sub(r"\bincorporated\b", "inc", s)
    s = re.sub(r"\bcorporation\b", "corp", s)
    s = re.sub(r"\blimited\b", "ltd", s)
    s = re.sub(r"\bgesellschaft\s+mit\s+beschrankter\s+haftung\b", "gmbh", s)
    s = re.sub(r"\bges\s*m\s*b\s*h\b", "gmbh", s)
    s = re.sub(r"\bpte\s+ltd\b", "pte ltd", s)
    # Collapse multiple whitespaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _clean_id(val: Optional[str]) -> str:
    """Removes dashes, slashes, spaces from identifiers."""
    if not val:
        return ""
    return re.sub(r"[\s\-_/.]", "", str(val)).upper()


def judge_vendor_identity(
    inv_vendor_name: str,
    inv_tax_id: Optional[str],
    inv_bank: Optional[str],
    master_vendor: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Evaluates whether the vendor on the invoice is the same entity as the master vendor record.
    Rules:
    - Tax ID and bank account must match exactly (if master has them).
    - Different tax ID => different entity (TAX_ID_MISMATCH / UNKNOWN_VENDOR).
    - Legal-suffix variants (Pvt Ltd / Private Limited, Inc, GmbH), abbreviations, punctuation,
      accents, word order, minor typos => same entity (VENDOR_NAME_VARIATION).
    """
    name_on_invoice = (inv_vendor_name or "").strip()
    name_on_record = master_vendor.get("legal_name", "") if master_vendor else ""

    if not master_vendor:
        return {
            "same_entity": False,
            "confidence": 0.95,
            "reason": f"Vendor '{name_on_invoice}' not found in Vendor Master Registry.",
            "name_on_invoice": name_on_invoice,
            "name_on_record": "",
            "reason_code": "UNKNOWN_VENDOR",
        }

    m_tax = master_vendor.get("tax_id", "")
    m_bank = master_vendor.get("bank_account", "")

    clean_inv_tax = _clean_id(inv_tax_id)
    clean_m_tax = _clean_id(m_tax)
    clean_inv_bank = _clean_id(inv_bank)
    clean_m_bank = _clean_id(m_bank)

    # 1. Hard Check: Tax ID Mismatch
    if clean_inv_tax and clean_m_tax and clean_inv_tax != clean_m_tax:
        return {
            "same_entity": False,
            "confidence": 0.99,
            "reason": f"Tax ID mismatch: Invoice lists '{inv_tax_id}' while Vendor Master record has '{m_tax}'. Different legal entity.",
            "name_on_invoice": name_on_invoice,
            "name_on_record": name_on_record,
            "reason_code": "TAX_ID_MISMATCH",
        }

    # 2. Hard Check: Bank Account Mismatch
    if clean_inv_bank and clean_m_bank and clean_inv_bank != clean_m_bank:
        return {
            "same_entity": False,
            "confidence": 0.99,
            "reason": f"Bank account mismatch: Invoice lists '{inv_bank}' while Vendor Master record has '{m_bank}'. Potential unauthorized redirection.",
            "name_on_invoice": name_on_invoice,
            "name_on_record": name_on_record,
            "reason_code": "BANK_DETAILS_CHANGED",
        }

    # 3. Check for exact name match (accounting for accents)
    norm_inv = _normalize_vendor_name(name_on_invoice)
    norm_master = _normalize_vendor_name(name_on_record)

    aliases = [a.strip() for a in master_vendor.get("aliases", "").split("|") if a.strip()]
    norm_aliases = [_normalize_vendor_name(a) for a in aliases]

    if norm_inv == norm_master or any(norm_inv == na for na in norm_aliases):
        return {
            "same_entity": True,
            "confidence": 0.99,
            "reason": f"Exact match with Vendor Master record for '{name_on_record}'.",
            "name_on_invoice": name_on_invoice,
            "name_on_record": name_on_record,
            "reason_code": None,
        }

    # 4. Try LLM if available
    if llm_available():
        system_prompt = (
            "You are a corporate AP auditor. Determine if the invoice vendor and master record represent the exact same company. "
            "Respond strictly in JSON with format: {\"same_entity\": bool, \"confidence\": float (0-1), \"reason\": str}"
        )
        user_prompt = (
            f"Invoice Vendor Name: '{name_on_invoice}'\n"
            f"Master Record Legal Name: '{name_on_record}'\n"
            f"Aliases on Record: {aliases}\n"
            f"Invoice Tax ID: '{inv_tax_id or 'None'}' vs Master Tax ID: '{m_tax or 'None'}'\n"
            f"Invoice Bank Account: '{inv_bank or 'None'}' vs Master Bank: '{m_bank or 'None'}'"
        )
        llm_res = call_llm_json(system=system_prompt, user=user_prompt, temperature=0.0)
        if llm_res and "same_entity" in llm_res:
            same = bool(llm_res.get("same_entity"))
            conf = float(llm_res.get("confidence", 0.95))
            reason = str(llm_res.get("reason", ""))
            return {
                "same_entity": same,
                "confidence": conf,
                "reason": reason,
                "name_on_invoice": name_on_invoice,
                "name_on_record": name_on_record,
                "reason_code": "VENDOR_NAME_VARIATION" if same else "UNKNOWN_VENDOR",
            }

    # 5. Rule-based Fallback
    # Compare string similarity ratio
    matcher = difflib.SequenceMatcher(None, norm_inv, norm_master)
    ratio = matcher.ratio()

    # Check similarity with aliases as well
    for na in norm_aliases:
        alias_ratio = difflib.SequenceMatcher(None, norm_inv, na).ratio()
        if alias_ratio > ratio:
            ratio = alias_ratio

    # Substring containment check
    is_contained = (norm_inv in norm_master) or (norm_master in norm_inv) or any((norm_inv in na or na in norm_inv) for na in norm_aliases)

    if ratio >= 0.88 or (is_contained and (clean_inv_tax == clean_m_tax if clean_m_tax else True)):
        reason = f"Name differs slightly ('{name_on_invoice}' vs '{name_on_record}'); Tax ID and banking records match master."
        return {
            "same_entity": True,
            "confidence": 0.95,
            "reason": reason,
            "name_on_invoice": name_on_invoice,
            "name_on_record": name_on_record,
            "reason_code": "VENDOR_NAME_VARIATION",
        }

    return {
        "same_entity": False,
        "confidence": 0.90,
        "reason": f"Vendor name '{name_on_invoice}' does not match Vendor Master legal name '{name_on_record}' or registered aliases.",
        "name_on_invoice": name_on_invoice,
        "name_on_record": name_on_record,
        "reason_code": "UNKNOWN_VENDOR",
    }


def final_review(case: Dict[str, Any]) -> Dict[str, Any]:
    """
    Final AP Controller Safety Review.
    Input case is a compact dictionary containing:
    - invoice: extracted fields (vendor, invoice_no, total, subtotal, tax, currency, date, due_date)
    - vendor_master: master info
    - vendor_identity: result from judge_vendor_identity
    - po: matched PO details and balance
    - tolerances: effective tolerances
    - reason_codes: deterministic reason codes
    - deterministic_decision: "AUTO_APPROVE" | "NEEDS_REVIEW" | "ON_HOLD" | "REJECT"

    Returns:
    {
        "verdict": "APPROVE" | "REVIEW" | "REJECT",
        "confidence": float,
        "summary": str,
        "checks": List[{"label": str, "ok": bool, "note": str}],
        "concerns": List[str],
        "mode": "ai" | "rules"
    }
    """
    reason_codes: List[str] = case.get("reason_codes", [])
    det_decision: str = case.get("deterministic_decision", "NEEDS_REVIEW")
    inv = case.get("invoice", {})
    po = case.get("po", {})
    vendor_master = case.get("vendor_master", {})
    vendor_id_res = case.get("vendor_identity", {}) or {}
    tolerances = case.get("tolerances", {})

    # 1. Build Deterministic Baseline Checks
    checks: List[Dict[str, Any]] = []

    # Vendor Check
    v_ok = (
        "UNKNOWN_VENDOR" not in reason_codes
        and "BLOCKED_VENDOR" not in reason_codes
        and "TAX_ID_MISMATCH" not in reason_codes
    )
    if "BLOCKED_VENDOR" in reason_codes:
        v_note = "Vendor is marked BLOCKED in policy."
    elif "TAX_ID_MISMATCH" in reason_codes:
        v_note = "Tax ID on invoice does not match master record."
    elif "VENDOR_NAME_VARIATION" in reason_codes:
        v_note = vendor_id_res.get("reason", "Vendor name variation verified against tax ID.")
    elif v_ok:
        v_note = f"Verified vendor ({vendor_master.get('legal_name', inv.get('vendor_name', ''))})."
    else:
        v_note = "Vendor identity unconfirmed in master."
    checks.append({"label": "Vendor verified", "ok": v_ok, "note": v_note})

    # Bank Details Check
    b_ok = "BANK_DETAILS_CHANGED" not in reason_codes
    b_note = "Remittance bank account verified." if b_ok else "CRITICAL: Invoice bank account does not match master record."
    checks.append({"label": "Bank details", "ok": b_ok, "note": b_note})

    # Purchase Order Match Check
    po_ok = (
        "NO_PO_FOUND" not in reason_codes
        and "PO_OVERBILLED" not in reason_codes
        and "PO_CLOSED" not in reason_codes
    )
    if "PREAPPROVED_NO_PO" in reason_codes:
        po_ok = True
        po_note = "Pre-approved recurring invoice; PO not required under policy limit."
    elif "PO_OVERBILLED" in reason_codes:
        po_note = "Invoice amount exceeds authorized PO remaining balance."
    elif "NO_PO_FOUND" in reason_codes:
        po_note = "No matching Purchase Order found."
    elif "PO_INFERRED" in reason_codes:
        po_note = f"PO {po.get('po_number', '')} automatically matched via line items."
    elif po_ok:
        po_note = f"Matched to PO {po.get('po_number', '')}."
    else:
        po_note = "PO exception detected."
    checks.append({"label": "Purchase order match", "ok": po_ok, "note": po_note})

    # Amount Within Tolerance Check
    amt_ok = "PRICE_VARIANCE" not in reason_codes and "OVER_VENDOR_LIMIT" not in reason_codes
    if "OVER_VENDOR_LIMIT" in reason_codes:
        amt_note = f"Invoice total exceeds vendor auto-approve limit."
    elif "PRICE_VARIANCE" in reason_codes:
        amt_note = "Line item unit price variance detected."
    elif amt_ok:
        amt_note = "Amounts and line prices within permissible tolerances."
    else:
        amt_note = "Variance detected beyond tolerance."
    checks.append({"label": "Amount within tolerance", "ok": amt_ok, "note": amt_note})

    # Duplicate Check
    dup_ok = "DUPLICATE_INVOICE" not in reason_codes
    dup_note = "No duplicate submissions detected." if dup_ok else "CRITICAL: Duplicate invoice submission detected."
    checks.append({"label": "Duplicate check", "ok": dup_ok, "note": dup_note})

    # Math & Fields Check
    math_ok = (
        "MISSING_INVOICE_NUMBER" not in reason_codes
        and "ARITHMETIC_MISMATCH" not in reason_codes
        and "MISSING_TOTAL" not in reason_codes
    )
    if not math_ok:
        errs = [c for c in ["MISSING_INVOICE_NUMBER", "ARITHMETIC_MISMATCH", "MISSING_TOTAL"] if c in reason_codes]
        math_note = f"Data validation issues: {', '.join(errs)}."
    else:
        math_note = "Mandatory fields present and arithmetic verified."
    checks.append({"label": "Math & fields", "ok": math_ok, "note": math_note})

    # Policy Check
    pol_ok = (
        "BLOCKED_VENDOR" not in reason_codes
        and "WATCHLIST_VENDOR" not in reason_codes
        and "OVER_VENDOR_LIMIT" not in reason_codes
        and "PO_REQUIRED_OVER_LIMIT" not in reason_codes
    )
    if "BLOCKED_VENDOR" in reason_codes:
        pol_note = "Blocked by corporate compliance policy."
    elif "WATCHLIST_VENDOR" in reason_codes:
        pol_note = "Vendor requires manual sign-off under watchlist governance."
    elif "OVER_VENDOR_LIMIT" in reason_codes:
        pol_note = "Exceeds automated approval limit under vendor policy."
    elif pol_ok:
        pol_note = "Complies with vendor trust tier and AP governance rules."
    else:
        pol_note = "Policy check warning."
    checks.append({"label": "Policy", "ok": pol_ok, "note": pol_note})

    # List Concerns
    concerns: List[str] = [c["note"] for c in checks if not c["ok"]]

    # 2. Try LLM Review if Available
    if llm_available():
        system_prompt = (
            "You are a Senior Corporate Accounts Payable Controller. Conduct a thorough safety and risk review of this invoice case. "
            "Rules:\n"
            "1. Be conservative and precise. Cite exact numbers and currency symbols.\n"
            "2. Never invent data. LLM can only make a case safer, never riskier.\n"
            "3. Look for suspicious discrepancies: bank account changes, duplicate submissions, PO overbilling, arithmetic errors, currency mismatches.\n"
            "4. Respond strictly in JSON: {\"verdict\": \"APPROVE\"|\"REVIEW\"|\"REJECT\", \"confidence\": float (0-1), \"summary\": str, \"concerns\": [str]}"
        )
        import json
        case_summary = json.dumps(case, indent=2, default=str)
        user_prompt = f"Case Summary for Review:\n{case_summary}"

        llm_res = call_llm_json(system=system_prompt, user=user_prompt, temperature=0.0)
        if llm_res and "verdict" in llm_res:
            llm_verdict = str(llm_res.get("verdict", "")).upper()
            llm_conf = float(llm_res.get("confidence", 0.90))
            llm_summary = str(llm_res.get("summary", ""))
            llm_concerns = llm_res.get("concerns", [])
            if not isinstance(llm_concerns, list):
                llm_concerns = [str(llm_concerns)]

            merged_concerns = list(dict.fromkeys(concerns + llm_concerns))
            return {
                "verdict": llm_verdict,
                "confidence": llm_conf,
                "summary": llm_summary or _synthesize_summary(det_decision, merged_concerns, inv),
                "checks": checks,
                "concerns": merged_concerns,
                "mode": "ai",
            }

    # 3. Rule-Based Fallback Review
    # Determine verdict conservatively based on checks
    if any(c in reason_codes for c in ["BANK_DETAILS_CHANGED", "DUPLICATE_INVOICE", "PO_OVERBILLED", "BLOCKED_VENDOR"]):
        verdict = "REJECT"
        confidence = 0.98
    elif any(not c["ok"] for c in checks) or det_decision in ["NEEDS_REVIEW", "ON_HOLD"]:
        verdict = "REVIEW" if det_decision != "ON_HOLD" else "REVIEW"
        confidence = 0.92
    else:
        verdict = "APPROVE"
        confidence = 0.96

    summary = _synthesize_summary(verdict, concerns, inv)
    return {
        "verdict": verdict,
        "confidence": confidence,
        "summary": summary,
        "checks": checks,
        "concerns": concerns,
        "mode": "rules",
    }


def _synthesize_summary(verdict: str, concerns: List[str], inv: Dict[str, Any]) -> str:
    """Generates a concise 2-3 sentence executive decision explanation."""
    v_name = inv.get("vendor_name") or "Vendor"
    inv_no = inv.get("invoice_number") or "invoice"
    curr = inv.get("currency") or "INR"
    tot = inv.get("total") or 0.0

    if verdict == "APPROVE":
        return (
            f"All automated AP verification checks passed for {v_name} ({inv_no}). "
            f"Line items and billing amount ({tot:,.2f} {curr}) match authorized purchase order and vendor banking records. "
            f"Transaction cleared for automated payment."
        )
    elif verdict == "REJECT":
        reason_txt = concerns[0] if concerns else "Critical security or duplication policy violation"
        return (
            f"Invoice {inv_no} from {v_name} for {tot:,.2f} {curr} has been blocked. "
            f"{reason_txt}. Payment will not be disbursed."
        )
    else:  # REVIEW or ON_HOLD
        reasons = "; ".join(concerns[:2]) if concerns else "Exceptions require human verification"
        return (
            f"Invoice {inv_no} from {v_name} for {tot:,.2f} {curr} requires controller sign-off. "
            f"{reasons}. Please inspect the workbench diff before clearing."
        )


def explain_decision(run_data: Dict[str, Any]) -> str:
    """Generates plain English 2-3 sentences for display at the top of the invoice detail UI."""
    ai_review = run_data.get("ai_review") or {}
    if ai_review.get("summary"):
        return ai_review["summary"]

    decision = run_data.get("decision", "NEEDS_REVIEW")
    reasons = run_data.get("reason_codes", [])
    std = run_data.get("standard_invoice", {})
    v_name = ""
    inv_no = ""
    curr = "INR"
    tot = 0.0

    if isinstance(std, dict):
        v_name = (std.get("vendor_name") or {}).get("value") or ""
        inv_no = (std.get("invoice_number") or {}).get("value") or ""
        curr = (std.get("currency") or {}).get("value") or "INR"
        tot = (std.get("total") or {}).get("value") or 0.0
    else:
        v_name = getattr(getattr(std, "vendor_name", None), "value", "")
        inv_no = getattr(getattr(std, "invoice_number", None), "value", "")
        curr = getattr(getattr(std, "currency", None), "value", "INR")
        tot = getattr(getattr(std, "total", None), "value", 0.0)

    inv_dict = {"vendor_name": v_name, "invoice_number": inv_no, "currency": curr, "total": tot}
    concerns = [f"Reason code: {r}" for r in reasons if r not in ["VENDOR_NAME_VARIATION", "PREAPPROVED_NO_PO"]]
    return _synthesize_summary(decision, concerns, inv_dict)
