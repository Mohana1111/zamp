"""
Vendor Policy & AP Governance Module.

Implements:
- Vendor Trust tiers: PREAPPROVED | STANDARD | WATCHLIST | BLOCKED
- Auto-approve limits per vendor (in vendor currency)
- Configurable price and total variance tolerances
- No-PO recurring services exemptions (rent, SaaS, utilities)
- Global settings persistence (tolerances, limits, AI review toggle)
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

DATA_DIR = Path(__file__).resolve().parent / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"
VENDOR_POLICY_FILE = DATA_DIR / "vendor_policy.json"

DEFAULT_GLOBAL_SETTINGS: Dict[str, Any] = {
    "default_price_tolerance_pct": 2.0,
    "default_total_tolerance_pct": 1.0,
    "default_auto_approve_limit_inr": None,
    "duplicate_window_days": 365,
    "require_po_above_inr": 50000.0,
    "ai_review_enabled": True,
    "ai_min_confidence": 0.85,
}

DEFAULT_VENDOR_POLICIES: Dict[str, Dict[str, Any]] = {
    "V001": {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "Packaging supplier. Strict 2-way match against open purchase orders.",
    },
    "V002": {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "Enterprise Cloud Software license vendor.",
    },
    "V003": {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "German machinery parts supplier. Subject to European VAT rules.",
    },
    "V004": {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "Singapore sea freight carrier.",
    },
    "V005": {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "Precision CNC assemblies vendor. Regular split shipments.",
    },
}


def load_settings() -> Dict[str, Any]:
    """Loads global settings from disk, applying defaults if missing."""
    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_GLOBAL_SETTINGS)
        return dict(DEFAULT_GLOBAL_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            merged = dict(DEFAULT_GLOBAL_SETTINGS)
            merged.update(data)
            return merged
    except Exception:
        return dict(DEFAULT_GLOBAL_SETTINGS)


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Saves global settings to disk."""
    current = load_settings() if SETTINGS_FILE.exists() else dict(DEFAULT_GLOBAL_SETTINGS)
    current.update(settings)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current


def load_vendor_policies() -> Dict[str, Dict[str, Any]]:
    """Loads all vendor policies from disk."""
    if not VENDOR_POLICY_FILE.exists():
        save_all_vendor_policies(DEFAULT_VENDOR_POLICIES)
        return dict(DEFAULT_VENDOR_POLICIES)
    try:
        with open(VENDOR_POLICY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception:
        return dict(DEFAULT_VENDOR_POLICIES)


def save_all_vendor_policies(policies: Dict[str, Dict[str, Any]]):
    """Saves full vendor policy map to disk."""
    VENDOR_POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(VENDOR_POLICY_FILE, "w", encoding="utf-8") as f:
        json.dump(policies, f, indent=2)


def get_vendor_policy(vendor_id: Optional[str]) -> Dict[str, Any]:
    """Returns policy for a given vendor_id, or standard default if not configured."""
    if not vendor_id:
        return {
            "trust": "STANDARD",
            "auto_approve_limit": None,
            "price_tolerance_pct": None,
            "total_tolerance_pct": None,
            "allow_without_po": False,
            "notes": "Unregistered / default policy",
        }
    policies = load_vendor_policies()
    v_clean = vendor_id.strip().upper()
    if v_clean in policies:
        return policies[v_clean]
    # Return standard default
    return {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "",
    }


def save_vendor_policy(vendor_id: str, policy_update: Dict[str, Any]) -> Dict[str, Any]:
    """Updates policy for a specific vendor_id."""
    v_clean = vendor_id.strip().upper()
    policies = load_vendor_policies()
    current = policies.get(v_clean, {
        "trust": "STANDARD",
        "auto_approve_limit": None,
        "price_tolerance_pct": None,
        "total_tolerance_pct": None,
        "allow_without_po": False,
        "notes": "",
    })

    # Validate trust enum
    valid_trust = ["PREAPPROVED", "STANDARD", "WATCHLIST", "BLOCKED"]
    if "trust" in policy_update:
        trust_val = str(policy_update["trust"]).upper()
        if trust_val in valid_trust:
            current["trust"] = trust_val

    for k in ["auto_approve_limit", "price_tolerance_pct", "total_tolerance_pct"]:
        if k in policy_update:
            val = policy_update[k]
            current[k] = float(val) if val is not None else None

    if "allow_without_po" in policy_update:
        current["allow_without_po"] = bool(policy_update["allow_without_po"])

    if "notes" in policy_update:
        current["notes"] = str(policy_update["notes"])

    policies[v_clean] = current
    save_all_vendor_policies(policies)
    return current


def reset_policy_state():
    """Resets vendor policies and settings to default clean state."""
    save_settings(DEFAULT_GLOBAL_SETTINGS)
    save_all_vendor_policies(DEFAULT_VENDOR_POLICIES)


def evaluate_vendor_policy(
    vendor_id: Optional[str],
    invoice_total: float,
    currency: str,
    base_total_inr: float,
    has_po: bool,
    reason_codes: List[str],
) -> Dict[str, Any]:
    """
    Evaluates vendor policy against the current invoice.
    Returns:
    {
        "policy_applied": {
            "trust": str,
            "limit": float|None,
            "price_tolerance_pct": float,
            "total_tolerance_pct": float,
            "allow_without_po": bool,
            "notes": List[str],
        },
        "effective_price_tolerance_pct": float,
        "effective_total_tolerance_pct": float,
        "policy_action": "CONTINUE" | "REJECT" | "REVIEW" | "PREAPPROVED_NO_PO",
        "policy_notes": List[str],
    }
    """
    settings = load_settings()
    vendor_pol = get_vendor_policy(vendor_id)

    trust = vendor_pol.get("trust", "STANDARD").upper()
    limit = vendor_pol.get("auto_approve_limit")
    allow_no_po = vendor_pol.get("allow_without_po", False)

    # Effective tolerances
    price_tol = vendor_pol.get("price_tolerance_pct")
    if price_tol is None:
        price_tol = float(settings.get("default_price_tolerance_pct", 2.0))

    total_tol = vendor_pol.get("total_tolerance_pct")
    if total_tol is None:
        total_tol = float(settings.get("default_total_tolerance_pct", 1.0))

    policy_notes: List[str] = []
    policy_action = "CONTINUE"

    # 1. BLOCKED vendor
    if trust == "BLOCKED":
        if "BLOCKED_VENDOR" not in reason_codes:
            reason_codes.append("BLOCKED_VENDOR")
        policy_action = "REJECT"
        policy_notes.append("Vendor is explicitly marked as BLOCKED in policy. Auto-rejecting invoice.")

    # 2. WATCHLIST vendor
    elif trust == "WATCHLIST":
        if "WATCHLIST_VENDOR" not in reason_codes:
            reason_codes.append("WATCHLIST_VENDOR")
        policy_action = "REVIEW"
        policy_notes.append("Vendor is on corporate WATCHLIST. Auto-approval disabled; human review required.")

    # 3. PREAPPROVED vendor
    elif trust == "PREAPPROVED":
        policy_notes.append("Vendor is PREAPPROVED.")
        # Check auto-approve limit
        if limit is not None and invoice_total > limit:
            if "OVER_VENDOR_LIMIT" not in reason_codes:
                reason_codes.append("OVER_VENDOR_LIMIT")
            policy_action = "REVIEW"
            policy_notes.append(f"Invoice total ({invoice_total:,.2f} {currency}) exceeds vendor auto-approve limit ({limit:,.2f} {currency}). Routed to review.")
        elif not has_po:
            if allow_no_po:
                if "PREAPPROVED_NO_PO" not in reason_codes:
                    reason_codes.append("PREAPPROVED_NO_PO")
                policy_action = "PREAPPROVED_NO_PO"
                policy_notes.append(f"Pre-approved recurring invoice without PO within policy limit ({invoice_total:,.2f} {currency}). Eligible for auto-approval.")
            else:
                policy_notes.append("Pre-approved vendor requires purchase order for this category.")

    # 4. Global require_po_above_inr check
    require_po_limit = settings.get("require_po_above_inr", 50000.0)
    if not has_po and require_po_limit and base_total_inr > require_po_limit:
        if trust != "PREAPPROVED" or not allow_no_po:
            if "PO_REQUIRED_OVER_LIMIT" not in reason_codes:
                reason_codes.append("PO_REQUIRED_OVER_LIMIT")
            policy_notes.append(f"Invoice value (INR {base_total_inr:,.2f}) exceeds PO requirement threshold (INR {require_po_limit:,.2f}).")

    policy_applied = {
        "trust": trust,
        "limit": limit,
        "price_tolerance_pct": price_tol,
        "total_tolerance_pct": total_tol,
        "allow_without_po": allow_no_po,
        "notes": policy_notes,
    }

    return {
        "policy_applied": policy_applied,
        "effective_price_tolerance_pct": price_tol,
        "effective_total_tolerance_pct": total_tol,
        "policy_action": policy_action,
        "policy_notes": policy_notes,
    }
