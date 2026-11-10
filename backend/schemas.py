from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class SourceInfo(BaseModel):
    source_type: Literal["GMAIL", "UPLOAD"] = "UPLOAD"
    filename: str
    file_format: Literal["PDF_TEXT", "PDF_SCANNED", "IMAGE", "XLSX", "DOCX"] = "PDF_TEXT"
    file_hash: str
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
    email_date: Optional[str] = None
    extraction_engine: str = "Hybrid AI + Deterministic Parser"
    thread_history: Optional[List[Dict[str, Any]]] = None


class ExtractedField(BaseModel):
    value: Optional[Any] = None
    raw: Optional[str] = None
    confidence: float = 0.98
    source_text: Optional[str] = None
    note: Optional[str] = None


class StandardLineItem(BaseModel):
    line_no: int
    item_code: Optional[str] = None
    description: str
    qty: float
    unit_price: float
    amount: float
    tax_rate: Optional[float] = None


class StandardInvoice(BaseModel):
    """Canonical Standard Invoice / Document Template that all formats normalize into."""
    document_type: str = "INVOICE"
    source_info: SourceInfo
    vendor_name: ExtractedField
    vendor_tax_id: ExtractedField
    vendor_country: ExtractedField
    vendor_bank_account: ExtractedField
    vendor_bank_code: ExtractedField
    matched_vendor_id: Optional[str] = None
    invoice_number: ExtractedField
    normalized_invoice_number: Optional[str] = None
    invoice_date: ExtractedField
    due_date: ExtractedField
    po_reference: ExtractedField
    inferred_po: bool = False
    currency: ExtractedField
    line_items: List[StandardLineItem] = Field(default_factory=list)
    subtotal: ExtractedField
    tax_amount: ExtractedField
    tax_label: str = "Tax"
    total: ExtractedField
    raw_text_preview: str = ""
    ai_summary: Optional[str] = None
    ai_flaws: List[str] = Field(default_factory=list)


class HeaderDiffItem(BaseModel):
    field: str
    label: str
    invoice_value: str
    reference_value: str
    reference_source: str
    status: Literal["MATCH", "WARN", "MISMATCH", "MISSING", "INFERRED"]
    highlight_note: str


class LineDiffItem(BaseModel):
    line_no: int
    item_code: Optional[str] = None
    description: str
    inv_qty: float
    po_qty: Optional[float] = None
    inv_unit_price: float
    po_unit_price: Optional[float] = None
    inv_amount: float
    po_amount: Optional[float] = None
    variance_amount: float = 0.0
    variance_pct: float = 0.0
    status: Literal["MATCH", "PRICE_VARIANCE", "QTY_VARIANCE", "UNORDERED_ITEM"]
    highlight_note: str


class POConsumptionSlice(BaseModel):
    run_id: str
    invoice_number: str
    amount: float
    date: str


class POConsumptionView(BaseModel):
    po_number: str
    currency: str
    po_total: float
    prior_invoiced: float
    this_invoice: float
    remaining_before: float
    remaining_after: float
    overbilled_amount: float = 0.0
    utilization_pct: float = 0.0
    prior_slices: List[POConsumptionSlice] = Field(default_factory=list)
    status: Literal["WITHIN_LIMIT", "EXACTLY_CONSUMED", "OVERBILLED", "PO_CLOSED"]


class DuplicateFieldDiff(BaseModel):
    field: str
    current_value: str
    original_value: str
    match_type: Literal["EXACT", "NORMALIZED_MATCH", "DIFFERENT"]
    note: str


class DuplicateDiffView(BaseModel):
    is_duplicate: bool = False
    duplicate_type: Optional[Literal["EXACT_HASH", "NORMALIZED_INVOICE_NO", "FUZZY_AMOUNT_DATE"]] = None
    similarity_score: int = 0
    original_run_id: str
    original_invoice_number: str
    original_filename: str
    original_date: str
    field_comparisons: List[DuplicateFieldDiff] = Field(default_factory=list)


class StoredQuotation(BaseModel):
    """Persistent Advance Expected Quotation / Bill stored before invoices arrive."""
    quotation_id: str
    quotation_number: str
    vendor_name: str
    vendor_country: str = "IN"
    vendor_tax_id: Optional[str] = None
    currency: str = "INR"
    validity_period: Optional[str] = "NET30"
    quotation_date: Optional[str] = None
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    items_count: int = 0
    total_qty: float = 0.0
    line_items: List[StandardLineItem] = Field(default_factory=list)
    filename: Optional[str] = None
    file_path: Optional[str] = None
    status: Literal["PENDING_INVOICE", "MATCHED_TO_INVOICE"] = "PENDING_INVOICE"
    matched_run_ids: List[str] = Field(default_factory=list)
    matched_invoice_numbers: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: str
    ai_summary: Optional[str] = None
    ai_flaws: List[str] = Field(default_factory=list)


class ExpectedQuotationView(BaseModel):
    """
    Extracted Expected Invoice or Quotation details and comparison against Actual Invoice.
    """
    document_name: Optional[str] = None
    quotation_number: Optional[str] = None
    quotation_id: Optional[str] = None
    vendor_tax_id: Optional[str] = None
    vendor_name: Optional[str] = None
    currency: str = "INR"
    items_count: int = 0
    total_qty: float = 0.0
    duration: Optional[str] = None
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total: float = 0.0
    match_status: Literal["EXACT_MATCH", "MISMATCH", "NO_QUOTATION"] = "NO_QUOTATION"
    match_badge_label: str = "No Quotation Linked"
    match_details: Optional[str] = None
    discrepancies: List[str] = Field(default_factory=list)
    line_items: List[StandardLineItem] = Field(default_factory=list)


class ComparisonWorkbench(BaseModel):
    """Side-by-side Compare & Highlight payload."""
    header_diffs: List[HeaderDiffItem] = Field(default_factory=list)
    line_diffs: List[LineDiffItem] = Field(default_factory=list)
    po_consumption: Optional[POConsumptionView] = None
    duplicate_diff: Optional[DuplicateDiffView] = None
    fx_comparison: Optional[Dict[str, Any]] = None
    expected_quotation: Optional[ExpectedQuotationView] = None


class StageResult(BaseModel):
    stage_id: int
    key: str
    name: str
    status: Literal["PASS", "WARN", "FAIL", "SKIPPED"]
    duration_ms: int
    summary: str
    details: List[str] = Field(default_factory=list)
    data: Optional[Dict[str, Any]] = None


class InvoiceRunResult(BaseModel):
    run_id: str
    created_at: str
    scenario_tag: Optional[str] = None
    decision: Literal["AUTO_APPROVE", "NEEDS_REVIEW", "ON_HOLD", "REJECT"]
    decision_title: str
    decision_summary: str
    reason_codes: List[str] = Field(default_factory=list)
    confidence_overall: float = 0.98
    invoice_currency: str = "INR"
    invoice_total: float = 0.0
    base_currency: str = "INR"
    base_total_inr: float = 0.0
    fx_rate_to_inr: float = 1.0
    matched_vendor_id: Optional[str] = None
    matched_vendor_name: Optional[str] = None
    matched_po_number: Optional[str] = None
    standard_invoice: StandardInvoice
    stages: List[StageResult] = Field(default_factory=list)
    comparison: ComparisonWorkbench
    recommended_action: str
    draft_email: Optional[Dict[str, str]] = None
    human_override: Optional[Dict[str, Any]] = None

    # Granular Metrics for Dashboard Columns
    source_type: Literal["UPLOAD", "GMAIL"] = "UPLOAD"
    gst_number: Optional[str] = None
    items_count: int = 0
    total_qty: float = 0.0
    duration: Optional[str] = None
    extraction_duration_sec: float = 0.4

    # Dual Document Expected Quotation & Match
    expected_quotation: Optional[ExpectedQuotationView] = None
    email_thread_history: Optional[List[Dict[str, Any]]] = None

    # Groq AI Executive Summary & Risk Flaws
    ai_summary: Optional[str] = None
    ai_flaws: List[str] = Field(default_factory=list)
    llm_brain: str = "Groq Llama-3.3-70B"

    # Contract additions (Upgrade Spec)
    ai_review: Optional[Dict[str, Any]] = None
    vendor_identity: Optional[Dict[str, Any]] = None
    policy_applied: Optional[Dict[str, Any]] = None
    read_method: Literal["text", "ocr", "vision"] = "text"

    # Mandatory Human Last-Point Approval Status
    human_approval_status: Literal[
        "PENDING_FINAL_APPROVAL",
        "NEEDS_HUMAN_APPROVAL",
        "APPROVED_BY_HUMAN",
        "REJECTED_BY_HUMAN"
    ] = "PENDING_FINAL_APPROVAL"
    human_approval_details: Optional[Dict[str, Any]] = None
