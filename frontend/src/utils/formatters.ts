import { DecisionType, VendorTrustLevel } from '../types';

/**
 * Format currency amounts nicely with appropriate symbols and decimal places.
 */
export function formatCurrency(amount: number | null | undefined, currency: string = 'INR'): string {
  if (amount === null || amount === undefined || isNaN(amount)) {
    return '—';
  }

  const curr = (currency || 'INR').toUpperCase();
  const symbolMap: Record<string, string> = {
    INR: '₹',
    USD: '$',
    EUR: '€',
    GBP: '£',
    SGD: 'S$',
    AED: 'AED ',
    JPY: '¥',
    AUD: 'A$',
    CAD: 'C$'
  };

  const symbol = symbolMap[curr] || `${curr} `;

  // Use Indian number formatting for INR, otherwise standard decimal formatting
  try {
    const formattedNum = curr === 'INR'
      ? amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return `${symbol}${formattedNum}`;
  } catch {
    return `${symbol}${amount.toFixed(2)}`;
  }
}

/**
 * Format date string into readable English (e.g. "Nov 10, 2026").
 */
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  } catch {
    return dateStr;
  }
}

/**
 * Map decision enum to clean human-readable UI label.
 * Spec: Approved = emerald, Needs review = amber, On hold = slate/blue, Rejected = rose.
 */
export function getDecisionBadge(decision: DecisionType | string) {
  switch (decision) {
    case 'AUTO_APPROVE':
      return {
        label: 'Approved',
        className: 'bg-emerald-50 text-emerald-700 border-emerald-200 ring-emerald-500/10',
        dotClass: 'bg-emerald-500',
        bgSubtle: 'bg-emerald-50/50'
      };
    case 'NEEDS_REVIEW':
      return {
        label: 'Needs review',
        className: 'bg-amber-50 text-amber-700 border-amber-200 ring-amber-500/10',
        dotClass: 'bg-amber-500',
        bgSubtle: 'bg-amber-50/50'
      };
    case 'ON_HOLD':
      return {
        label: 'On hold',
        className: 'bg-slate-100 text-slate-700 border-slate-200 ring-slate-500/10',
        dotClass: 'bg-slate-400',
        bgSubtle: 'bg-slate-50/50'
      };
    case 'REJECT':
      return {
        label: 'Rejected',
        className: 'bg-rose-50 text-rose-700 border-rose-200 ring-rose-500/10',
        dotClass: 'bg-rose-500',
        bgSubtle: 'bg-rose-50/50'
      };
    default:
      return {
        label: decision || 'Unknown',
        className: 'bg-gray-100 text-gray-700 border-gray-200',
        dotClass: 'bg-gray-400',
        bgSubtle: 'bg-gray-50'
      };
  }
}

/**
 * Map vendor trust level to clean badge.
 */
export function getTrustBadge(trust: VendorTrustLevel | string = 'STANDARD') {
  switch (trust) {
    case 'PREAPPROVED':
      return {
        label: 'Pre-approved',
        className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
        dotClass: 'bg-emerald-500',
        description: 'Approved automatically within limit'
      };
    case 'WATCHLIST':
      return {
        label: 'Watchlist',
        className: 'bg-amber-50 text-amber-700 border-amber-200',
        dotClass: 'bg-amber-500',
        description: 'Always held for manual review'
      };
    case 'BLOCKED':
      return {
        label: 'Blocked',
        className: 'bg-rose-50 text-rose-700 border-rose-200',
        dotClass: 'bg-rose-500',
        description: 'Invoices immediately rejected'
      };
    case 'STANDARD':
    default:
      return {
        label: 'Standard',
        className: 'bg-slate-100 text-slate-700 border-slate-200',
        dotClass: 'bg-slate-400',
        description: 'Standard 2-way verification rules'
      };
  }
}

/**
 * Map internal reason codes to plain English business language.
 * Strictly no code constants, hashes, or technical jargon.
 */
export function translateReasonCode(code: string): string {
  if (!code) return '';

  const clean = code.trim().toUpperCase();

  const codeMap: Record<string, string> = {
    AUTO_APPROVE: 'Approved automatically based on clean verification checks and vendor policy.',
    PREAPPROVED_NO_PO: 'Pre-approved recurring vendor without purchase order.',
    VENDOR_NAME_VARIATION: 'Vendor legal name verified with minor typographical/suffix variation.',
    OVER_VENDOR_LIMIT: 'Invoice total exceeds the pre-approved vendor spending limit.',
    WATCHLIST_VENDOR: 'Vendor is flagged on the corporate watchlist and requires controller review.',
    BLOCKED_VENDOR: 'Vendor is blocked from payments.',
    TAX_ID_MISMATCH: 'Tax identification number does not match master records.',
    UNKNOWN_VENDOR: 'Vendor was not found in corporate vendor master records.',
    PRICE_VARIANCE_EXCEEDED: 'Line item unit price exceeds allowed tolerance.',
    TOTAL_VARIANCE_EXCEEDED: 'Invoice total exceeds purchase order limit beyond tolerance.',
    PO_OVERBILLED: 'Invoice amount exceeds remaining purchase order balance.',
    PO_NOT_FOUND: 'Purchase order reference was not found in procurement records.',
    PO_CLOSED: 'Purchase order is already closed or fully consumed.',
    DUPLICATE_INVOICE: 'Duplicate invoice detected with identical details.',
    DUPLICATE_SUSPECTED: 'Potential duplicate invoice detected with similar details.',
    CURRENCY_MISMATCH: 'Invoice currency does not match purchase order currency.',
    ARITHMETIC_ERROR: 'Subtotal, tax, and total arithmetic do not add up.',
    BANK_MISMATCH: 'Bank account number does not match verified vendor record.',
    STALE_INVOICE: 'Invoice date is older than 365 days.',
    FUTURE_DATE: 'Invoice date is dated in the future.',
    DUE_BEFORE_INVOICE: 'Payment due date precedes the invoice issue date.',
    SCANNED_DOCUMENT: 'Scanned document requires visual verification.',
    LOW_CONFIDENCE: 'Certain invoice fields require manual review.',
    CONFIRMED_BY_HUMAN: 'Authorized by AP reviewer.',
    OVERRIDDEN_BY_HUMAN: 'Reviewer decision override recorded.',
    MANUAL_REVIEW_REQUESTED: 'Manual controller review requested.',
    MISSING_LINE_ITEMS: 'Itemized line items could not be parsed from document.'
  };

  if (codeMap[clean]) {
    return codeMap[clean];
  }

  // Gracefully convert SNAKE_CASE_CODE to Clean sentence
  const sentence = clean
    .toLowerCase()
    .split('_')
    .map((word, idx) => (idx === 0 ? word.charAt(0).toUpperCase() + word.slice(1) : word))
    .join(' ');

  return sentence.length > 2 ? sentence : code;
}

/**
 * Standard live pipeline stages in clean business language.
 */
export const STANDARD_STAGES = [
  { key: 'ingest', name: 'Reading document' },
  { key: 'extract', name: 'Checking fields' },
  { key: 'vendor', name: 'Verifying vendor' },
  { key: 'po', name: 'Matching purchase order' },
  { key: 'duplicate', name: 'Checking duplicates' },
  { key: 'policy', name: 'Applying vendor policy' },
  { key: 'ai_review', name: 'AI review' },
  { key: 'decision', name: 'Decision' }
];

/**
 * Map backend stage key or name to clean business label.
 */
export function mapStageKeyToFriendlyName(key: string, originalName?: string): string {
  const k = (key || '').toLowerCase();
  const n = (originalName || '').toLowerCase();

  const exact: Record<string, string> = {
    intake: 'Reading document',
    perception: 'Reading document',
    normalization: 'Checking fields',
    validation: 'Checking fields',
    vendor_fraud: 'Verifying vendor',
    vendor_policy: 'Applying vendor policy',
    po_match: 'Matching purchase order',
    duplicate_check: 'Checking duplicates',
    ai_review: 'AI review',
    decision: 'Decision',
  };
  if (exact[k]) return exact[k];

  if (k.includes('ingest') || k.includes('raw') || k.includes('read') || k.includes('ocr') || n.includes('ingest') || n.includes('ocr') || n.includes('document')) {
    return 'Reading document';
  }
  if (k.includes('extract') || k.includes('field') || n.includes('extract') || n.includes('field')) {
    return 'Checking fields';
  }
  if (k.includes('vendor') || k.includes('entity') || n.includes('vendor')) {
    return 'Verifying vendor';
  }
  if (k.includes('po') || k.includes('order') || k.includes('ledger') || n.includes('po') || n.includes('purchase')) {
    return 'Matching purchase order';
  }
  if (k.includes('dup') || n.includes('dup')) {
    return 'Checking duplicates';
  }
  if (k.includes('policy') || n.includes('policy')) {
    return 'Applying vendor policy';
  }
  if (k.includes('ai') || k.includes('llm') || k.includes('safety') || n.includes('ai') || n.includes('llm') || n.includes('review')) {
    return 'AI review';
  }
  if (k.includes('decision') || k.includes('final') || n.includes('decision')) {
    return 'Decision';
  }

  return originalName || key;
}

