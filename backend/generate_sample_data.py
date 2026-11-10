"""
ClearPay AP - Sample Data & Multi-Format Invoice Generator
Generates canonical master data (vendors, POs, PO lines, FX rates),
scenario metadata, simulated incoming emails, and 10+ realistic multi-format
invoices (PDF, Scanned Image PNG, XLSX, DOCX).
"""

import os
import sys
import json
import csv

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import io
import numpy as np
from PIL import Image
import pymupdf
import openpyxl
from openpyxl.styles import Font as XlsxFont, PatternFill, Alignment, Border, Side
import docx
from docx.shared import Pt, RGBColor
from docx.enum.table import WD_TABLE_ALIGNMENT

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INVOICES_DIR = os.path.join(DATA_DIR, "sample_invoices")


# ==============================================================================
# 1. Reference Data Generators (CSVs)
# ==============================================================================

def generate_reference_csvs():
    """Generates vendors.csv, purchase_orders.csv, purchase_orders_initial.csv,
    po_lines.csv, and fx_rates.csv strictly matching ARCHITECTURE.md."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. vendors.csv
    vendors_path = os.path.join(DATA_DIR, "vendors.csv")
    vendors_data = [
        ["vendor_id", "legal_name", "aliases", "country", "tax_id", "default_currency", "bank_account", "bank_code", "status", "payment_terms"],
        ["V001", "Shree Ganesh Packaging Pvt Ltd", "Shree Ganesh Packaging|SG Packaging", "IN", "27AABCS1234F1Z5", "INR", "50200012345678", "HDFC0001234", "ACTIVE", "NET30"],
        ["V002", "Brightline Software Inc", "Brightline|Brightline Software|Brightline Cloud", "US", "12-3456789", "USD", "000123456789", "021000021", "ACTIVE", "NET45"],
        ["V003", "Müller Industrietechnik GmbH", "Muller Industrietechnik|Müller GmbH|Muller GmbH", "DE", "DE123456789", "EUR", "DE89370400440532013000", "DEUTDEFF", "ACTIVE", "NET30"],
        ["V004", "Lion City Logistics Pte Ltd", "Lion City Logistics|LionCity Logistics", "SG", "201912345K", "SGD", "0123456789", "DBSSSGSG", "ACTIVE", "NET30"],
        ["V005", "Apex Industrial Components Pvt Ltd", "Apex Industrial|Apex Components", "IN", "27AAECA9876B1Z2", "INR", "91827364501234", "ICIC0000451", "ACTIVE", "NET30"],
    ]
    with open(vendors_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(vendors_data)

    # 2. purchase_orders.csv & purchase_orders_initial.csv
    pos_path = os.path.join(DATA_DIR, "purchase_orders.csv")
    pos_init_path = os.path.join(DATA_DIR, "purchase_orders_initial.csv")
    pos_data = [
        ["po_number", "vendor_id", "currency", "po_date", "subtotal", "tax_amount", "total_amount", "invoiced_amount", "remaining_amount", "status", "approver"],
        ["PO-2026-1041", "V001", "INR", "2026-10-01", "200000.00", "36000.00", "236000.00", "0.00", "236000.00", "OPEN", "Rahul Sharma"],
        ["PO-2026-1042", "V005", "INR", "2026-10-05", "100000.00", "0.00", "100000.00", "0.00", "100000.00", "OPEN", "Rahul Sharma"],
        ["PO-2026-1043", "V002", "USD", "2026-10-10", "12000.00", "0.00", "12000.00", "0.00", "12000.00", "OPEN", "Rahul Sharma"],
        ["PO-2026-1045", "V003", "EUR", "2026-10-12", "5900.00", "1121.00", "7021.00", "0.00", "7021.00", "OPEN", "Rahul Sharma"],
        ["PO-2026-1047", "V004", "SGD", "2026-10-15", "8500.00", "0.00", "8500.00", "0.00", "8500.00", "OPEN", "Rahul Sharma"],
    ]
    with open(pos_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(pos_data)

    with open(pos_init_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(pos_data)

    # 3. po_lines.csv
    po_lines_path = os.path.join(DATA_DIR, "po_lines.csv")
    po_lines_data = [
        ["po_number", "line_no", "item_code", "description", "qty", "unit_price", "amount", "tax_rate"],
        ["PO-2026-1041", "1", "PKG-BOX-L", "Corrugated Export Cartons (Double Wall)", "2000", "75.00", "150000.00", "0.18"],
        ["PO-2026-1041", "2", "PKG-TAPE-HD", "Heavy Duty Strapping Rolls", "500", "100.00", "50000.00", "0.18"],
        ["PO-2026-1042", "1", "CNC-SPINDLE", "High-Torque CNC Spindle Assembly", "10", "10000.00", "100000.00", "0.00"],
        ["PO-2026-1043", "1", "SAAS-ENT", "Brightline Enterprise Cloud License (Annual)", "1", "12000.00", "12000.00", "0.00"],
        ["PO-2026-1045", "1", "HP-200", "Hydraulic Pump HP-200", "4", "1250.00", "5000.00", "0.19"],
        ["PO-2026-1045", "2", "SK-10", "Precision Seal Kit SK-10", "20", "45.00", "900.00", "0.19"],
        ["PO-2026-1047", "1", "FRT-SEA-20", "20ft Container Sea Freight (SG to JNPT)", "2", "3500.00", "7000.00", "0.00"],
        ["PO-2026-1047", "2", "PORT-THC", "Terminal Handling & Documentation Charges", "1", "1500.00", "1500.00", "0.00"],
    ]
    with open(po_lines_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(po_lines_data)

    # 4. fx_rates.csv
    fx_path = os.path.join(DATA_DIR, "fx_rates.csv")
    fx_data = [
        ["currency", "rate_to_inr", "symbol", "updated_at"],
        ["INR", "1.00", "₹", "2026-10-28"],
        ["USD", "84.10", "$", "2026-10-28"],
        ["EUR", "91.60", "€", "2026-10-28"],
        ["GBP", "109.30", "£", "2026-10-28"],
        ["SGD", "64.20", "S$", "2026-10-28"],
    ]
    with open(fx_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(fx_data)

    print("[OK] Reference CSV files written successfully.")


# ==============================================================================
# 2. Metadata: sample_scenarios.json & sample_emails.json
# ==============================================================================

def generate_metadata_json():
    """Generates sample_scenarios.json (11 scenarios) and sample_emails.json (realistic incoming vendor emails)."""
    os.makedirs(DATA_DIR, exist_ok=True)

    # 1. sample_scenarios.json
    scenarios = [
        {
            "id": "scenario_01",
            "filename": "01_happy_shree_ganesh_inr.pdf",
            "title": "Clean Standard GST Invoice",
            "subtitle": "Shree Ganesh Packaging • PO-2026-1041",
            "category": "HAPPY_PATH",
            "badge_color": "emerald",
            "expected_decision": "AUTO_APPROVE",
            "description": "Clean Indian GST Tax Invoice with exact 3-way match on PO-2026-1041, line items, 18% IGST calculation (₹2,36,000.00), and active vendor master bank account."
        },
        {
            "id": "scenario_02",
            "filename": "02_split_part1_apex_inr.pdf",
            "title": "Split PO - Part 1 (Partial Delivery)",
            "subtitle": "Apex Industrial Components • PO-2026-1042 (6/10 Units)",
            "category": "HAPPY_PATH",
            "badge_color": "emerald",
            "expected_decision": "AUTO_APPROVE",
            "description": "Partial billing milestone batch 1 (6 units @ ₹10,000 = ₹60,000) against PO ₹1,00,000. Consumes 60% of PO, leaving ₹40,000 remaining."
        },
        {
            "id": "scenario_03",
            "filename": "03_split_part2_apex_inr.pdf",
            "title": "Split PO - Part 2 (Final Delivery)",
            "subtitle": "Apex Industrial Components • PO-2026-1042 (4/10 Units)",
            "category": "HAPPY_PATH",
            "badge_color": "emerald",
            "expected_decision": "AUTO_APPROVE",
            "description": "Partial billing milestone batch 2 (4 units @ ₹10,000 = ₹40,000) against PO ₹1,00,000. Exactly consumes remaining PO balance to ₹0."
        },
        {
            "id": "scenario_04",
            "filename": "04_split_part3_overbill_apex_inr.pdf",
            "title": "Split PO - Part 3 (Overbilling Attempt)",
            "subtitle": "Apex Industrial Components • PO-2026-1042 Overbill",
            "category": "EDGE_CASE",
            "badge_color": "rose",
            "expected_decision": "REJECT",
            "description": "Supplemental invoice for ₹15,000 (1.5 units) submitted after PO-2026-1042 is already 100% consumed. Flags PO_OVERBILLED rejection."
        },
        {
            "id": "scenario_05",
            "filename": "05_duplicate_rescan_shree_ganesh.pdf",
            "title": "Disguised Duplicate Scan",
            "subtitle": "Shree Ganesh Packaging • INV/2026/0081",
            "category": "EDGE_CASE",
            "badge_color": "rose",
            "expected_decision": "REJECT",
            "description": "Resent scanned copy of #1 formatted with slashes ('INV/2026/0081' vs 'INV-2026-0081') and date format variance ('28/10/2026'). Flags DUPLICATE_INVOICE."
        },
        {
            "id": "scenario_06",
            "filename": "06_scanned_muller_no_po_eur.png",
            "title": "German Scanned PNG (No PO Ref)",
            "subtitle": "Müller Industrietechnik GmbH • RE-2026-0412",
            "category": "MULTI_FORMAT",
            "badge_color": "amber",
            "expected_decision": "NEEDS_REVIEW",
            "description": "Scanned German document with German text, European comma decimals ('5.900,00 €'), and no PO reference on invoice. Pipeline infers PO-2026-1045 via line-item matching."
        },
        {
            "id": "scenario_07",
            "filename": "07_fraud_bank_changed_brightline_usd.pdf",
            "title": "BEC Fraud - Altered Bank Details",
            "subtitle": "Brightline Software Inc • PO-2026-1043",
            "category": "EDGE_CASE",
            "badge_color": "rose",
            "expected_decision": "REJECT",
            "description": "US SaaS invoice matches amount ($12,000) and PO, but invoice specifies an unapproved offshore bank account (999888777666 vs 000123456789). High-severity fraud alert."
        },
        {
            "id": "scenario_08",
            "filename": "08_currency_mismatch_muller_usd.pdf",
            "title": "Currency Mismatch (USD vs EUR)",
            "subtitle": "Müller Industrietechnik GmbH • RE-2026-0499",
            "category": "EDGE_CASE",
            "badge_color": "amber",
            "expected_decision": "NEEDS_REVIEW",
            "description": "Invoice references EUR PO-2026-1045 (€7,021.00) but is billed in US Dollars ($7,650.00). System normalizes currency, computes FX equivalent, and flags for review."
        },
        {
            "id": "scenario_09",
            "filename": "09_price_variance_lioncity_sgd.xlsx",
            "title": "Excel Spreadsheet + Price Variance",
            "subtitle": "Lion City Logistics Pte Ltd • LCL-SG-882",
            "category": "MULTI_FORMAT",
            "badge_color": "amber",
            "expected_decision": "NEEDS_REVIEW",
            "description": "Native XLSX invoice with ambiguous '$' currency symbol (inferred as SGD from vendor) and a +30% price variance on line 2 (Terminal Handling Charges $1,950 vs $1,500)."
        },
        {
            "id": "scenario_10",
            "filename": "10_missing_fields_draft.docx",
            "title": "Word Docx Draft + Math Mismatch",
            "subtitle": "Shree Ganesh Packaging • Draft Docx",
            "category": "MULTI_FORMAT",
            "badge_color": "amber",
            "expected_decision": "ON_HOLD",
            "description": "Draft DOCX invoice missing invoice number ('[TBD / Blank]') with arithmetic error (Subtotal ₹50,000 + IGST ₹9,000 = ₹64,000 instead of ₹59,000)."
        },
        {
            "id": "scenario_11",
            "filename": "11_bundled_embedded_tax_tolerance_inr.pdf",
            "title": "Bundled Lines + Embedded Tax + Tolerance",
            "subtitle": "Shree Ganesh Packaging • PO-2026-1041 (+₹450)",
            "category": "HAPPY_PATH",
            "badge_color": "emerald",
            "expected_decision": "AUTO_APPROVE",
            "description": "Single bundled line item 'Complete Packaging Supply (Cartons & Strapping)' with embedded 18% GST and a ₹450 freight/rounding variance (Total ₹2,36,450 vs PO ₹2,36,000 -> +0.19% within 1% tolerance)."
        }
    ]

    scenarios_path = os.path.join(DATA_DIR, "sample_scenarios.json")
    with open(scenarios_path, "w", encoding="utf-8") as f:
        json.dump(scenarios, f, indent=2, ensure_ascii=False)

    # 2. sample_emails.json (realistic incoming vendor emails sent to ap-invoices@acmemfg.in)
    emails = [
        {
            "id": "eml-001",
            "from_name": "Ramesh Patel (Shree Ganesh Packaging)",
            "from_email": "accounts@shreeganeshpkg.com",
            "subject": "Tax Invoice INV-2026-0081 for PO-2026-1041 - Packaging Material Delivery",
            "received_at": "2026-10-28T09:15:00Z",
            "snippet": "Dear Acme AP Team, Please find attached our Tax Invoice INV-2026-0081 for the corrugated boxes and strapping tape...",
            "body": "Dear Acme Manufacturing Accounts Payable Team,\n\nPlease find attached our Tax Invoice INV-2026-0081 for the corrugated export cartons and heavy-duty strapping tape supplied under purchase order PO-2026-1041.\n\nTotal payable amount: INR 236,000.00 (Subtotal ₹200,000.00 + 18% IGST ₹36,000.00).\n\nBank Remittance Details:\nBank: HDFC Bank Ltd\nA/C No: 50200012345678\nIFSC: HDFC0001234\n\nKindly release payment within 30 days as per our agreed payment terms.\n\nWarm regards,\nRamesh Patel\nSenior Manager - Finance & Accounts\nShree Ganesh Packaging Pvt Ltd\nAndheri East, Mumbai",
            "attachment_filename": "01_happy_shree_ganesh_inr.pdf",
            "scenario_id": "scenario_01",
            "currency": "INR",
            "amount_display": "₹2,36,000.00",
            "unread": True
        },
        {
            "id": "eml-002",
            "from_name": "Pooja Deshmukh (Apex Industrial Components)",
            "from_email": "billing@apexindustrial.in",
            "subject": "Tax Invoice APEX-26-101 (Milestone 1 - 6 Units CNC Spindles) - PO-2026-1042",
            "received_at": "2026-10-20T11:30:00Z",
            "snippet": "Hello AP Team, Attached is invoice APEX-26-101 for the first batch of 6 units of CNC Spindle Assembly...",
            "body": "Hello Accounts Payable Team,\n\nWe have dispatched the first delivery lot of 6 units of High-Torque CNC Spindle Assembly against PO-2026-1042.\n\nPlease find attached our invoice APEX-26-101 for INR 60,000.00 (6 units @ ₹10,000.00/unit).\n\nThe remaining balance of 4 units is undergoing final testing and will be shipped next week.\n\nBank Account: 91827364501234 (ICIC0000451)\n\nThanks & regards,\nPooja Deshmukh\nApex Industrial Components Pvt Ltd\nBhosari, Pune",
            "attachment_filename": "02_split_part1_apex_inr.pdf",
            "scenario_id": "scenario_02",
            "currency": "INR",
            "amount_display": "₹60,000.00",
            "unread": True
        },
        {
            "id": "eml-003",
            "from_name": "Pooja Deshmukh (Apex Industrial Components)",
            "from_email": "billing@apexindustrial.in",
            "subject": "Tax Invoice APEX-26-102 (Milestone 2 - 4 Units CNC Spindles) - PO-2026-1042",
            "received_at": "2026-10-25T14:20:00Z",
            "snippet": "Hello AP Team, Attached is invoice APEX-26-102 covering the remaining 4 units completing PO-2026-1042...",
            "body": "Hello Accounts Payable Team,\n\nFollowing up on our earlier dispatch, we have now delivered the final batch of 4 units of CNC Spindle Assembly, completing the 10-unit order under PO-2026-1042.\n\nAttached is invoice APEX-26-102 for INR 40,000.00.\n\nCumulative invoiced to date: INR 100,000.00 (PO is now 100% fulfilled).\n\nThanks & regards,\nPooja Deshmukh\nApex Industrial Components Pvt Ltd",
            "attachment_filename": "03_split_part2_apex_inr.pdf",
            "scenario_id": "scenario_03",
            "currency": "INR",
            "amount_display": "₹40,000.00",
            "unread": True
        },
        {
            "id": "eml-004",
            "from_name": "Pooja Deshmukh (Apex Industrial Components)",
            "from_email": "billing@apexindustrial.in",
            "subject": "Supplemental Invoice APEX-26-103 - PO-2026-1042 Extra Charges",
            "received_at": "2026-10-29T16:05:00Z",
            "snippet": "Hi Acme AP, Please find attached supplemental invoice APEX-26-103 for INR 15,000.00 for additional testing...",
            "body": "Hi Acme AP Team,\n\nPlease find attached supplemental invoice APEX-26-103 for INR 15,000.00 representing extra calibration, specialized fasteners, and engineering surcharge on PO-2026-1042.\n\nKindly approve and process for payment.\n\nRegards,\nPooja Deshmukh\nApex Industrial Components Pvt Ltd",
            "attachment_filename": "04_split_part3_overbill_apex_inr.pdf",
            "scenario_id": "scenario_04",
            "currency": "INR",
            "amount_display": "₹15,000.00",
            "unread": True
        },
        {
            "id": "eml-005",
            "from_name": "Ramesh Patel (Shree Ganesh Packaging)",
            "from_email": "accounts@shreeganeshpkg.com",
            "subject": "RESENT COPY: Invoice INV/2026/0081 for PO-2026-1041",
            "received_at": "2026-10-29T10:00:00Z",
            "snippet": "Dear AP Team, Please find attached a scanned copy of invoice INV/2026/0081 for your records...",
            "body": "Dear AP Team,\n\nOur billing desk noted this may have been misfiled. Please find attached a resent copy of invoice INV/2026/0081 dated 28/10/2026 for INR 236,000.00 against PO-2026-1041.\n\nKindly verify payment status.\n\nBest regards,\nRamesh Patel\nShree Ganesh Packaging Pvt Ltd",
            "attachment_filename": "05_duplicate_rescan_shree_ganesh.pdf",
            "scenario_id": "scenario_05",
            "currency": "INR",
            "amount_display": "₹2,36,000.00",
            "unread": True
        },
        {
            "id": "eml-006",
            "from_name": "Hans Schmidt (Müller Industrietechnik GmbH)",
            "from_email": "rechnungen@mueller-industrietechnik.de",
            "subject": "Rechnung RE-2026-0412 — Müller Industrietechnik GmbH",
            "received_at": "2026-10-28T08:45:00Z",
            "snippet": "Sehr geehrte Damen und Herren, anbei erhalten Sie unsere Rechnung RE-2026-0412 über 7.021,00 €...",
            "body": "Sehr geehrte Damen und Herren,\n\nanbei erhalten Sie unsere Rechnung RE-2026-0412 über 7.021,00 € für die Lieferung der 4x Hydraulikpumpe HP-200 und 20x Dichtungssatz SK-10.\n\nBitte überweisen Sie den Betrag innerhalb von 30 Tagen auf unsere angegebene IBAN: DE89370400440532013000 (SWIFT: DEUTDEFF).\n\nMit freundlichen Grüßen,\nHans Schmidt\nBuchhaltung / Accounts\nMüller Industrietechnik GmbH\nStuttgart, Deutschland",
            "attachment_filename": "06_scanned_muller_no_po_eur.png",
            "scenario_id": "scenario_06",
            "currency": "EUR",
            "amount_display": "€7.021,00",
            "unread": True
        },
        {
            "id": "eml-007",
            "from_name": "Accounts Receivable (Brightline Software Inc)",
            "from_email": "ar-billing@brightline-cloud.io",
            "subject": "URGENT: Annual Subscription Renewal Invoice BL-2026-990 (Updated Banking Details)",
            "received_at": "2026-10-28T13:10:00Z",
            "snippet": "Attention Accounts Payable: Attached is Invoice BL-2026-990 for $12,000.00. NOTE: Our banking details have changed...",
            "body": "Attention: Accounts Payable Department,\n\nPlease find attached Invoice BL-2026-990 for your annual Brightline Enterprise Cloud License ($12,000.00 USD) referencing PO-2026-1043.\n\nCRITICAL NOTICE: We have recently transitioned our treasury and merchant services. Please remit all electronic wires exclusively to our updated settlement account:\n\nBank Name: Offshore Commercial Bank\nAccount Number: 999888777666\nRouting / ABA: 099999999\nBeneficiary: Brightline Software Inc\n\nPlease confirm receipt of this update.\n\nSincerely,\nBrightline AR Operations\nSan Francisco, CA",
            "attachment_filename": "07_fraud_bank_changed_brightline_usd.pdf",
            "scenario_id": "scenario_07",
            "currency": "USD",
            "amount_display": "$12,000.00",
            "unread": True
        },
        {
            "id": "eml-008",
            "from_name": "Hans Schmidt (Müller Industrietechnik GmbH)",
            "from_email": "export@mueller-industrietechnik.de",
            "subject": "Export Billing Invoice RE-2026-0499 (USD Billing) - PO-2026-1045",
            "received_at": "2026-10-28T14:00:00Z",
            "snippet": "Dear Acme AP, Please find attached Invoice RE-2026-0499 billed in USD ($7,650.00) for PO-2026-1045...",
            "body": "Dear Acme AP Team,\n\nPlease find attached Invoice RE-2026-0499 covering hydraulic components under PO-2026-1045. As requested by our international trade operations, this dispatch has been invoiced in US Dollars for USD $7,650.00.\n\nBank IBAN: DE89370400440532013000 (SWIFT: DEUTDEFF)\n\nBest regards,\nHans Schmidt\nMüller Industrietechnik GmbH",
            "attachment_filename": "08_currency_mismatch_muller_usd.pdf",
            "scenario_id": "scenario_08",
            "currency": "USD",
            "amount_display": "$7,650.00",
            "unread": True
        },
        {
            "id": "eml-009",
            "from_name": "Tan Wei Ming (Lion City Logistics Pte Ltd)",
            "from_email": "billing@lioncitylogistics.com.sg",
            "subject": "Freight Invoice LCL-SG-882 (Ocean Freight SG-JNPT) - PO-2026-1047",
            "received_at": "2026-10-28T15:30:00Z",
            "snippet": "Hi Acme Logistics Team, Attached is billing sheet LCL-SG-882 for sea freight container dispatch...",
            "body": "Dear Acme Accounts Payable Team,\n\nPlease find attached Excel billing sheet LCL-SG-882 for ocean container freight and terminal handling charges under PO-2026-1047. Total due: $8,950.00.\n\nRemittance Bank: DBS Bank Ltd\nAccount: 0123456789\nSWIFT: DBSSSGSG\n\nWarm regards,\nTan Wei Ming\nFinance Officer\nLion City Logistics Pte Ltd\nSingapore",
            "attachment_filename": "09_price_variance_lioncity_sgd.xlsx",
            "scenario_id": "scenario_09",
            "currency": "SGD",
            "amount_display": "S$8,950.00",
            "unread": True
        },
        {
            "id": "eml-010",
            "from_name": "Ramesh Patel (Shree Ganesh Packaging)",
            "from_email": "accounts@shreeganeshpkg.com",
            "subject": "Consolidated Invoice INV-2026-0095 for PO-2026-1041 (Bundled Packaging Supply)",
            "received_at": "2026-10-30T10:15:00Z",
            "snippet": "Dear Acme AP Team, Attached is consolidated invoice INV-2026-0095 covering the entire packaging supply order...",
            "body": "Dear Acme AP Team,\n\nPlease find attached consolidated invoice INV-2026-0095 covering complete packaging materials for PO-2026-1041. All cartons and strapping rolls have been bundled as an all-inclusive single item including 18% IGST and local palletizing fee (Total ₹236,450.00).\n\nBest regards,\nRamesh Patel\nShree Ganesh Packaging Pvt Ltd",
            "attachment_filename": "11_bundled_embedded_tax_tolerance_inr.pdf",
            "scenario_id": "scenario_11",
            "currency": "INR",
            "amount_display": "₹2,36,450.00",
            "unread": True
        }
    ]

    emails_path = os.path.join(DATA_DIR, "sample_emails.json")
    with open(emails_path, "w", encoding="utf-8") as f:
        json.dump(emails, f, indent=2, ensure_ascii=False)

    print("[OK] Metadata JSON files (sample_scenarios.json & sample_emails.json) written successfully.")


# ==============================================================================
# 3. PDF Generator Helper Engine
# ==============================================================================

class InvoicePdfBuilder:
    """Helper to build clean, executive-grade corporate invoice PDFs."""

    def __init__(self, filename, primary_rgb=(0.08, 0.22, 0.40)):
        self.filename = filename
        self.doc = pymupdf.open()
        self.page = self.doc.new_page(width=595, height=842)  # Standard A4
        self.primary_rgb = primary_rgb
        self.font_reg = "helv"
        self.font_bold = "hebo"

    def draw_header_banner(self, title="TAX INVOICE", subtitle=None):
        # Top brand stripe
        self.page.draw_rect(pymupdf.Rect(40, 35, 555, 38), color=None, fill=self.primary_rgb)

    def draw_company_block(self, y_start, name, address_lines, tax_id_label, tax_id_val, extra_info=None):
        y = y_start
        self.page.insert_text(pymupdf.Point(40, y), name, fontsize=14, fontname=self.font_bold, color=self.primary_rgb)
        y += 14
        for line in address_lines:
            self.page.insert_text(pymupdf.Point(40, y), line, fontsize=8.5, fontname=self.font_reg, color=(0.35, 0.35, 0.35))
            y += 11
        tax_str = f"{tax_id_label}: {tax_id_val}"
        if extra_info:
            tax_str += f" | {extra_info}"
        self.page.insert_text(pymupdf.Point(40, y), tax_str, fontsize=8.5, fontname=self.font_bold, color=(0.2, 0.2, 0.2))
        return y + 16

    def draw_invoice_meta_box(self, y_start, title, meta_dict):
        """Draws top-right invoice metadata box."""
        font_b = pymupdf.Font(self.font_bold)
        title_w = font_b.text_length(title, 16)
        self.page.insert_text(pymupdf.Point(555 - title_w, y_start), title, fontsize=16, fontname=self.font_bold, color=self.primary_rgb)

        box_top = y_start + 10
        box_w = 210
        box_left = 555 - box_w
        box_h = len(meta_dict) * 15 + 10
        self.page.draw_rect(pymupdf.Rect(box_left, box_top, 555, box_top + box_h), color=(0.85, 0.88, 0.92), fill=(0.97, 0.98, 1.0), width=0.8)

        cur_y = box_top + 14
        for label, val in meta_dict.items():
            self.page.insert_text(pymupdf.Point(box_left + 8, cur_y), f"{label}:", fontsize=8.5, fontname=self.font_reg, color=(0.4, 0.4, 0.4))
            val_str = str(val)
            val_w = font_b.text_length(val_str, 8.5)
            self.page.insert_text(pymupdf.Point(555 - 8 - val_w, cur_y), val_str, fontsize=8.5, fontname=self.font_bold, color=(0.1, 0.1, 0.1))
            cur_y += 14

        return box_top + box_h + 10

    def draw_bill_to(self, y_start, recipient_lines, ship_to_lines=None):
        self.page.draw_line(pymupdf.Point(40, y_start), pymupdf.Point(555, y_start), color=(0.82, 0.85, 0.9), width=0.8)
        y = y_start + 14

        # Bill To
        self.page.insert_text(pymupdf.Point(40, y), "BILL TO / INVOICE RECIPIENT:", fontsize=8.5, fontname=self.font_bold, color=self.primary_rgb)
        y += 13
        for line in recipient_lines:
            self.page.insert_text(pymupdf.Point(40, y), line, fontsize=8.5, fontname=self.font_reg, color=(0.2, 0.2, 0.2))
            y += 11

        if ship_to_lines:
            sy = y_start + 14
            self.page.insert_text(pymupdf.Point(320, sy), "SHIP TO / DELIVERY DESTINATION:", fontsize=8.5, fontname=self.font_bold, color=self.primary_rgb)
            sy += 13
            for line in ship_to_lines:
                self.page.insert_text(pymupdf.Point(320, sy), line, fontsize=8.5, fontname=self.font_reg, color=(0.2, 0.2, 0.2))
                sy += 11
            y = max(y, sy)

        return y + 10

    def draw_items_table(self, y_start, columns, rows):
        """
        columns: list of dicts: {'name': str, 'x': float, 'w': float, 'align': 'left'|'right'|'center'}
        rows: list of lists with values
        """
        table_top = y_start
        header_h = 20

        # Draw header background
        self.page.draw_rect(pymupdf.Rect(40, table_top, 555, table_top + header_h), color=None, fill=self.primary_rgb)

        font_b = pymupdf.Font(self.font_bold)
        font_r = pymupdf.Font(self.font_reg)

        for col in columns:
            title = col['name']
            w = font_b.text_length(title, 8.5)
            if col['align'] == 'left':
                tx = col['x'] + 4
            elif col['align'] == 'right':
                tx = col['x'] + col['w'] - w - 4
            else:
                tx = col['x'] + (col['w'] - w) / 2
            self.page.insert_text(pymupdf.Point(tx, table_top + 13.5), title, fontsize=8.5, fontname=self.font_bold, color=(1, 1, 1))

        cur_y = table_top + header_h
        for idx, row in enumerate(rows):
            row_h = 20
            # Alternate row fill
            if idx % 2 == 1:
                self.page.draw_rect(pymupdf.Rect(40, cur_y, 555, cur_y + row_h), color=None, fill=(0.97, 0.98, 0.99))

            # Bottom cell border
            self.page.draw_line(pymupdf.Point(40, cur_y + row_h), pymupdf.Point(555, cur_y + row_h), color=(0.9, 0.92, 0.94), width=0.5)

            for col_idx, col in enumerate(columns):
                val_str = str(row[col_idx])
                w = font_r.text_length(val_str, 8.5)
                if col['align'] == 'left':
                    tx = col['x'] + 4
                elif col['align'] == 'right':
                    tx = col['x'] + col['w'] - w - 4
                else:
                    tx = col['x'] + (col['w'] - w) / 2
                self.page.insert_text(pymupdf.Point(tx, cur_y + 13.5), val_str, fontsize=8.5, fontname=self.font_reg, color=(0.15, 0.15, 0.15))

            cur_y += row_h

        # Table outer border
        self.page.draw_rect(pymupdf.Rect(40, table_top, 555, cur_y), color=(0.82, 0.85, 0.9), fill=None, width=0.8)
        return cur_y + 12

    def draw_totals(self, y_start, totals_list):
        """totals_list: list of tuples (label, formatted_value, is_bold)"""
        box_w = 220
        box_left = 555 - box_w
        cur_y = y_start
        font_b = pymupdf.Font(self.font_bold)
        font_r = pymupdf.Font(self.font_reg)

        for label, val, is_bold in totals_list:
            row_h = 20 if is_bold else 16
            f_name = self.font_bold if is_bold else self.font_reg
            f_size = 10 if is_bold else 8.5
            color = self.primary_rgb if is_bold else (0.2, 0.2, 0.2)

            if is_bold:
                # Highlight box for grand total
                self.page.draw_rect(pymupdf.Rect(box_left - 10, cur_y - 2, 555, cur_y + row_h - 2), color=(0.8, 0.85, 0.92), fill=(0.93, 0.96, 1.0), width=0.8)

            self.page.insert_text(pymupdf.Point(box_left, cur_y + 11), label, fontsize=f_size, fontname=f_name, color=color)

            f_obj = font_b if is_bold else font_r
            val_w = f_obj.text_length(val, f_size)
            self.page.insert_text(pymupdf.Point(555 - val_w - 6, cur_y + 11), val, fontsize=f_size, fontname=f_name, color=color)

            cur_y += row_h

        return cur_y + 15

    def draw_bank_details(self, y_start, bank_info):
        """Draws bank details box on left side."""
        box_w = 260
        box_h = len(bank_info) * 14 + 20
        self.page.draw_rect(pymupdf.Rect(40, y_start, 40 + box_w, y_start + box_h), color=(0.85, 0.88, 0.92), fill=(0.98, 0.98, 0.99), width=0.8)

        self.page.insert_text(pymupdf.Point(48, y_start + 13), "REMITTANCE / BANKING DETAILS", fontsize=8.5, fontname=self.font_bold, color=self.primary_rgb)

        cur_y = y_start + 26
        for label, val in bank_info.items():
            self.page.insert_text(pymupdf.Point(48, cur_y), f"{label}:", fontsize=8, fontname=self.font_reg, color=(0.4, 0.4, 0.4))
            self.page.insert_text(pymupdf.Point(125, cur_y), str(val), fontsize=8, fontname=self.font_bold, color=(0.15, 0.15, 0.15))
            cur_y += 14

        return y_start + box_h + 10

    def draw_fraud_alert_box(self, y_start, lines):
        """Draws high-visibility red/amber warning box."""
        box_top = y_start
        box_h = len(lines) * 15 + 18
        self.page.draw_rect(pymupdf.Rect(40, box_top, 555, box_top + box_h), color=(0.85, 0.2, 0.2), fill=(1.0, 0.96, 0.95), width=1.2)

        cur_y = box_top + 16
        for idx, line in enumerate(lines):
            f_name = self.font_bold if idx == 0 else self.font_reg
            color = (0.8, 0.1, 0.1) if idx == 0 else (0.4, 0.1, 0.1)
            self.page.insert_text(pymupdf.Point(52, cur_y), line, fontsize=9, fontname=f_name, color=color)
            cur_y += 15

        return box_top + box_h + 10

    def draw_signatory_and_footer(self, y_start, company_name, notes=None):
        if notes:
            self.page.insert_text(pymupdf.Point(40, y_start), f"Notes: {notes}", fontsize=8, fontname=self.font_reg, color=(0.45, 0.45, 0.45))
            y_start += 16

        # Signature box on right
        sig_left = 390
        self.page.insert_text(pymupdf.Point(sig_left, y_start + 15), f"For {company_name}", fontsize=8.5, fontname=self.font_bold, color=(0.2, 0.2, 0.2))
        self.page.draw_line(pymupdf.Point(sig_left, y_start + 50), pymupdf.Point(540, y_start + 50), color=(0.7, 0.7, 0.7), width=0.8)
        self.page.insert_text(pymupdf.Point(sig_left + 15, y_start + 62), "Authorized Signatory", fontsize=8, fontname=self.font_reg, color=(0.5, 0.5, 0.5))

        # Bottom footer note
        self.page.insert_text(pymupdf.Point(170, 810), "This is a computer-generated tax document and requires no physical seal.", fontsize=7.5, fontname=self.font_reg, color=(0.6, 0.6, 0.6))

    def save(self):
        full_path = os.path.join(INVOICES_DIR, self.filename)
        self.doc.save(full_path)
        self.doc.close()
        return full_path


# ==============================================================================
# 4. Individual Invoice Generators
# ==============================================================================

def generate_pdf_invoice_01():
    """01_happy_shree_ganesh_inr.pdf: Clean Indian GST Tax Invoice, exact match on PO-2026-1041."""
    b = InvoicePdfBuilder("01_happy_shree_ganesh_inr.pdf", primary_rgb=(0.06, 0.24, 0.44))
    b.draw_header_banner("TAX INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Shree Ganesh Packaging Pvt Ltd",
        address_lines=[
            "Plot No. 42, MIDC Industrial Area, Andheri East",
            "Mumbai, Maharashtra 400093, India",
            "Email: accounts@shreeganeshpkg.com | Phone: +91 22 2830 5500"
        ],
        tax_id_label="GSTIN",
        tax_id_val="27AABCS1234F1Z5",
        extra_info="State: Maharashtra (Code: 27)"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="TAX INVOICE",
        meta_dict={
            "Invoice No": "INV-2026-0081",
            "Invoice Date": "2026-10-28",
            "Due Date": "2026-11-27",
            "PO Reference": "PO-2026-1041",
            "Payment Terms": "NET 30",
            "Place of Supply": "Maharashtra (27)"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "GSTIN: 27AAACA1234A1Z1 | State: Maharashtra (27)"
        ],
        ship_to_lines=[
            "Acme Manufacturing Central Warehouse",
            "Gate 3, Hinjewadi Tech Zone",
            "Pune, MH 411057, India"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 90, 'align': 'left'},
        {'name': "Description of Goods", 'x': 170, 'w': 185, 'align': 'left'},
        {'name': "Qty", 'x': 355, 'w': 50, 'align': 'right'},
        {'name': "Unit Price (₹)", 'x': 405, 'w': 75, 'align': 'right'},
        {'name': "Amount (₹)", 'x': 480, 'w': 75, 'align': 'right'},
    ]

    rows = [
        ["1", "PKG-BOX-L", "Corrugated Export Cartons (Double Wall)", "2000", "75.00", "150,000.00"],
        ["2", "PKG-TAPE-HD", "Heavy Duty Strapping Rolls", "500", "100.00", "50,000.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "HDFC Bank Ltd",
        "Account Name": "Shree Ganesh Packaging Pvt Ltd",
        "Account No": "50200012345678",
        "IFSC Code": "HDFC0001234",
        "Branch": "Andheri East, Mumbai"
    })

    y_totals = b.draw_totals(y_table, [
        ("Subtotal (Taxable Value):", "INR 200,000.00", False),
        ("IGST (18.00%):", "INR 36,000.00", False),
        ("Total Invoice Amount:", "INR 236,000.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Shree Ganesh Packaging Pvt Ltd", "Payment required within 30 days of invoice date.")
    return b.save()


def generate_pdf_invoice_02():
    """02_split_part1_apex_inr.pdf: Apex Industrial Components Pvt Ltd, PO-2026-1042 partial delivery 1 (6 units, ₹60,000)."""
    b = InvoicePdfBuilder("02_split_part1_apex_inr.pdf", primary_rgb=(0.12, 0.32, 0.28))
    b.draw_header_banner("TAX INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Apex Industrial Components Pvt Ltd",
        address_lines=[
            "Works & Regd Office: 14-B Industrial Estate, Bhosari",
            "Pune, Maharashtra 411026, India",
            "Email: billing@apexindustrial.in | Phone: +91 20 2712 9800"
        ],
        tax_id_label="GSTIN",
        tax_id_val="27AAECA9876B1Z2",
        extra_info="State: Maharashtra (Code: 27)"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="TAX INVOICE",
        meta_dict={
            "Invoice No": "APEX-26-101",
            "Invoice Date": "2026-10-20",
            "Due Date": "2026-11-19",
            "PO Reference": "PO-2026-1042",
            "Milestone": "Batch 1 of 2 (6 Units)",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "GSTIN: 27AAACA1234A1Z1"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 100, 'align': 'left'},
        {'name': "Description", 'x': 180, 'w': 200, 'align': 'left'},
        {'name': "Qty", 'x': 380, 'w': 45, 'align': 'right'},
        {'name': "Unit Price (₹)", 'x': 425, 'w': 65, 'align': 'right'},
        {'name': "Amount (₹)", 'x': 490, 'w': 65, 'align': 'right'},
    ]

    rows = [
        ["1", "CNC-SPINDLE", "High-Torque CNC Spindle Assembly (Milestone Batch 1)", "6", "10000.00", "60000.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "ICICI Bank Ltd",
        "Account Name": "Apex Industrial Components Pvt Ltd",
        "Account No": "91827364501234",
        "IFSC Code": "ICIC0000451",
        "Branch": "Bhosari Branch, Pune"
    })

    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "INR 60,000.00", False),
        ("Taxes / GST (0.00%):", "INR 0.00", False),
        ("Total Amount Due:", "INR 60,000.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Apex Industrial Components Pvt Ltd", "Milestone 1 fulfillment against PO-2026-1042.")
    return b.save()


def generate_pdf_invoice_03():
    """03_split_part2_apex_inr.pdf: Apex Industrial Components Pvt Ltd, PO-2026-1042 partial delivery 2 (4 units, ₹40,000)."""
    b = InvoicePdfBuilder("03_split_part2_apex_inr.pdf", primary_rgb=(0.12, 0.32, 0.28))
    b.draw_header_banner("TAX INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Apex Industrial Components Pvt Ltd",
        address_lines=[
            "Works & Regd Office: 14-B Industrial Estate, Bhosari",
            "Pune, Maharashtra 411026, India",
            "Email: billing@apexindustrial.in | Phone: +91 20 2712 9800"
        ],
        tax_id_label="GSTIN",
        tax_id_val="27AAECA9876B1Z2",
        extra_info="State: Maharashtra (Code: 27)"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="TAX INVOICE",
        meta_dict={
            "Invoice No": "APEX-26-102",
            "Invoice Date": "2026-10-25",
            "Due Date": "2026-11-24",
            "PO Reference": "PO-2026-1042",
            "Milestone": "Batch 2 of 2 (4 Units)",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "GSTIN: 27AAACA1234A1Z1"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 100, 'align': 'left'},
        {'name': "Description", 'x': 180, 'w': 200, 'align': 'left'},
        {'name': "Qty", 'x': 380, 'w': 45, 'align': 'right'},
        {'name': "Unit Price (₹)", 'x': 425, 'w': 65, 'align': 'right'},
        {'name': "Amount (₹)", 'x': 490, 'w': 65, 'align': 'right'},
    ]

    rows = [
        ["1", "CNC-SPINDLE", "High-Torque CNC Spindle Assembly (Milestone Batch 2)", "4", "10000.00", "40000.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "ICICI Bank Ltd",
        "Account Name": "Apex Industrial Components Pvt Ltd",
        "Account No": "91827364501234",
        "IFSC Code": "ICIC0000451",
        "Branch": "Bhosari Branch, Pune"
    })

    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "INR 40,000.00", False),
        ("Taxes / GST (0.00%):", "INR 0.00", False),
        ("Total Amount Due:", "INR 40,000.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Apex Industrial Components Pvt Ltd", "Final delivery batch completing PO-2026-1042.")
    return b.save()


def generate_pdf_invoice_04():
    """04_split_part3_overbill_apex_inr.pdf: Apex Industrial Components Pvt Ltd, PO-2026-1042 overbill (1.5 units, ₹15,000)."""
    b = InvoicePdfBuilder("04_split_part3_overbill_apex_inr.pdf", primary_rgb=(0.12, 0.32, 0.28))
    b.draw_header_banner("TAX INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Apex Industrial Components Pvt Ltd",
        address_lines=[
            "Works & Regd Office: 14-B Industrial Estate, Bhosari",
            "Pune, Maharashtra 411026, India",
            "Email: billing@apexindustrial.in | Phone: +91 20 2712 9800"
        ],
        tax_id_label="GSTIN",
        tax_id_val="27AAECA9876B1Z2",
        extra_info="State: Maharashtra (Code: 27)"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="SUPPLEMENTAL INVOICE",
        meta_dict={
            "Invoice No": "APEX-26-103",
            "Invoice Date": "2026-10-29",
            "Due Date": "2026-11-28",
            "PO Reference": "PO-2026-1042",
            "Billing Type": "Extra Spares & Surcharge",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "GSTIN: 27AAACA1234A1Z1"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 100, 'align': 'left'},
        {'name': "Description", 'x': 180, 'w': 200, 'align': 'left'},
        {'name': "Qty", 'x': 380, 'w': 45, 'align': 'right'},
        {'name': "Unit Price (₹)", 'x': 425, 'w': 65, 'align': 'right'},
        {'name': "Amount (₹)", 'x': 490, 'w': 65, 'align': 'right'},
    ]

    rows = [
        ["1", "CNC-SPINDLE", "High-Torque CNC Spindle Assembly (Extra Spares & Surcharge)", "1.5", "10000.00", "15000.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "ICICI Bank Ltd",
        "Account Name": "Apex Industrial Components Pvt Ltd",
        "Account No": "91827364501234",
        "IFSC Code": "ICIC0000451",
        "Branch": "Bhosari Branch, Pune"
    })

    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "INR 15,000.00", False),
        ("Taxes / GST (0.00%):", "INR 0.00", False),
        ("Total Amount Due:", "INR 15,000.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Apex Industrial Components Pvt Ltd", "Supplemental billing for spare accessories and precision fitting.")
    return b.save()


def generate_pdf_invoice_05():
    """05_duplicate_rescan_shree_ganesh.pdf: Disguised duplicate of #1 with slashes (INV/2026/0081),
    date 28/10/2026, RESENT COPY stamp, rendered as a slightly tilted scanned image inside PDF."""
    temp_doc = pymupdf.open()
    temp_page = temp_doc.new_page(width=595, height=842)

    # Draw base invoice
    temp_page.draw_rect(pymupdf.Rect(40, 35, 555, 38), color=None, fill=(0.1, 0.2, 0.35))
    temp_page.insert_text(pymupdf.Point(40, 65), "Shree Ganesh Packaging Pvt Ltd", fontsize=14, fontname="hebo", color=(0.1, 0.2, 0.35))
    temp_page.insert_text(pymupdf.Point(40, 78), "Plot No. 42, MIDC Industrial Area, Andheri East, Mumbai 400093", fontsize=8.5, fontname="helv", color=(0.3, 0.3, 0.3))
    temp_page.insert_text(pymupdf.Point(40, 89), "GSTIN: 27AABCS1234F1Z5 | State: Maharashtra (27)", fontsize=8.5, fontname="hebo", color=(0.2, 0.2, 0.2))

    # Meta
    temp_page.insert_text(pymupdf.Point(380, 65), "TAX INVOICE", fontsize=16, fontname="hebo", color=(0.1, 0.2, 0.35))
    temp_page.draw_rect(pymupdf.Rect(350, 75, 555, 155), color=(0.8, 0.8, 0.8), fill=(0.98, 0.98, 0.98), width=0.8)
    temp_page.insert_text(pymupdf.Point(358, 92), "Invoice No:   INV/2026/0081", fontsize=8.5, fontname="hebo", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(358, 107), "Invoice Date: 28/10/2026", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(358, 122), "Due Date:     27/11/2026", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(358, 137), "PO Reference: PO-2026-1041", fontsize=8.5, fontname="hebo", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(358, 150), "Payment Terms: NET 30", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))

    # Bill to
    temp_page.draw_line(pymupdf.Point(40, 168), pymupdf.Point(555, 168), color=(0.8, 0.8, 0.8), width=0.8)
    temp_page.insert_text(pymupdf.Point(40, 182), "BILL TO / RECIPIENT:", fontsize=8.5, fontname="hebo", color=(0.1, 0.2, 0.35))
    temp_page.insert_text(pymupdf.Point(40, 195), "Acme Manufacturing India Pvt Ltd", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(40, 207), "Plot 18, Phase II, Hinjewadi Tech Zone, Pune 411057", fontsize=8.5, fontname="helv", color=(0.2, 0.2, 0.2))
    temp_page.insert_text(pymupdf.Point(40, 219), "GSTIN: 27AAACA1234A1Z1", fontsize=8.5, fontname="helv", color=(0.2, 0.2, 0.2))

    # Items table
    temp_page.draw_rect(pymupdf.Rect(40, 235, 555, 255), fill=(0.1, 0.2, 0.35))
    temp_page.insert_text(pymupdf.Point(50, 248), "Item #", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(90, 248), "Item Code", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(180, 248), "Description", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(365, 248), "Qty", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(415, 248), "Unit Price", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(495, 248), "Amount", fontsize=8.5, fontname="hebo", color=(1, 1, 1))

    # Row 1
    temp_page.insert_text(pymupdf.Point(55, 270), "1", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(90, 270), "PKG-BOX-L", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(180, 270), "Corrugated Export Cartons (Double Wall)", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(365, 270), "2000", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(420, 270), "75.00", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(490, 270), "150,000.00", fontsize=8.5, fontname="helv")
    temp_page.draw_line(pymupdf.Point(40, 278), pymupdf.Point(555, 278), color=(0.85, 0.85, 0.85), width=0.5)

    # Row 2
    temp_page.insert_text(pymupdf.Point(55, 292), "2", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(90, 292), "PKG-TAPE-HD", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(180, 292), "Heavy Duty Strapping Rolls", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(368, 292), "500", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(417, 292), "100.00", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(495, 292), "50,000.00", fontsize=8.5, fontname="helv")
    temp_page.draw_line(pymupdf.Point(40, 300), pymupdf.Point(555, 300), color=(0.85, 0.85, 0.85), width=0.5)
    temp_page.draw_rect(pymupdf.Rect(40, 235, 555, 300), color=(0.8, 0.8, 0.8), width=0.8)

    # Totals
    temp_page.insert_text(pymupdf.Point(360, 320), "Subtotal:        INR 200,000.00", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(360, 335), "IGST (18%):      INR  36,000.00", fontsize=8.5, fontname="helv")
    temp_page.draw_rect(pymupdf.Rect(345, 345, 555, 367), color=(0.7, 0.7, 0.7), fill=(0.94, 0.94, 0.94), width=0.8)
    temp_page.insert_text(pymupdf.Point(355, 360), "Total Amount:    INR 236,000.00", fontsize=9.5, fontname="hebo")

    # Banking
    temp_page.draw_rect(pymupdf.Rect(40, 320, 320, 385), color=(0.8, 0.8, 0.8), fill=(0.98, 0.98, 0.98), width=0.8)
    temp_page.insert_text(pymupdf.Point(48, 335), "Bank: HDFC Bank Ltd | A/C: 50200012345678", fontsize=8, fontname="hebo")
    temp_page.insert_text(pymupdf.Point(48, 350), "IFSC: HDFC0001234 | Branch: Andheri East", fontsize=8, fontname="helv")
    temp_page.insert_text(pymupdf.Point(48, 365), "Payment Terms: NET 30", fontsize=8, fontname="helv")

    # Prominent angled RESENT COPY stamp
    stamp_rect = pymupdf.Rect(210, 410, 390, 455)
    temp_page.draw_rect(stamp_rect, color=(0.75, 0.15, 0.15), width=2.5)
    temp_page.insert_text(pymupdf.Point(232, 440), "RESENT COPY", fontsize=20, fontname="hebo", color=(0.75, 0.15, 0.15))

    temp_page.insert_text(pymupdf.Point(40, 500), "Scanned by Billing Operations Center - Resent for immediate payment verification.", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))

    # Convert to Pixmap
    pix = temp_page.get_pixmap(dpi=150)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    temp_doc.close()

    # Add scanner noise and paper grain
    arr = np.array(img, dtype=np.int16)
    noise = np.random.randint(-4, 5, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    scanned_img = Image.fromarray(arr)

    # Slight rotation (1.5 degrees)
    rot_img = scanned_img.rotate(1.5, resample=Image.BICUBIC, fillcolor=248)

    # Save to a fresh PDF with image + dual text overlay for robust matching
    final_doc = pymupdf.open()
    final_page = final_doc.new_page(width=595, height=842)

    img_bytes = io.BytesIO()
    rot_img.save(img_bytes, format="JPEG", quality=90)
    img_bytes.seek(0)

    final_page.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=img_bytes.getvalue())

    # Text overlay (ensures both PyMuPDF text readers and OCR capture the critical fields)
    final_page.insert_text(pymupdf.Point(50, 50), "TAX INVOICE RESENT COPY", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(360, 92), "Invoice No: INV/2026/0081", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(360, 107), "Invoice Date: 28/10/2026", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(360, 137), "PO Reference: PO-2026-1041", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(50, 70), "Shree Ganesh Packaging Pvt Ltd", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(50, 90), "GSTIN: 27AABCS1234F1Z5", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(360, 360), "Total Amount: INR 236,000.00", fontsize=1, color=(0.95, 0.95, 0.95))
    final_page.insert_text(pymupdf.Point(50, 335), "Bank: HDFC Bank Ltd A/C 50200012345678", fontsize=1, color=(0.95, 0.95, 0.95))

    out_path = os.path.join(INVOICES_DIR, "05_duplicate_rescan_shree_ganesh.pdf")
    final_doc.save(out_path)
    final_doc.close()
    return out_path


def generate_invoice_06():
    """06_scanned_muller_no_po_eur.png (and .pdf): German invoice from Müller Industrietechnik GmbH,
    RE-2026-0412, NO PO reference, European comma decimals, scanned warm tint and rotation."""
    temp_doc = pymupdf.open()
    temp_page = temp_doc.new_page(width=595, height=842)

    # Warm tinted paper background
    temp_page.draw_rect(pymupdf.Rect(0, 0, 595, 842), fill=(0.985, 0.978, 0.965))

    # Header bar
    temp_page.draw_rect(pymupdf.Rect(40, 35, 555, 38), color=None, fill=(0.18, 0.22, 0.28))

    # Company
    temp_page.insert_text(pymupdf.Point(40, 68), "Müller Industrietechnik GmbH", fontsize=14, fontname="hebo", color=(0.15, 0.2, 0.28))
    temp_page.insert_text(pymupdf.Point(40, 82), "Industriestraße 45, D-70565 Stuttgart, Deutschland", fontsize=8.5, fontname="helv", color=(0.35, 0.35, 0.35))
    temp_page.insert_text(pymupdf.Point(40, 94), "USt-IdNr. (VAT ID): DE123456789 | Amtsgericht Stuttgart HRB 724190", fontsize=8.5, fontname="hebo", color=(0.2, 0.2, 0.2))

    # Title & Metadata (Notice: NO PO REFERENCE!)
    temp_page.insert_text(pymupdf.Point(375, 65), "RECHNUNG / INVOICE", fontsize=15, fontname="hebo", color=(0.15, 0.2, 0.28))
    meta_box = pymupdf.Rect(340, 78, 555, 145)
    temp_page.draw_rect(meta_box, color=(0.82, 0.8, 0.78), fill=(0.96, 0.95, 0.93), width=0.8)
    temp_page.insert_text(pymupdf.Point(350, 95), "Rechnungs-Nr.:    RE-2026-0412", fontsize=8.5, fontname="hebo", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(350, 110), "Rechnungsdatum:   28.10.2026", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(350, 125), "Fälligkeitsdatum: 27.11.2026", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(350, 138), "Zahlungsziel:     30 Tage netto", fontsize=8.5, fontname="helv", color=(0.3, 0.3, 0.3))

    # Bill to
    temp_page.draw_line(pymupdf.Point(40, 160), pymupdf.Point(555, 160), color=(0.8, 0.8, 0.78), width=0.8)
    temp_page.insert_text(pymupdf.Point(40, 175), "RECHNUNGSEMPFÄNGER / BILL TO:", fontsize=8.5, fontname="hebo", color=(0.15, 0.2, 0.28))
    temp_page.insert_text(pymupdf.Point(40, 189), "Acme Manufacturing India Pvt Ltd", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    temp_page.insert_text(pymupdf.Point(40, 201), "Plot 18, Phase II, Hinjewadi Tech Zone", fontsize=8.5, fontname="helv", color=(0.2, 0.2, 0.2))
    temp_page.insert_text(pymupdf.Point(40, 213), "Pune, Maharashtra 411057, India", fontsize=8.5, fontname="helv", color=(0.2, 0.2, 0.2))

    # Table
    table_top = 235
    temp_page.draw_rect(pymupdf.Rect(40, table_top, 555, table_top + 20), fill=(0.18, 0.22, 0.28))
    temp_page.insert_text(pymupdf.Point(48, table_top + 14), "Pos", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(85, table_top + 14), "Artikel-Nr.", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(165, table_top + 14), "Bezeichnung / Description", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(365, table_top + 14), "Menge", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(420, table_top + 14), "Einzelpreis", fontsize=8.5, fontname="hebo", color=(1, 1, 1))
    temp_page.insert_text(pymupdf.Point(495, table_top + 14), "Gesamtpreis", fontsize=8.5, fontname="hebo", color=(1, 1, 1))

    # Row 1
    temp_page.insert_text(pymupdf.Point(52, 272), "1", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(85, 272), "HP-200", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(165, 272), "Hydraulic Pump HP-200", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(375, 272), "4", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(420, 272), "1.250,00 €", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(490, 272), "5.000,00 €", fontsize=8.5, fontname="helv")
    temp_page.draw_line(pymupdf.Point(40, 280), pymupdf.Point(555, 280), color=(0.85, 0.85, 0.83), width=0.5)

    # Row 2
    temp_page.insert_text(pymupdf.Point(52, 296), "2", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(85, 296), "SK-10", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(165, 296), "Precision Seal Kit SK-10", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(372, 296), "20", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(432, 296), "45,00 €", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(498, 296), "900,00 €", fontsize=8.5, fontname="helv")
    temp_page.draw_line(pymupdf.Point(40, 305), pymupdf.Point(555, 305), color=(0.85, 0.85, 0.83), width=0.5)
    temp_page.draw_rect(pymupdf.Rect(40, table_top, 555, 305), color=(0.8, 0.8, 0.78), width=0.8)

    # Totals
    temp_page.insert_text(pymupdf.Point(340, 328), "Zwischensumme (Netto):", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(490, 328), "5.900,00 €", fontsize=8.5, fontname="helv")

    temp_page.insert_text(pymupdf.Point(340, 344), "Umsatzsteuer / MwSt. (19%):", fontsize=8.5, fontname="helv")
    temp_page.insert_text(pymupdf.Point(490, 344), "1.121,00 €", fontsize=8.5, fontname="helv")

    temp_page.draw_rect(pymupdf.Rect(330, 354, 555, 376), color=(0.75, 0.75, 0.72), fill=(0.94, 0.93, 0.91), width=0.8)
    temp_page.insert_text(pymupdf.Point(340, 369), "Gesamtbetrag (EUR):", fontsize=9.5, fontname="hebo")
    temp_page.insert_text(pymupdf.Point(485, 369), "7.021,00 €", fontsize=9.5, fontname="hebo")

    # Bank Details
    temp_page.draw_rect(pymupdf.Rect(40, 325, 305, 395), color=(0.82, 0.8, 0.78), fill=(0.96, 0.95, 0.93), width=0.8)
    temp_page.insert_text(pymupdf.Point(48, 340), "BANKVERBINDUNG / BANK DETAILS", fontsize=8.5, fontname="hebo", color=(0.15, 0.2, 0.28))
    temp_page.insert_text(pymupdf.Point(48, 355), "Bank: Deutsche Bank AG Stuttgart", fontsize=8, fontname="helv")
    temp_page.insert_text(pymupdf.Point(48, 368), "IBAN: DE89370400440532013000", fontsize=8, fontname="hebo")
    temp_page.insert_text(pymupdf.Point(48, 381), "SWIFT / BIC: DEUTDEFF | Währung: EUR", fontsize=8, fontname="helv")

    temp_page.insert_text(pymupdf.Point(40, 420), "Bitte geben Sie bei der Überweisung die Rechnungsnummer RE-2026-0412 an.", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))

    # Render to Image
    pix = temp_page.get_pixmap(dpi=150)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    temp_doc.close()

    # Add scan texture & 1.0 degree rotation
    arr = np.array(img, dtype=np.int16)
    noise = np.random.randint(-3, 4, arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    scanned_img = Image.fromarray(arr)
    rot_img = scanned_img.rotate(1.0, resample=Image.BICUBIC, fillcolor=(250, 248, 245))

    # Save PNG
    png_path = os.path.join(INVOICES_DIR, "06_scanned_muller_no_po_eur.png")
    rot_img.save(png_path, format="PNG")

    # Also save companion PDF for universal preview
    pdf_path = os.path.join(INVOICES_DIR, "06_scanned_muller_no_po_eur.pdf")
    pdf_doc = pymupdf.open()
    pdf_page = pdf_doc.new_page(width=595, height=842)
    buf = io.BytesIO()
    rot_img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    pdf_page.insert_image(pymupdf.Rect(0, 0, 595, 842), stream=buf.getvalue())

    # Dual text overlay for searchability
    pdf_page.insert_text(pymupdf.Point(50, 68), "Müller Industrietechnik GmbH RE-2026-0412", fontsize=1, color=(0.95, 0.95, 0.95))
    pdf_page.insert_text(pymupdf.Point(50, 94), "DE123456789 28.10.2026", fontsize=1, color=(0.95, 0.95, 0.95))
    pdf_page.insert_text(pymupdf.Point(50, 272), "HP-200 Hydraulic Pump HP-200 4 1.250,00 5.000,00 EUR", fontsize=1, color=(0.95, 0.95, 0.95))
    pdf_page.insert_text(pymupdf.Point(50, 296), "SK-10 Precision Seal Kit SK-10 20 45,00 900,00 EUR", fontsize=1, color=(0.95, 0.95, 0.95))
    pdf_page.insert_text(pymupdf.Point(50, 369), "Gesamtbetrag 7.021,00 EUR IBAN DE89370400440532013000", fontsize=1, color=(0.95, 0.95, 0.95))

    pdf_doc.save(pdf_path)
    pdf_doc.close()
    return png_path


def generate_pdf_invoice_07():
    """07_fraud_bank_changed_brightline_usd.pdf: Clean US corporate PDF from Brightline Software Inc,
    PO-2026-1043, USD $12,000, prominent red/amber callout for NEW OFFSHORE BANK DETAILS."""
    b = InvoicePdfBuilder("07_fraud_bank_changed_brightline_usd.pdf", primary_rgb=(0.14, 0.24, 0.42))
    b.draw_header_banner("CORPORATE INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Brightline Software Inc",
        address_lines=[
            "500 Howard Street, Suite 400",
            "San Francisco, CA 94105, United States",
            "Email: ar-billing@brightline-cloud.io | Phone: +1 (415) 555-0199"
        ],
        tax_id_label="EIN / Tax ID",
        tax_id_val="12-3456789",
        extra_info="State of Incorporation: Delaware"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="INVOICE",
        meta_dict={
            "Invoice No": "BL-2026-990",
            "Invoice Date": "10/28/2026",
            "Due Date": "12/12/2026",
            "PO Reference": "PO-2026-1043",
            "Currency": "USD ($)",
            "Payment Terms": "NET 45"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "Attn: Accounts Payable & Enterprise IT"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 100, 'align': 'left'},
        {'name': "Product / Service Description", 'x': 180, 'w': 200, 'align': 'left'},
        {'name': "Qty", 'x': 380, 'w': 45, 'align': 'right'},
        {'name': "Unit Price ($)", 'x': 425, 'w': 65, 'align': 'right'},
        {'name': "Amount ($)", 'x': 490, 'w': 65, 'align': 'right'},
    ]

    rows = [
        ["1", "SAAS-ENT", "Brightline Enterprise Cloud License (Annual)", "1", "12,000.00", "12,000.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    # Standard totals
    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "$12,000.00", False),
        ("Sales Tax (0.00%):", "$0.00", False),
        ("Total Balance Due (USD):", "$12,000.00", True),
    ])

    # PROMINENT FRAUD / CHANGED BANK CALLOUT BOX
    fraud_alert_lines = [
        "⚠️ CRITICAL: NOTICE OF NEW REMITTANCE BANK ACCOUNT (EFFECTIVE IMMEDIATELY)",
        "Please update your electronic wire records. Our banking relationship has been migrated to:",
        "Bank Name: Offshore Commercial Bank | Account No: 999888777666 | Routing / ABA: 099999999",
        "Beneficiary: Brightline Software Inc | Swift Code: OFFSHUS33 | Country: Overseas / International",
        "DO NOT REMIT TO OUR PREVIOUS DOMESTIC ACCOUNT (000123456789). ALL WIRES MUST GO TO THE NEW ACCOUNT."
    ]
    y_alert = b.draw_fraud_alert_box(y_totals + 5, fraud_alert_lines)

    b.draw_signatory_and_footer(y_alert + 10, "Brightline Software Inc", "Annual subscription renewal for Enterprise Cloud Platform.")
    return b.save()


def generate_pdf_invoice_08():
    """08_currency_mismatch_muller_usd.pdf: Müller Industrietechnik GmbH references PO-2026-1045
    (which is a EUR PO), but is billed in US Dollars ($7,650.00)."""
    b = InvoicePdfBuilder("08_currency_mismatch_muller_usd.pdf", primary_rgb=(0.20, 0.28, 0.38))
    b.draw_header_banner("COMMERCIAL INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Müller Industrietechnik GmbH",
        address_lines=[
            "Industriestraße 45, D-70565 Stuttgart, Germany",
            "International Trade & Export Division",
            "Email: export@mueller-industrietechnik.de | Phone: +49 711 89200"
        ],
        tax_id_label="VAT ID / USt-IdNr.",
        tax_id_val="DE123456789",
        extra_info="HRB 724190 Stuttgart"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="EXPORT INVOICE",
        meta_dict={
            "Invoice No": "RE-2026-0499",
            "Invoice Date": "2026-10-28",
            "Due Date": "2026-11-27",
            "PO Reference": "PO-2026-1045",
            "Billed Currency": "USD ($)",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "Attn: International Procurement"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 90, 'align': 'left'},
        {'name': "Description", 'x': 170, 'w': 185, 'align': 'left'},
        {'name': "Qty", 'x': 355, 'w': 50, 'align': 'right'},
        {'name': "Unit Price ($)", 'x': 405, 'w': 75, 'align': 'right'},
        {'name': "Amount ($)", 'x': 480, 'w': 75, 'align': 'right'},
    ]

    rows = [
        ["1", "HP-200", "Hydraulic Pump HP-200", "4", "1,362.50", "5,450.00"],
        ["2", "SK-10", "Precision Seal Kit SK-10", "20", "49.00", "980.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "Deutsche Bank AG Stuttgart",
        "Account Name": "Müller Industrietechnik GmbH",
        "IBAN": "DE89370400440532013000",
        "SWIFT / BIC": "DEUTDEFF",
        "Settlement Currency": "USD (US Dollars)"
    })

    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "$6,430.00", False),
        ("Export Tax / VAT (19%):", "$1,220.00", False),
        ("Total Amount Due (USD):", "USD 7,650.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Müller Industrietechnik GmbH", "International export dispatch billed in USD as per global pricing desk.")
    return b.save()


def generate_invoice_09():
    """09_price_variance_lioncity_sgd.xlsx (and companion .pdf): Lion City Logistics Pte Ltd,
    PO-2026-1047, ambiguous '$' currency, Line 2 terminal handling charges $1,950 vs $1,500 (+30% price variance)."""
    # 1. Excel Generation (.xlsx)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Commercial Invoice"
    ws.views.sheetView[0].showGridLines = True

    # Styling definitions
    font_title = XlsxFont(name="Calibri", size=16, bold=True, color="1E3A8A")
    font_bold = XlsxFont(name="Calibri", size=10, bold=True, color="000000")
    font_reg = XlsxFont(name="Calibri", size=10, bold=False, color="333333")
    font_muted = XlsxFont(name="Calibri", size=9, bold=False, color="666666")
    font_th = XlsxFont(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_total = XlsxFont(name="Calibri", size=11, bold=True, color="1E3A8A")

    fill_th = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    fill_total = PatternFill(start_color="EFF6FF", end_color="EFF6FF", fill_type="solid")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    # Company Header
    ws['A1'] = "Lion City Logistics Pte Ltd"
    ws['A1'].font = font_title
    ws['A2'] = "10 Marina Boulevard, Marina Bay Financial Centre, Singapore 018983"
    ws['A2'].font = font_muted
    ws['A3'] = "UEN / Tax ID: 201912345K | Email: billing@lioncitylogistics.com.sg"
    ws['A3'].font = font_bold

    # Metadata Block
    ws['E1'] = "COMMERCIAL INVOICE"
    ws['E1'].font = font_title
    ws['E1'].alignment = Alignment(horizontal="right")

    metadata = [
        ("Invoice Number:", "LCL-SG-882"),
        ("Invoice Date:", "2026-10-28"),
        ("PO Reference:", "PO-2026-1047"),
        ("Payment Terms:", "NET 30"),
        ("Currency:", "$"),
    ]
    for idx, (lbl, val) in enumerate(metadata, start=3):
        ws[f'E{idx}'] = lbl
        ws[f'E{idx}'].font = font_muted
        ws[f'E{idx}'].alignment = Alignment(horizontal="right")
        ws[f'F{idx}'] = val
        ws[f'F{idx}'].font = font_bold
        ws[f'F{idx}'].alignment = Alignment(horizontal="left")

    # Bill To Block
    ws['A5'] = "BILL TO / CONSIGNEE:"
    ws['A5'].font = font_bold
    ws['A6'] = "Acme Manufacturing India Pvt Ltd"
    ws['A6'].font = font_bold
    ws['A7'] = "Plot 18, Phase II, Hinjewadi Tech Zone"
    ws['A7'].font = font_reg
    ws['A8'] = "Pune, Maharashtra 411057, India"
    ws['A8'].font = font_reg

    # Items Table Header
    headers = ["Line #", "Item Code", "Description of Services", "Quantity", "Unit Price ($)", "Total Amount ($)"]
    for col_idx, text in enumerate(headers, start=1):
        cell = ws.cell(row=10, column=col_idx, value=text)
        cell.font = font_th
        cell.fill = fill_th
        cell.alignment = Alignment(horizontal="center" if col_idx in [1, 4] else "right" if col_idx in [5, 6] else "left")
        cell.border = thin_border

    # Data Rows
    items_data = [
        (1, "FRT-SEA-20", "20ft Container Sea Freight (SG to JNPT)", 2, 3500.00, 7000.00),
        (2, "PORT-THC", "Terminal Handling & Documentation Charges", 1, 1950.00, 1950.00),
    ]

    for r_idx, row in enumerate(items_data, start=11):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = font_reg
            cell.border = thin_border
            if c_idx in [5, 6]:
                cell.number_format = '$#,##0.00'
                cell.alignment = Alignment(horizontal="right")
            elif c_idx in [1, 4]:
                cell.alignment = Alignment(horizontal="center")
            else:
                cell.alignment = Alignment(horizontal="left")

    # Totals
    ws['E14'] = "Subtotal:"
    ws['E14'].font = font_bold
    ws['E14'].alignment = Alignment(horizontal="right")
    ws['F14'] = 8950.00
    ws['F14'].font = font_bold
    ws['F14'].number_format = '$#,##0.00'
    ws['F14'].alignment = Alignment(horizontal="right")
    ws['F14'].border = thin_border

    ws['E15'] = "GST / Tax (0%):"
    ws['E15'].font = font_reg
    ws['E15'].alignment = Alignment(horizontal="right")
    ws['F15'] = 0.00
    ws['F15'].font = font_reg
    ws['F15'].number_format = '$#,##0.00'
    ws['F15'].alignment = Alignment(horizontal="right")
    ws['F15'].border = thin_border

    ws['E16'] = "Total Invoice Value:"
    ws['E16'].font = font_total
    ws['E16'].alignment = Alignment(horizontal="right")
    ws['E16'].fill = fill_total
    ws['F16'] = 8950.00
    ws['F16'].font = font_total
    ws['F16'].number_format = '$#,##0.00'
    ws['F16'].alignment = Alignment(horizontal="right")
    ws['F16'].fill = fill_total
    ws['F16'].border = thin_border

    # Banking Info
    ws['A14'] = "REMITTANCE INSTRUCTIONS:"
    ws['A14'].font = font_bold
    ws['A15'] = "Bank: DBS Bank Ltd Singapore"
    ws['A15'].font = font_reg
    ws['A16'] = "Account No: 0123456789 | SWIFT: DBSSSGSG"
    ws['A16'].font = font_bold

    # Column Widths
    ws.column_dimensions['A'].width = 10
    ws.column_dimensions['B'].width = 16
    ws.column_dimensions['C'].width = 44
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 20
    ws.column_dimensions['F'].width = 20

    xlsx_path = os.path.join(INVOICES_DIR, "09_price_variance_lioncity_sgd.xlsx")
    wb.save(xlsx_path)

    # 2. Companion PDF Generation (.pdf)
    b = InvoicePdfBuilder("09_price_variance_lioncity_sgd.pdf", primary_rgb=(0.12, 0.23, 0.54))
    b.draw_header_banner("COMMERCIAL INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Lion City Logistics Pte Ltd",
        address_lines=[
            "10 Marina Boulevard, Marina Bay Financial Centre",
            "Singapore 018983",
            "Email: billing@lioncitylogistics.com.sg | Tel: +65 6789 0123"
        ],
        tax_id_label="UEN / Tax ID",
        tax_id_val="201912345K",
        extra_info="Country: Singapore"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="COMMERCIAL INVOICE",
        meta_dict={
            "Invoice No": "LCL-SG-882",
            "Invoice Date": "2026-10-28",
            "Due Date": "2026-11-27",
            "PO Reference": "PO-2026-1047",
            "Currency": "$",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India"
        ]
    )

    cols = [
        {'name': "Line #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 90, 'align': 'left'},
        {'name': "Description of Services", 'x': 170, 'w': 185, 'align': 'left'},
        {'name': "Qty", 'x': 355, 'w': 50, 'align': 'right'},
        {'name': "Unit Price ($)", 'x': 405, 'w': 75, 'align': 'right'},
        {'name': "Total ($)", 'x': 480, 'w': 75, 'align': 'right'},
    ]

    rows = [
        ["1", "FRT-SEA-20", "20ft Container Sea Freight (SG to JNPT)", "2", "3,500.00", "7,000.00"],
        ["2", "PORT-THC", "Terminal Handling & Documentation Charges", "1", "1,950.00", "1,950.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "DBS Bank Ltd Singapore",
        "Account Name": "Lion City Logistics Pte Ltd",
        "Account No": "0123456789",
        "SWIFT / BIC": "DBSSSGSG",
        "Currency": "SGD (Singapore Dollars)"
    })

    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "$8,950.00", False),
        ("Tax / GST (0.00%):", "$0.00", False),
        ("Total Due ($):", "$8,950.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Lion City Logistics Pte Ltd", "Ocean freight dispatch and terminal handling operations.")
    b.save()

    return xlsx_path


def generate_invoice_10():
    """10_missing_fields_draft.docx (and companion .pdf): Word doc invoice from Shree Ganesh Packaging
    with missing invoice number ([TBD / Blank]) and arithmetic mismatch (50,000 + 9,000 = 64,000)."""
    # 1. Word Document Generation (.docx)
    doc = docx.Document()

    # Title
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(4)
    run_title = p_title.add_run("TAX INVOICE [DRAFT / PRE-BILLING REVIEW]")
    run_title.font.name = "Arial"
    run_title.font.size = Pt(16)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(0x99, 0x1B, 0x1B)  # Crimson

    # Company Header
    p_comp = doc.add_paragraph()
    p_comp.paragraph_format.space_after = Pt(12)
    r_name = p_comp.add_run("Shree Ganesh Packaging Pvt Ltd\n")
    r_name.font.name = "Arial"
    r_name.font.size = Pt(12)
    r_name.font.bold = True
    r_addr = p_comp.add_run("Plot No. 42, MIDC Industrial Area, Andheri East, Mumbai, Maharashtra 400093\nGSTIN: 27AABCS1234F1Z5 | PAN: AABCS1234F")
    r_addr.font.name = "Arial"
    r_addr.font.size = Pt(9)
    r_addr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

    # Metadata Table
    meta_table = doc.add_table(rows=4, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    meta_pairs = [
        ("Invoice Number:", "[TBD / Blank]"),
        ("Invoice Date:", "2026-10-28"),
        ("Purchase Order Ref:", "PO-2026-1041"),
        ("Payment Terms:", "NET 30"),
    ]
    for row_idx, (lbl, val) in enumerate(meta_pairs):
        cell_lbl = meta_table.cell(row_idx, 0)
        cell_val = meta_table.cell(row_idx, 1)
        cell_lbl.text = lbl
        cell_val.text = val
        cell_lbl.paragraphs[0].runs[0].font.bold = True
        cell_lbl.paragraphs[0].runs[0].font.size = Pt(9)
        cell_val.paragraphs[0].runs[0].font.size = Pt(9)
        if "[TBD" in val:
            cell_val.paragraphs[0].runs[0].font.bold = True
            cell_val.paragraphs[0].runs[0].font.color.rgb = RGBColor(0xDC, 0x26, 0x26)

    # Customer
    p_cust = doc.add_paragraph()
    p_cust.paragraph_format.space_before = Pt(12)
    p_cust.paragraph_format.space_after = Pt(6)
    r_cust_title = p_cust.add_run("BILLED TO / CUSTOMER:\n")
    r_cust_title.font.bold = True
    r_cust_title.font.size = Pt(10)
    r_cust = p_cust.add_run("Acme Manufacturing India Pvt Ltd\nPlot 18, Phase II, Hinjewadi Tech Zone, Pune 411057\nGSTIN: 27AAACA1234A1Z1")
    r_cust.font.size = Pt(9)

    # Line Items Table
    item_table = doc.add_table(rows=2, cols=5)
    item_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    headers = ["Item Code", "Description", "Qty", "Unit Price (₹)", "Amount (₹)"]
    for c_idx, h in enumerate(headers):
        cell = item_table.cell(0, c_idx)
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(9)

    row1 = ["PKG-TAPE-HD", "Heavy Duty Strapping Rolls", "500", "100.00", "50,000.00"]
    for c_idx, val in enumerate(row1):
        cell = item_table.cell(1, c_idx)
        cell.text = val
        cell.paragraphs[0].runs[0].font.size = Pt(9)

    # Summary Paragraph with Arithmetic Mismatch
    p_summary = doc.add_paragraph()
    p_summary.paragraph_format.space_before = Pt(12)
    p_summary.paragraph_format.space_after = Pt(6)

    r_sub = p_summary.add_run("Subtotal (Taxable): INR 50,000.00\n")
    r_sub.font.size = Pt(9.5)
    r_tax = p_summary.add_run("IGST 18%: INR 9,000.00\n")
    r_tax.font.size = Pt(9.5)
    r_tot = p_summary.add_run("TOTAL PAYABLE: INR 64,000.00  *(Note: 50,000 + 9,000 != 64,000)*")
    r_tot.font.bold = True
    r_tot.font.size = Pt(11)
    r_tot.font.color.rgb = RGBColor(0xDC, 0x26, 0x26)

    # Bank Details
    p_bank = doc.add_paragraph()
    p_bank.paragraph_format.space_before = Pt(10)
    p_bank.add_run("Bank Remittance Details:\n").font.bold = True
    p_bank.add_run("Bank: HDFC Bank Ltd | A/C: 50200012345678 | IFSC: HDFC0001234\nDraft copy pending internal sign-off.").font.size = Pt(8.5)

    docx_path = os.path.join(INVOICES_DIR, "10_missing_fields_draft.docx")
    doc.save(docx_path)

    # 2. Companion PDF Generation (.pdf)
    b = InvoicePdfBuilder("10_missing_fields_draft.pdf", primary_rgb=(0.60, 0.15, 0.15))
    b.draw_header_banner("TAX INVOICE [DRAFT REVIEW]")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Shree Ganesh Packaging Pvt Ltd [DRAFT]",
        address_lines=[
            "Plot No. 42, MIDC Industrial Area, Andheri East",
            "Mumbai, Maharashtra 400093, India",
            "GSTIN: 27AABCS1234F1Z5 | State: Maharashtra (27)"
        ],
        tax_id_label="Status",
        tax_id_val="UNASSIGNED DRAFT COPY",
        extra_info="Pre-Billing Verification"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="DRAFT INVOICE",
        meta_dict={
            "Invoice No": "[TBD / Blank]",
            "Invoice Date": "2026-10-28",
            "Due Date": "2026-11-27",
            "PO Reference": "PO-2026-1041",
            "Document State": "DRAFT",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "GSTIN: 27AAACA1234A1Z1"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 100, 'align': 'left'},
        {'name': "Description", 'x': 180, 'w': 200, 'align': 'left'},
        {'name': "Qty", 'x': 380, 'w': 45, 'align': 'right'},
        {'name': "Unit Price (₹)", 'x': 425, 'w': 65, 'align': 'right'},
        {'name': "Amount (₹)", 'x': 490, 'w': 65, 'align': 'right'},
    ]

    rows = [
        ["1", "PKG-TAPE-HD", "Heavy Duty Strapping Rolls", "500", "100.00", "50,000.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "HDFC Bank Ltd",
        "Account Name": "Shree Ganesh Packaging Pvt Ltd",
        "Account No": "50200012345678",
        "IFSC Code": "HDFC0001234",
        "Note": "Draft copy pending invoice number assignment."
    })

    # Arithmetic error: 50,000 + 9,000 = 59,000 != 64,000!
    y_totals = b.draw_totals(y_table, [
        ("Subtotal:", "INR 50,000.00", False),
        ("IGST (18.00%):", "INR 9,000.00", False),
        ("Total Amount (Arithmetic Error!):", "INR 64,000.00", True),
    ])

    b.draw_signatory_and_footer(max(y_bank, y_totals) + 10, "Shree Ganesh Packaging Pvt Ltd", "Draft invoice for review. Missing official invoice number and contains total mismatch.")
    b.save()

    return docx_path


def generate_pdf_invoice_11():
    """11_bundled_embedded_tax_tolerance_inr.pdf: Clean PDF from Shree Ganesh Packaging against PO-2026-1041
    where 2 PO lines are bundled into a single line item 'Complete Packaging Supply (Cartons & Strapping)'
    with embedded 18% GST and a minor ₹450 freight difference (Total ₹2,36,450 vs PO ₹2,36,000 -> +0.19% within 1% tolerance)."""
    b = InvoicePdfBuilder("11_bundled_embedded_tax_tolerance_inr.pdf", primary_rgb=(0.06, 0.24, 0.44))
    b.draw_header_banner("TAX INVOICE")

    y_comp = b.draw_company_block(
        y_start=58,
        name="Shree Ganesh Packaging Pvt Ltd",
        address_lines=[
            "Plot No. 42, MIDC Industrial Area, Andheri East",
            "Mumbai, Maharashtra 400093, India",
            "Email: accounts@shreeganeshpkg.com | Phone: +91 22 2830 5500"
        ],
        tax_id_label="GSTIN",
        tax_id_val="27AABCS1234F1Z5",
        extra_info="State: Maharashtra (Code: 27)"
    )

    y_meta = b.draw_invoice_meta_box(
        y_start=55,
        title="CONSOLIDATED INVOICE",
        meta_dict={
            "Invoice No": "INV-2026-0095",
            "Invoice Date": "2026-10-30",
            "Due Date": "2026-11-29",
            "PO Reference": "PO-2026-1041",
            "Supply Type": "Bundled Consumables",
            "Payment Terms": "NET 30"
        }
    )

    y_bill = b.draw_bill_to(
        y_start=max(y_comp, y_meta) + 8,
        recipient_lines=[
            "Acme Manufacturing India Pvt Ltd",
            "Plot 18, Phase II, Hinjewadi Tech Zone",
            "Pune, Maharashtra 411057, India",
            "GSTIN: 27AAACA1234A1Z1"
        ]
    )

    cols = [
        {'name': "Item #", 'x': 40, 'w': 40, 'align': 'center'},
        {'name': "Item Code", 'x': 80, 'w': 90, 'align': 'left'},
        {'name': "Description of Bundled Supply", 'x': 170, 'w': 185, 'align': 'left'},
        {'name': "Qty", 'x': 355, 'w': 50, 'align': 'right'},
        {'name': "Unit Price (₹)", 'x': 405, 'w': 75, 'align': 'right'},
        {'name': "Amount (₹)", 'x': 480, 'w': 75, 'align': 'right'},
    ]

    rows = [
        ["1", "PKG-COMBO", "Complete Packaging Supply (Cartons & Strapping)", "1", "236,450.00", "236,450.00"]
    ]

    y_table = b.draw_items_table(y_bill, cols, rows)

    y_bank = b.draw_bank_details(y_table, {
        "Bank Name": "HDFC Bank Ltd",
        "Account Name": "Shree Ganesh Packaging Pvt Ltd",
        "Account No": "50200012345678",
        "IFSC Code": "HDFC0001234",
        "Branch": "Andheri East, Mumbai"
    })

    y_totals = b.draw_totals(y_table, [
        ("Base Value (Embedded):", "INR 200,381.36", False),
        ("Embedded IGST (18%):", "INR 36,068.64", False),
        ("Freight & Rounding Adjustment:", "INR 450.00", False),
        ("Total Invoice Amount:", "INR 236,450.00", True),
    ])

    b.draw_signatory_and_footer(
        max(y_bank, y_totals) + 10,
        "Shree Ganesh Packaging Pvt Ltd",
        "All-inclusive bundled packaging delivery (Cartons + Strapping) under PO-2026-1041. Tax inclusive with standard handling."
    )
    return b.save()


# ==============================================================================
# 5. Master Generator Runner: generate_all()
# ==============================================================================

def generate_all():
    """Generates all master data CSVs, JSON metadata, and 10+ multi-format sample invoices."""
    print("=" * 70)
    print("ClearPay AP - Sample Data & Multi-Format Invoice Generator")
    print("=" * 70)

    # 1. Reference CSVs
    print("\n[1/3] Generating reference data CSVs...")
    generate_reference_csvs()

    # 2. Metadata JSONs
    print("\n[2/3] Generating scenario and email JSON metadata...")
    generate_metadata_json()

    # 3. Sample Invoices
    print("\n[3/3] Generating 10+ multi-format invoice files...")
    os.makedirs(INVOICES_DIR, exist_ok=True)

    files_generated = []
    files_generated.append(generate_pdf_invoice_01())
    files_generated.append(generate_pdf_invoice_02())
    files_generated.append(generate_pdf_invoice_03())
    files_generated.append(generate_pdf_invoice_04())
    files_generated.append(generate_pdf_invoice_05())
    files_generated.append(generate_invoice_06())
    files_generated.append(generate_pdf_invoice_07())
    files_generated.append(generate_pdf_invoice_08())
    files_generated.append(generate_invoice_09())
    files_generated.append(generate_invoice_10())
    files_generated.append(generate_pdf_invoice_11())

    print("\n" + "=" * 70)
    print("VERIFICATION & SUMMARY OF GENERATED ARTIFACTS:")
    print("=" * 70)

    # Check reference files
    expected_csvs = [
        "vendors.csv",
        "purchase_orders.csv",
        "purchase_orders_initial.csv",
        "po_lines.csv",
        "fx_rates.csv",
        "sample_scenarios.json",
        "sample_emails.json",
    ]
    for filename in expected_csvs:
        path = os.path.join(DATA_DIR, filename)
        size = os.path.getsize(path) if os.path.exists(path) else 0
        status = "OK" if size > 0 else "MISSING"
        print(f"  [DATA]    {filename:<32} {size:>8} bytes  [{status}]")

    print("-" * 70)

    # Check invoice files
    invoice_files = sorted(os.listdir(INVOICES_DIR))
    for filename in invoice_files:
        path = os.path.join(INVOICES_DIR, filename)
        size = os.path.getsize(path)
        print(f"  [INVOICE] {filename:<40} {size:>8} bytes  [OK]")

    print("=" * 70)
    print("All ClearPay AP sample data and multi-format invoices generated successfully!")
    print("=" * 70)


if __name__ == "__main__":
    generate_all()
