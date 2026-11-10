export type SourceType = 'GMAIL' | 'UPLOAD' | 'DRIVE' | 'WEBHOOK' | 'SAMPLE';
export type FileFormat = 'PDF_TEXT' | 'PDF_SCANNED' | 'IMAGE' | 'XLSX' | 'DOCX';
export type DecisionType = 'AUTO_APPROVE' | 'NEEDS_REVIEW' | 'ON_HOLD' | 'REJECT';
export type StageStatus = 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED';
export type DiffStatus = 'MATCH' | 'WARN' | 'MISMATCH' | 'MISSING' | 'INFERRED';
export type LineDiffStatus = 'MATCH' | 'PRICE_VARIANCE' | 'QTY_VARIANCE' | 'UNORDERED_ITEM';
export type POStatus = 'WITHIN_LIMIT' | 'EXACTLY_CONSUMED' | 'OVERBILLED' | 'PO_CLOSED';
export type VendorTrustLevel = 'PREAPPROVED' | 'STANDARD' | 'WATCHLIST' | 'BLOCKED';
export type ReadMethod = 'text' | 'ocr' | 'vision';

export interface SourceInfo {
  source_type: SourceType;
  filename: string;
  file_format: FileFormat;
  file_hash?: string;
  email_subject?: string;
  email_from?: string;
  email_date?: string;
  extraction_engine?: string;
}

export interface ExtractedField<T = any> {
  value: T;
  raw?: string;
  confidence: number;
  source_text?: string;
  note?: string;
}

export interface StandardLineItem {
  line_no: number;
  item_code?: string;
  description: string;
  qty: number;
  unit_price: number;
  amount: number;
  tax_rate?: number;
}

export interface StandardInvoice {
  document_type: string;
  source_info: SourceInfo;
  vendor_name: ExtractedField<string>;
  vendor_tax_id: ExtractedField<string>;
  vendor_country: ExtractedField<string>;
  vendor_bank_account: ExtractedField<string>;
  vendor_bank_code: ExtractedField<string>;
  matched_vendor_id?: string;
  invoice_number: ExtractedField<string>;
  normalized_invoice_number?: string;
  invoice_date: ExtractedField<string>;
  due_date: ExtractedField<string>;
  po_reference: ExtractedField<string>;
  inferred_po?: boolean;
  currency: ExtractedField<string>;
  line_items: StandardLineItem[];
  subtotal: ExtractedField<number>;
  tax_amount: ExtractedField<number>;
  tax_label?: string;
  total: ExtractedField<number>;
  raw_text_preview?: string;
  ai_summary?: string | null;
  ai_flaws?: string[];
  llm_brain?: string;
}

export interface HeaderDiffItem {
  field: string;
  label: string;
  invoice_value: string;
  reference_value: string;
  reference_source?: string;
  status: DiffStatus;
  highlight_note?: string;
}

export interface LineDiffItem {
  line_no: number;
  item_code?: string;
  description: string;
  inv_qty: number;
  po_qty?: number;
  inv_unit_price: number;
  po_unit_price?: number;
  inv_amount: number;
  po_amount?: number;
  variance_amount: number;
  variance_pct: number;
  status: LineDiffStatus;
  highlight_note?: string;
}

export interface POConsumptionSlice {
  run_id: string;
  invoice_number: string;
  amount: number;
  date: string;
}

export interface POConsumptionView {
  po_number: string;
  currency: string;
  po_total: number;
  prior_invoiced: number;
  this_invoice: number;
  remaining_before: number;
  remaining_after: number;
  overbilled_amount: number;
  utilization_pct: number;
  prior_slices?: POConsumptionSlice[];
  status: POStatus;
}

export interface DuplicateFieldDiff {
  field: string;
  current_value: string;
  original_value: string;
  match_type: 'EXACT' | 'NORMALIZED_MATCH' | 'DIFFERENT';
  note: string;
}

export interface DuplicateDiffView {
  is_duplicate: boolean;
  duplicate_type?: 'EXACT_HASH' | 'NORMALIZED_INVOICE_NO' | 'FUZZY_AMOUNT_DATE';
  similarity_score?: number;
  original_run_id?: string;
  original_invoice_number?: string;
  original_filename?: string;
  original_date?: string;
  field_comparisons?: DuplicateFieldDiff[];
}

export interface FXComparisonView {
  invoice_currency: string;
  invoice_amount: number;
  po_currency: string;
  po_amount: number;
  rate_to_inr_inv: number;
  rate_to_inr_po: number;
  inv_in_inr: number;
  po_in_inr: number;
  inr_variance: number;
  note: string;
}

export interface ExpectedQuotationView {
  document_name?: string;
  quotation_number?: string;
  quotation_id?: string;
  vendor_tax_id?: string;
  vendor_name?: string;
  currency: string;
  items_count: number;
  total_qty: number;
  duration?: string;
  subtotal: number;
  tax_amount: number;
  total: number;
  match_status: 'EXACT_MATCH' | 'MISMATCH' | 'NO_QUOTATION';
  match_badge_label: string;
  match_details?: string;
  discrepancies?: string[];
  line_items?: StandardLineItem[];
}

export interface ComparisonWorkbench {
  header_diffs: HeaderDiffItem[];
  line_diffs: LineDiffItem[];
  po_consumption?: POConsumptionView | null;
  duplicate_diff?: DuplicateDiffView | null;
  fx_comparison?: FXComparisonView | null;
  expected_quotation?: ExpectedQuotationView | null;
}

export interface StageResult {
  stage_id: number;
  key: string;
  name: string;
  status: StageStatus;
  duration_ms: number;
  summary: string;
  details: string[];
  data?: Record<string, any>;
}

export interface HumanOverride {
  original_decision?: DecisionType;
  new_decision?: DecisionType;
  prior_decision?: DecisionType;
  reviewer?: string;
  overridden_by?: string;
  comment?: string;
  timestamp?: string;
  overridden_at?: string;
}

export interface AICheckItem {
  label: string;
  ok: boolean;
  note: string;
}

export interface AIReviewResult {
  verdict: 'APPROVE' | 'REVIEW' | 'REJECT';
  confidence: number;
  summary: string;
  checks: AICheckItem[];
  concerns: string[];
  mode: 'ai' | 'rules';
}

export interface VendorIdentityResult {
  same_entity: boolean;
  confidence: number;
  reason: string;
  name_on_invoice: string;
  name_on_record: string;
}

export interface PolicyAppliedResult {
  trust: VendorTrustLevel;
  limit: number | null;
  price_tolerance_pct: number | null;
  total_tolerance_pct: number | null;
  notes: string[];
}

export interface InvoiceRunResult {
  run_id: string;
  created_at: string;
  scenario_tag?: string;
  decision: DecisionType;
  decision_title?: string;
  decision_summary?: string;
  reason_codes: string[];
  confidence_overall: number;
  invoice_currency: string;
  invoice_total: number;
  base_currency: string;
  base_total_inr?: number;
  base_Total_inr?: number;
  fx_rate_to_inr: number;
  matched_vendor_id?: string;
  matched_vendor_name?: string;
  matched_po_number?: string;
  standard_invoice: StandardInvoice;
  stages: StageResult[];
  comparison: ComparisonWorkbench;
  recommended_action?: string;
  human_override?: HumanOverride;

  // New contract fields
  ai_review?: AIReviewResult | null;
  vendor_identity?: VendorIdentityResult | null;
  policy_applied?: PolicyAppliedResult | null;
  read_method?: ReadMethod;

  // Summary & details
  ai_summary?: string | null;
  ai_flaws?: string[];
  human_approval_status?: 'PENDING_FINAL_APPROVAL' | 'NEEDS_HUMAN_APPROVAL' | 'APPROVED_BY_HUMAN' | 'REJECTED_BY_HUMAN';
  human_approval_details?: {
    reviewer: string;
    timestamp: string;
    action: string;
    comment?: string;
  } | null;
  gst_number?: string | null;
}

export interface VendorPolicy {
  trust: VendorTrustLevel;
  auto_approve_limit: number | null;
  price_tolerance_pct: number | null;
  total_tolerance_pct: number | null;
  allow_without_po: boolean;
  notes: string;
}

export interface VendorStats {
  invoice_count: number;
  approved_total_inr: number;
  last_invoice_date: string | null;
}

export interface VendorMaster {
  vendor_id: string;
  legal_name: string;
  aliases: string;
  country: string;
  tax_id: string;
  default_currency: string;
  bank_account: string;
  bank_code: string;
  status: string; // 'ACTIVE' | 'INACTIVE'
  payment_terms: string;

  // Policy fields (either nested under .policy or flattened)
  policy?: VendorPolicy;
  trust?: VendorTrustLevel;
  auto_approve_limit?: number | null;
  price_tolerance_pct?: number | null;
  total_tolerance_pct?: number | null;
  allow_without_po?: boolean;
  notes?: string;

  // Stats fields (returned by GET /api/vendors)
  invoice_count?: number;
  approved_total_inr?: number;
  last_invoice_date?: string | null;
}

export interface POLineItem {
  po_number: string;
  line_no: number;
  item_code: string;
  description: string;
  qty: number;
  unit_price: number;
  amount: number;
  tax_rate?: number;
}

export interface PurchaseOrder {
  po_number: string;
  vendor_id: string;
  vendor_name?: string;
  currency: string;
  po_date: string;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
  invoiced_amount: number;
  remaining_amount: number;
  status: string;
  approver?: string;
  lines?: POLineItem[];
}

export interface SystemSettings {
  default_price_tolerance_pct: number;
  default_total_tolerance_pct: number;
  default_auto_approve_limit_inr: number | null;
  duplicate_window_days: number;
  require_po_above_inr: number;
  ai_review_enabled: boolean;
  ai_min_confidence: number;
  api_key?: string;
  has_api_key?: boolean;
}

export interface AIStatus {
  enabled: boolean;
  mode: 'ai' | 'rules';
}

export interface FXRate {
  currency: string;
  rate_to_inr: number;
  symbol: string;
  updated_at: string;
}

export interface StoredQuotation {
  quotation_id: string;
  quotation_number: string;
  vendor_name: string;
  currency: string;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
  status: string;
  created_at: string;
  line_items?: StandardLineItem[];
}

export interface SampleScenario {
  id: string;
  title: string;
  category: string;
  filename: string;
  vendor_name: string;
  po_number: string;
  amount_formatted: string;
  expected_decision: DecisionType;
  description: string;
}

export interface GmailMessage {
  id: string;
  subject: string;
  from_sender: string;
  sender_email?: string;
  date: string;
  attachment_name?: string;
  attachment_size?: string;
  currency?: string;
  processed: boolean;
  run_id?: string;
}

export interface OverviewKPIs {
  total_runs: number;
  auto_approve_count: number;
  auto_approve_pct: number;
  needs_review_count: number;
  reject_count: number;
  fraud_and_duplicates_blocked_inr: number;
  total_amount_processed_inr: number;
}

export interface OverviewResponse {
  kpis: OverviewKPIs;
  recent_runs: InvoiceRunResult[];
  pos: PurchaseOrder[];
  vendors: VendorMaster[];
  fx_rates?: FXRate[];
  quotations?: StoredQuotation[];
  sample_scenarios?: SampleScenario[];
}

export interface SendEmailToAgentResponse {
  status?: string;
  run: InvoiceRunResult | null;
  already_exists?: boolean;
  quotation_already_exists?: boolean;
  matched_quotation_number?: string;
  agent_summary?: string;
}

// ---------------------------------------------------------------------------
// Dashboard Types
// ---------------------------------------------------------------------------
export interface DashboardTotals {
  runs: number;
  approved: number;
  needs_review: number;
  on_hold: number;
  rejected: number;
  auto_rate_pct: number;
}

export interface AmountByDecision {
  AUTO_APPROVE: number;
  NEEDS_REVIEW: number;
  ON_HOLD: number;
  REJECT: number;
}

export interface VendorSpendSummary {
  name: string;
  count: number;
  total_inr: number;
}

export interface ReasonBreakdownItem {
  label: string;
  count: number;
}

export interface TrendDayItem {
  date: string;
  count: number;
  approved: number;
  flagged: number;
}

export interface DashboardData {
  totals: DashboardTotals;
  amount_by_decision_inr: AmountByDecision;
  top_vendors: VendorSpendSummary[];
  reason_breakdown: ReasonBreakdownItem[];
  recent_trend: TrendDayItem[];
}

// ---------------------------------------------------------------------------
// Live Stage Streaming Types
// ---------------------------------------------------------------------------
export interface StreamStage {
  key: string;
  name: string;
  status: 'PENDING' | 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED';
  summary?: string;
  duration_ms?: number;
}

export interface FileProcessingState {
  file: string;
  index: number;
  total: number;
  stages: StreamStage[];
  status: 'PROCESSING' | 'DONE' | 'ERROR';
  run?: InvoiceRunResult;
  error?: string;
}

