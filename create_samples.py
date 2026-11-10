import os
from pathlib import Path
import pymupdf

out_dir = Path(r"c:\Users\vedan\OneDrive\Desktop\Study\zamp\sample_documents")
out_dir.mkdir(parents=True, exist_ok=True)

def create_doc(filename, doc_type, vendor_name, vendor_addr, gstin, doc_no, doc_date, ref_no, items, subtotal, tax_amount, grand_total, currency="INR", terms="NET30", bank_info=""):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842) # A4 format
    
    # Header Banner
    is_quote = "QUOTATION" in doc_type.upper() or "ESTIMATE" in doc_type.upper()
    header_color = (0.05, 0.2, 0.45) if is_quote else (0.1, 0.1, 0.1) # Navy for Quote, Dark Ink for Invoice
    page.draw_rect(pymupdf.Rect(40, 40, 555, 95), color=None, fill=header_color)
    
    # Title
    page.insert_text(pymupdf.Point(55, 68), doc_type, fontsize=17, fontname="helv", color=(1, 1, 1))
    page.insert_text(pymupdf.Point(55, 84), "COMMERCIAL B2B TRANSACTION DOCUMENT", fontsize=9, fontname="helv", color=(0.8, 0.8, 0.8))
    
    # Doc No on top right
    page.insert_text(pymupdf.Point(370, 68), f"{doc_no}", fontsize=14, fontname="helv", color=(1, 1, 1))
    page.insert_text(pymupdf.Point(370, 84), f"Date: {doc_date}", fontsize=9, fontname="helv", color=(0.8, 0.8, 0.8))
    
    # Vendor & Bill To Section
    y = 125
    page.insert_text(pymupdf.Point(40, y), "ISSUED BY (VENDOR):", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
    page.insert_text(pymupdf.Point(320, y), "BILLED TO / BUYER:", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
    
    y += 16
    page.insert_text(pymupdf.Point(40, y), vendor_name, fontsize=11, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(320, y), "Acme Manufacturing India Pvt Ltd", fontsize=11, fontname="helv", color=(0.1, 0.1, 0.1))
    
    y += 14
    page.insert_text(pymupdf.Point(40, y), vendor_addr, fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page.insert_text(pymupdf.Point(320, y), "Plot 42, Hinjewadi Phase 2, Pune, MH, India", fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    
    y += 14
    page.insert_text(pymupdf.Point(40, y), f"GSTIN / Tax ID: {gstin}", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(320, y), "GSTIN: 27AABCA1234F1Z9", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    
    # Metadata bar
    y += 24
    page.draw_rect(pymupdf.Rect(40, y, 555, y + 30), color=(0.85, 0.85, 0.85), fill=(0.96, 0.96, 0.96))
    if ref_no:
        page.insert_text(pymupdf.Point(50, y + 18), f"Reference: {ref_no}", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(260, y + 18), f"Payment Terms: {terms}", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(440, y + 18), f"Currency: {currency}", fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
    
    # Table Header
    y += 45
    page.draw_rect(pymupdf.Rect(40, y, 555, y + 24), color=None, fill=(0.9, 0.92, 0.95) if is_quote else (0.9, 0.9, 0.9))
    page.insert_text(pymupdf.Point(48, y + 16), "#", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(70, y + 16), "ITEM CODE / DESCRIPTION", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(330, y + 16), "QTY", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(380, y + 16), "UNIT RATE", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(475, y + 16), "TOTAL AMOUNT", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    
    # Table Rows
    curr_sym = "₹" if currency == "INR" else "$"
    row_y = y + 24
    for idx, itm in enumerate(items):
        bg = (0.98, 0.98, 0.98) if idx % 2 == 1 else (1, 1, 1)
        page.draw_rect(pymupdf.Rect(40, row_y, 555, row_y + 36), color=None, fill=bg)
        page.draw_line(pymupdf.Point(40, row_y + 36), pymupdf.Point(555, row_y + 36), color=(0.88, 0.88, 0.88))
        
        qty_val = itm["qty"]
        rate_val = itm["rate"]
        amt_val = itm["amount"]
        
        page.insert_text(pymupdf.Point(48, row_y + 16), f"{idx+1:02d}", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
        page.insert_text(pymupdf.Point(70, row_y + 16), itm["code"], fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(70, row_y + 28), itm["desc"], fontsize=8, fontname="helv", color=(0.35, 0.35, 0.35))
        page.insert_text(pymupdf.Point(330, row_y + 20), str(qty_val), fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(380, row_y + 20), f"{curr_sym}{rate_val:,.2f}", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
        page.insert_text(pymupdf.Point(475, row_y + 20), f"{curr_sym}{amt_val:,.2f}", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
        row_y += 36
        
    # Summary Box
    sum_y = row_y + 20
    page.draw_rect(pymupdf.Rect(320, sum_y, 555, sum_y + 85), color=(0.85, 0.85, 0.85), fill=(0.97, 0.97, 0.97))
    page.insert_text(pymupdf.Point(340, sum_y + 22), "Subtotal:", fontsize=9, fontname="helv", color=(0.3, 0.3, 0.3))
    page.insert_text(pymupdf.Point(470, sum_y + 22), f"{curr_sym}{subtotal:,.2f}", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    
    page.insert_text(pymupdf.Point(340, sum_y + 42), "Tax (GST / VAT):", fontsize=9, fontname="helv", color=(0.3, 0.3, 0.3))
    page.insert_text(pymupdf.Point(470, sum_y + 42), f"{curr_sym}{tax_amount:,.2f}", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    
    page.draw_line(pymupdf.Point(330, sum_y + 54), pymupdf.Point(545, sum_y + 54), color=(0.8, 0.8, 0.8))
    
    page.insert_text(pymupdf.Point(340, sum_y + 72), "GRAND TOTAL:", fontsize=10, fontname="helv", color=(0.1, 0.1, 0.1))
    page.insert_text(pymupdf.Point(460, sum_y + 72), f"{curr_sym}{grand_total:,.2f}", fontsize=11, fontname="helv", color=(0.05, 0.2, 0.45) if is_quote else (0.1, 0.1, 0.1))
    
    # Banking details
    if bank_info:
        page.draw_rect(pymupdf.Rect(40, sum_y, 300, sum_y + 85), color=(0.85, 0.85, 0.85), fill=(1, 1, 1))
        page.insert_text(pymupdf.Point(50, sum_y + 18), "BANK REMITTANCE DETAILS:", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
        lines = bank_info.split("\n")
        by = sum_y + 34
        for l in lines:
            page.insert_text(pymupdf.Point(50, by), l, fontsize=8, fontname="helv", color=(0.2, 0.2, 0.2))
            by += 13
            
    # Footer
    page.insert_text(pymupdf.Point(40, 780), "ClearPay AP Autonomous Ingestion • Dual Extraction & Quotation Matching Engine", fontsize=8, fontname="helv", color=(0.6, 0.6, 0.6))
    
    fpath = out_dir / filename
    doc.save(str(fpath))
    doc.close()
    print(f"Generated: {fpath.name}")

# Pair 1: Exact Match
create_doc(
    filename="01_Quotation_Apex_QTE-2026-701.pdf",
    doc_type="FORMAL COMMERCIAL QUOTATION",
    vendor_name="Apex Industrial Components Pvt Ltd",
    vendor_addr="Gat No. 408, Chakan Industrial Area, Phase II, Pune - 410501",
    gstin="27AAECA9876B1Z2",
    doc_no="QTE-2026-701",
    doc_date="2026-08-15",
    ref_no="RFQ-APEX-9921 (Valid for 90 Days)",
    items=[
        {"code": "CNC-SPINDLE-H", "desc": "High-Torque CNC Spindle Assembly 24000 RPM", "qty": 5, "rate": 20000.0, "amount": 100000.0},
        {"code": "BEAR-CERAMIC-60", "desc": "Precision Hybrid Ceramic Bearing Kits (SK-60)", "qty": 10, "rate": 2500.0, "amount": 25000.0}
    ],
    subtotal=125000.0,
    tax_amount=22500.0,
    grand_total=147500.0,
    currency="INR",
    terms="NET30 upon delivery",
    bank_info="Bank: ICICI Bank, Chakan Branch\nA/C No: 91827364501234\nIFSC: ICIC0000451"
)

create_doc(
    filename="01_Invoice_Apex_INV-2026-891.pdf",
    doc_type="TAX INVOICE",
    vendor_name="Apex Industrial Components Pvt Ltd",
    vendor_addr="Gat No. 408, Chakan Industrial Area, Phase II, Pune - 410501",
    gstin="27AAECA9876B1Z2",
    doc_no="INV-2026-891",
    doc_date="2026-11-02",
    ref_no="Quotation Ref: QTE-2026-701",
    items=[
        {"code": "CNC-SPINDLE-H", "desc": "High-Torque CNC Spindle Assembly 24000 RPM", "qty": 5, "rate": 20000.0, "amount": 100000.0},
        {"code": "BEAR-CERAMIC-60", "desc": "Precision Hybrid Ceramic Bearing Kits (SK-60)", "qty": 10, "rate": 2500.0, "amount": 25000.0}
    ],
    subtotal=125000.0,
    tax_amount=22500.0,
    grand_total=147500.0,
    currency="INR",
    terms="NET30 (Due Date: 2026-12-02)",
    bank_info="Bank: ICICI Bank, Chakan Branch\nA/C No: 91827364501234\nIFSC: ICIC0000451"
)

# Pair 2: Mismatch
create_doc(
    filename="02_Quotation_Ganesh_QTE-2026-802.pdf",
    doc_type="OFFICIAL PRICE QUOTATION",
    vendor_name="Shree Ganesh Packaging Pvt Ltd",
    vendor_addr="Plot 14, MIDC Bhosari, Pune - 411026, Maharashtra",
    gstin="27AABCS1234F1Z5",
    doc_no="QTE-2026-802",
    doc_date="2026-07-20",
    ref_no="Annual Supply Quote Ref: RFQ-SGP-108",
    items=[
        {"code": "PKG-BOX-5PLY", "desc": "5-Ply Heavy Duty Corrugated Export Cartons (60x40x40 cm)", "qty": 1000, "rate": 80.0, "amount": 80000.0},
        {"code": "TAPE-BOPP-3IN", "desc": "Industrial BOPP Strapping Rolls 3-inch 65 Micron", "qty": 200, "rate": 150.0, "amount": 30000.0}
    ],
    subtotal=110000.0,
    tax_amount=19800.0,
    grand_total=129800.0,
    currency="INR",
    terms="NET30 (Valid for 120 Days)",
    bank_info="Bank: HDFC Bank, Bhosari Branch\nA/C No: 50200012345678\nIFSC: HDFC0001234"
)

create_doc(
    filename="02_Invoice_Ganesh_INV-2026-944_MISMATCH.pdf",
    doc_type="TAX INVOICE",
    vendor_name="Shree Ganesh Packaging Pvt Ltd",
    vendor_addr="Plot 14, MIDC Bhosari, Pune - 411026, Maharashtra",
    gstin="27AABCS1234F1Z5",
    doc_no="INV-2026-944",
    doc_date="2026-11-05",
    ref_no="Quotation Ref: QTE-2026-802",
    items=[
        {"code": "PKG-BOX-5PLY", "desc": "5-Ply Heavy Duty Corrugated Export Cartons (Price Variance)", "qty": 1000, "rate": 95.0, "amount": 95000.0},
        {"code": "TAPE-BOPP-3IN", "desc": "Industrial BOPP Strapping Rolls (Extra 50 Units)", "qty": 250, "rate": 150.0, "amount": 37500.0}
    ],
    subtotal=132500.0,
    tax_amount=23850.0,
    grand_total=156350.0,
    currency="INR",
    terms="NET30 (Due Date: 2026-12-05)",
    bank_info="Bank: HDFC Bank, Bhosari Branch\nA/C No: 50200012345678\nIFSC: HDFC0001234"
)

# Pair 3: Software License & Duration
create_doc(
    filename="03_Quotation_Brightline_QTE-2026-903.pdf",
    doc_type="ANNUAL ENTERPRISE SERVICE QUOTATION",
    vendor_name="Brightline Software Inc",
    vendor_addr="548 Market St, Suite 3400, San Francisco, CA 94104, USA",
    gstin="12-3456789",
    doc_no="QTE-2026-903",
    doc_date="2026-09-01",
    ref_no="SaaS Order Form (Duration: 2026-11-01 to 2027-10-31)",
    items=[
        {"code": "SAAS-PRO-ENT", "desc": "Brightline Enterprise Cloud Platform Annual License (Tier 1)", "qty": 1, "rate": 12000.0, "amount": 12000.0}
    ],
    subtotal=12000.0,
    tax_amount=0.0,
    grand_total=12000.0,
    currency="USD",
    terms="Annual Prepaid (12 Months)",
    bank_info="Bank: JPMorgan Chase Bank, San Francisco\nA/C No: 000123456789\nWire / Routing: 021000021"
)

create_doc(
    filename="03_Invoice_Brightline_INV-2026-102.pdf",
    doc_type="COMMERCIAL INVOICE",
    vendor_name="Brightline Software Inc",
    vendor_addr="548 Market St, Suite 3400, San Francisco, CA 94104, USA",
    gstin="12-3456789",
    doc_no="INV-2026-102",
    doc_date="2026-11-01",
    ref_no="Quotation Ref: QTE-2026-903",
    items=[
        {"code": "SAAS-PRO-ENT", "desc": "Brightline Enterprise Cloud Platform Annual License (Tier 1)", "qty": 1, "rate": 12000.0, "amount": 12000.0}
    ],
    subtotal=12000.0,
    tax_amount=0.0,
    grand_total=12000.0,
    currency="USD",
    terms="NET30 (Billing Period: 2026-11-01 to 2027-10-31)",
    bank_info="Bank: JPMorgan Chase Bank, San Francisco\nA/C No: 000123456789\nWire / Routing: 021000021"
)

print("SUCCESS: ALL 6 SAMPLE DOCUMENTS GENERATED AND SAVED!")
