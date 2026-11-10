import React, { useState, useEffect } from 'react';
import {
  X,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  ShieldCheck,
  Check,
  ArrowRight,
  Sparkles,
  Building2,
  Calendar,
  CreditCard,
  Hash,
  Eye
} from 'lucide-react';
import {
  InvoiceRunResult,
  DecisionType
} from '../types';
import {
  formatCurrency,
  formatDate,
  getDecisionBadge,
  translateReasonCode,
  mapStageKeyToFriendlyName
} from '../utils/formatters';

interface InvoiceDetailDrawerProps {
  run: InvoiceRunResult | null;
  onClose: () => void;
  onApprove: (runId: string, action: 'APPROVE' | 'REJECT', comment?: string, preapproveVendor?: boolean) => Promise<void>;
  onDelete?: (runId: string) => Promise<void>;
}

export const InvoiceDetailDrawer: React.FC<InvoiceDetailDrawerProps> = ({
  run,
  onClose,
  onApprove,
  onDelete
}) => {
  const [activeTab, setActiveTab] = useState<'OVERVIEW' | 'COMPARE' | 'DOCUMENT'>('OVERVIEW');
  const [expandedCheckIdx, setExpandedCheckIdx] = useState<number | null>(null);
  const [comment, setComment] = useState('');
  const [showCommentBox, setShowCommentBox] = useState(false);
  const [isProcessOpen, setIsProcessOpen] = useState(false);
  const [isActing, setIsActing] = useState(false);
  const [imageError, setImageError] = useState(false);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Reset tab & state when run changes
  useEffect(() => {
    setActiveTab('OVERVIEW');
    setComment('');
    setShowCommentBox(false);
    setImageError(false);
    setIsProcessOpen(false);
  }, [run?.run_id]);

  if (!run) return null;

  const decisionBadge = getDecisionBadge(run.decision);
  const inv = run.standard_invoice;
  const vendorName = run.matched_vendor_name || inv?.vendor_name?.value || 'Unknown Vendor';
  const invoiceNumber = inv?.invoice_number?.value || run.run_id;
  const currency = run.invoice_currency || inv?.currency?.value || 'INR';
  const totalAmount = run.invoice_total ?? inv?.total?.value ?? 0;
  const filename = inv?.source_info?.filename;

  // Build the 7 plain-business verification checks
  const checksList = [
    {
      id: 'vendor',
      label: 'Vendor verified',
      ok: run.vendor_identity ? run.vendor_identity.same_entity : Boolean(run.matched_vendor_id && !run.reason_codes.includes('UNKNOWN_VENDOR') && !run.reason_codes.includes('TAX_ID_MISMATCH')),
      isWarning: Boolean(run.vendor_identity && run.vendor_identity.same_entity && run.vendor_identity.name_on_invoice !== run.vendor_identity.name_on_record),
      note: run.vendor_identity?.reason ||
        (run.reason_codes.includes('TAX_ID_MISMATCH')
          ? 'Tax ID does not match vendor records.'
          : run.matched_vendor_name
          ? `Verified against master record (${run.matched_vendor_name}).`
          : 'Vendor verified.')
    },
    {
      id: 'bank',
      label: 'Bank details',
      ok: !run.reason_codes.includes('BANK_MISMATCH'),
      isWarning: false,
      note: run.reason_codes.includes('BANK_MISMATCH')
        ? 'Bank account differs from master vendor payee details.'
        : inv?.vendor_bank_account?.value
        ? `Account ${inv.vendor_bank_account.value} matches vendor record.`
        : 'Bank information verified.'
    },
    {
      id: 'po',
      label: 'Purchase order match',
      ok: Boolean(run.matched_po_number || inv?.po_reference?.value || run.policy_applied?.trust === 'PREAPPROVED' || run.reason_codes.includes('PREAPPROVED_NO_PO')),
      isWarning: !run.matched_po_number && !inv?.po_reference?.value && run.policy_applied?.trust !== 'PREAPPROVED',
      note: run.matched_po_number
        ? `Matched to purchase order ${run.matched_po_number}.`
        : run.reason_codes.includes('PREAPPROVED_NO_PO') || run.policy_applied?.trust === 'PREAPPROVED'
        ? 'Pre-approved recurring vendor. No purchase order required.'
        : 'No purchase order reference matched.'
    },
    {
      id: 'tolerance',
      label: 'Amount within tolerance',
      ok: !run.reason_codes.includes('PRICE_VARIANCE_EXCEEDED') && !run.reason_codes.includes('TOTAL_VARIANCE_EXCEEDED') && !run.reason_codes.includes('OVER_VENDOR_LIMIT'),
      isWarning: false,
      note: run.reason_codes.includes('OVER_VENDOR_LIMIT')
        ? 'Invoice total exceeds the pre-approved vendor spending limit.'
        : run.reason_codes.includes('TOTAL_VARIANCE_EXCEEDED')
        ? 'Total amount exceeds purchase order tolerance.'
        : run.reason_codes.includes('PRICE_VARIANCE_EXCEEDED')
        ? 'Line item unit price variance exceeds allowable threshold.'
        : 'Pricing and totals are within approved corporate tolerance.'
    },
    {
      id: 'duplicate',
      label: 'Duplicate check',
      ok: !run.reason_codes.includes('DUPLICATE_INVOICE') && !run.reason_codes.includes('DUPLICATE_SUSPECTED'),
      isWarning: run.reason_codes.includes('DUPLICATE_SUSPECTED'),
      note: run.reason_codes.includes('DUPLICATE_INVOICE')
        ? 'Duplicate invoice detected in AP history.'
        : 'No prior identical invoice found in historical records.'
    },
    {
      id: 'math',
      label: 'Math & fields',
      ok: !run.reason_codes.includes('ARITHMETIC_ERROR') && !run.reason_codes.includes('DUE_BEFORE_INVOICE') && !run.reason_codes.includes('FUTURE_DATE'),
      isWarning: run.reason_codes.includes('STALE_INVOICE'),
      note: run.reason_codes.includes('ARITHMETIC_ERROR')
        ? 'Subtotal and tax do not calculate correctly to gross total.'
        : run.reason_codes.includes('DUE_BEFORE_INVOICE')
        ? 'Due date precedes the invoice issue date.'
        : 'Subtotal, tax, and itemized arithmetic verified successfully.'
    },
    {
      id: 'policy',
      label: 'Policy',
      ok: run.policy_applied ? run.policy_applied.trust !== 'BLOCKED' : !run.reason_codes.includes('BLOCKED_VENDOR'),
      isWarning: run.policy_applied?.trust === 'WATCHLIST' || run.reason_codes.includes('WATCHLIST_VENDOR'),
      note: run.policy_applied?.notes && run.policy_applied.notes.length > 0
        ? run.policy_applied.notes.join('; ')
        : run.policy_applied?.trust
        ? `Evaluated under ${run.policy_applied.trust} vendor policy.`
        : 'Checked against vendor trust policies and limits.'
    }
  ];

  // AI Review reasoning & concerns
  const reasoning = run.ai_review?.summary || run.decision_summary || run.ai_summary || 'Verification completed based on 2-way checks and vendor policy.';
  const rawConcerns = run.ai_review?.concerns || run.ai_flaws || [];
  const concerns = rawConcerns.length > 0
    ? rawConcerns
    : run.reason_codes.filter((c) => c !== 'AUTO_APPROVE' && c !== 'PREAPPROVED_NO_PO').map(translateReasonCode);

  const isConfirmed = Boolean(run.human_approval_details || run.human_override);
  const confirmedBy = run.human_approval_details?.reviewer || run.human_override?.overridden_by || run.human_override?.reviewer || 'AP Lead';
  const confirmedAt = run.human_approval_details?.timestamp || run.human_override?.overridden_at || run.human_override?.timestamp;

  const handleAction = async (action: 'APPROVE' | 'REJECT', preapprove: boolean = false) => {
    setIsActing(true);
    try {
      await onApprove(run.run_id, action, comment.trim() || undefined, preapprove);
      setShowCommentBox(false);
      setComment('');
    } finally {
      setIsActing(false);
    }
  };

  const poConsumption = run.comparison?.po_consumption;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity animate-in fade-in duration-200"
        onClick={onClose}
      />

      {/* Drawer Container */}
      <div className="fixed inset-y-0 right-0 max-w-4xl w-full flex pl-6 sm:pl-10">
        <div className="w-full bg-white shadow-2xl flex flex-col border-l border-neutral-200 animate-in slide-in-from-right duration-200">
          {/* Drawer Top Header */}
          <div className="px-6 py-5 border-b border-neutral-200/80 flex items-start justify-between gap-4 bg-neutral-50/50">
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2.5 flex-wrap">
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${decisionBadge.className}`}>
                  <span className={`h-1.5 w-1.5 rounded-full ${decisionBadge.dotClass}`} />
                  {decisionBadge.label}
                </span>

                {run.read_method && (
                  <span className="text-[11px] font-mono text-neutral-400 bg-white px-2 py-0.5 rounded border border-neutral-200 uppercase">
                    {run.read_method}
                  </span>
                )}
              </div>

              <h2 className="text-xl font-semibold text-neutral-900 tracking-tight truncate">
                {vendorName}
              </h2>

              <div className="flex items-center gap-3 text-xs text-neutral-500 font-mono">
                <span>Inv #{invoiceNumber}</span>
                <span>•</span>
                <span>{formatDate(inv?.invoice_date?.value)}</span>
                {inv?.vendor_tax_id?.value && (
                  <>
                    <span>•</span>
                    <span>Tax ID: {inv.vendor_tax_id.value}</span>
                  </>
                )}
              </div>
            </div>

            <div className="flex items-center gap-4 shrink-0">
              <div className="text-right">
                <div className="text-xl font-semibold text-neutral-900 font-mono tracking-tight">
                  {formatCurrency(totalAmount, currency)}
                </div>
                <div className="text-[11px] font-mono text-neutral-400">
                  Total Payable
                </div>
              </div>

              <button
                onClick={onClose}
                className="p-2 text-neutral-400 hover:text-neutral-900 rounded-xl hover:bg-neutral-100 transition-colors cursor-pointer"
                aria-label="Close panel"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="px-6 border-b border-neutral-200 bg-white flex items-center gap-6 text-sm">
            {(['OVERVIEW', 'COMPARE', 'DOCUMENT'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`py-3 font-medium transition-all cursor-pointer relative ${
                  activeTab === tab
                    ? 'text-neutral-900'
                    : 'text-neutral-500 hover:text-neutral-900'
                }`}
              >
                {tab.charAt(0) + tab.slice(1).toLowerCase()}
                {activeTab === tab && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-neutral-900 rounded-full" />
                )}
              </button>
            ))}
          </div>

          {/* Drawer Body Content */}
          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            {/* TAB 1: OVERVIEW */}
            {activeTab === 'OVERVIEW' && (
              <div className="space-y-6">
                {/* Decision Card */}
                <div className="rounded-2xl border border-neutral-200/90 bg-neutral-50/40 p-5 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-neutral-700 shrink-0" />
                        <h3 className="text-sm font-semibold text-neutral-900">
                          AP Decision Review
                        </h3>
                      </div>
                      <p className="text-xs text-neutral-600 leading-relaxed font-sans">
                        {reasoning}
                      </p>
                    </div>

                    {isConfirmed && (
                      <span className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-[11px] font-medium font-mono">
                        <Check className="h-3 w-3" />
                        Authorized by {confirmedBy}
                      </span>
                    )}
                  </div>

                  {/* Concerns / Flags */}
                  {concerns.length > 0 && (
                    <div className="pt-2 border-t border-neutral-200/60 space-y-1.5">
                      <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-500 font-mono">
                        Noted Observations
                      </div>
                      <ul className="space-y-1">
                        {concerns.map((concern, idx) => (
                          <li key={idx} className="flex items-start gap-2 text-xs text-neutral-700">
                            <span className="h-1.5 w-1.5 rounded-full bg-neutral-400 mt-1.5 shrink-0" />
                            <span>{concern}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Human Override / Confirmation notice */}
                  {isConfirmed && confirmedAt && (
                    <div className="text-[11px] text-neutral-500 font-mono pt-2 border-t border-neutral-200/60">
                      Sign-off recorded: {formatDate(confirmedAt)} by {confirmedBy}
                    </div>
                  )}

                  {/* Actions Bar */}
                  <div className="pt-3 border-t border-neutral-200/60 flex flex-wrap items-center gap-2.5">
                    <button
                      onClick={() => handleAction('APPROVE')}
                      disabled={isActing}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium shadow-xs transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      <span>Approve</span>
                    </button>

                    <button
                      onClick={() => handleAction('REJECT')}
                      disabled={isActing}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium shadow-xs transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <XCircle className="h-4 w-4" />
                      <span>Reject</span>
                    </button>

                    {run.decision === 'NEEDS_REVIEW' && (
                      <button
                        onClick={() => handleAction('APPROVE', true)}
                        disabled={isActing}
                        className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-neutral-300 hover:border-neutral-900 text-neutral-800 text-xs font-medium bg-white hover:bg-neutral-50 shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
                        title="Approve this invoice and set vendor trust to Pre-approved for automatic processing within limit"
                      >
                        <ShieldCheck className="h-4 w-4 text-emerald-600" />
                        <span>Approve & pre-approve vendor</span>
                      </button>
                    )}

                    <button
                      onClick={() => setShowCommentBox(!showCommentBox)}
                      className="inline-flex items-center gap-1 px-3 py-2 rounded-xl text-neutral-600 hover:text-neutral-900 text-xs font-medium hover:bg-neutral-100 transition-colors ml-auto cursor-pointer"
                    >
                      <MessageSquare className="h-3.5 w-3.5 text-neutral-400" />
                      <span>{showCommentBox ? 'Hide note' : 'Add note'}</span>
                    </button>
                  </div>

                  {/* Popover / Collapsible Comment Box */}
                  {showCommentBox && (
                    <div className="pt-3 border-t border-neutral-200/60 animate-in fade-in duration-150 space-y-2">
                      <label className="block text-[11px] font-mono uppercase tracking-wider text-neutral-500">
                        Reviewer Sign-off Note
                      </label>
                      <textarea
                        value={comment}
                        onChange={(e) => setComment(e.target.value)}
                        placeholder="Add an internal controller justification or reference..."
                        rows={2}
                        className="w-full text-xs rounded-xl border border-neutral-200 p-2.5 bg-white text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
                      />
                    </div>
                  )}
                </div>

                {/* Process Pipeline Timeline (Collapsed by default) */}
                {run.stages && run.stages.length > 0 && (
                  <div className="rounded-2xl border border-neutral-200/90 bg-white overflow-hidden shadow-2xs">
                    <button
                      type="button"
                      onClick={() => setIsProcessOpen(!isProcessOpen)}
                      className="w-full px-4 py-3 flex items-center justify-between text-left hover:bg-neutral-50/70 transition-colors cursor-pointer"
                    >
                      <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-neutral-700" />
                        <span className="text-xs font-semibold text-neutral-900">
                          Process Timeline ({run.stages.length} stages)
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] font-mono text-neutral-400">
                          {isProcessOpen ? 'Collapse' : 'Expand'}
                        </span>
                        {isProcessOpen ? (
                          <ChevronUp className="h-3.5 w-3.5 text-neutral-400" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-neutral-400" />
                        )}
                      </div>
                    </button>

                    {isProcessOpen && (
                      <div className="px-4 pb-4 pt-1 divide-y divide-neutral-100 border-t border-neutral-100 animate-in fade-in duration-150">
                        {run.stages.map((st, idx) => {
                          const friendlyName = mapStageKeyToFriendlyName(st.key, st.name);
                          const isPass = st.status === 'PASS';
                          const isWarn = st.status === 'WARN';
                          const isFail = st.status === 'FAIL';

                          return (
                            <div key={idx} className="py-2.5 flex items-start gap-2.5 first:pt-2">
                              <div className="mt-0.5 shrink-0">
                                {isPass ? (
                                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                                ) : isWarn ? (
                                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                                ) : isFail ? (
                                  <XCircle className="h-3.5 w-3.5 text-rose-500" />
                                ) : (
                                  <div className="h-3.5 w-3.5 rounded-full border border-neutral-300" />
                                )}
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center justify-between text-xs">
                                  <span className="font-medium text-neutral-800">{friendlyName}</span>
                                  <span className="text-[10px] font-mono text-neutral-400">
                                    {st.duration_ms}ms
                                  </span>
                                </div>
                                {st.summary && (
                                  <p className="text-[11px] text-neutral-500 mt-0.5 leading-relaxed">
                                    {st.summary}
                                  </p>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* Checks Checklist */}
                <div className="space-y-3">
                  <h3 className="text-xs font-medium font-mono uppercase tracking-wider text-neutral-500">
                    Verification Checklist ({checksList.filter((c) => c.ok).length}/{checksList.length} Passed)
                  </h3>

                  <div className="rounded-2xl border border-neutral-200/90 divide-y divide-neutral-100 bg-white overflow-hidden shadow-2xs">
                    {checksList.map((check, idx) => {
                      const isExpanded = expandedCheckIdx === idx;
                      return (
                        <div key={check.id} className="transition-colors hover:bg-neutral-50/50">
                          <button
                            onClick={() => setExpandedCheckIdx(isExpanded ? null : idx)}
                            className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left cursor-pointer"
                          >
                            <div className="flex items-center gap-3">
                              {check.ok ? (
                                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                              ) : check.isWarning ? (
                                <AlertTriangle className="h-4 w-4 text-amber-500 shrink-0" />
                              ) : (
                                <XCircle className="h-4 w-4 text-rose-500 shrink-0" />
                              )}
                              <span className="text-xs font-medium text-neutral-900">
                                {check.label}
                              </span>
                            </div>

                            <div className="flex items-center gap-2">
                              <span className="text-[11px] text-neutral-500 truncate max-w-xs hidden sm:inline">
                                {check.note}
                              </span>
                              {isExpanded ? (
                                <ChevronUp className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
                              ) : (
                                <ChevronDown className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
                              )}
                            </div>
                          </button>

                          {isExpanded && (
                            <div className="px-10 pb-3 pt-0 text-xs text-neutral-600 leading-relaxed font-sans animate-in fade-in duration-100">
                              {check.note}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: COMPARE */}
            {activeTab === 'COMPARE' && (
              <div className="space-y-6">
                {/* PO Usage Progress Bar */}
                {poConsumption ? (
                  <div className="rounded-2xl border border-neutral-200/90 bg-neutral-50/40 p-5 space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-xs font-semibold text-neutral-900">
                          Purchase Order Balance ({poConsumption.po_number})
                        </div>
                        <div className="text-[11px] text-neutral-500 font-mono">
                          Total Budget: {formatCurrency(poConsumption.po_total, poConsumption.currency)}
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="text-xs font-semibold font-mono text-neutral-900">
                          {poConsumption.utilization_pct.toFixed(1)}% Billed
                        </div>
                        <div className="text-[11px] text-neutral-500 font-mono">
                          Remaining: {formatCurrency(poConsumption.remaining_after, poConsumption.currency)}
                        </div>
                      </div>
                    </div>

                    {/* Progress Track */}
                    <div className="h-3 rounded-full bg-neutral-200 overflow-hidden flex">
                      <div
                        style={{ width: `${Math.min(100, (poConsumption.prior_invoiced / (poConsumption.po_total || 1)) * 100)}%` }}
                        className="bg-neutral-400 h-full transition-all"
                        title={`Prior invoiced: ${formatCurrency(poConsumption.prior_invoiced, poConsumption.currency)}`}
                      />
                      <div
                        style={{ width: `${Math.min(100, (poConsumption.this_invoice / (poConsumption.po_total || 1)) * 100)}%` }}
                        className="bg-emerald-500 h-full transition-all"
                        title={`This invoice: ${formatCurrency(poConsumption.this_invoice, poConsumption.currency)}`}
                      />
                    </div>

                    <div className="flex items-center gap-4 text-[11px] font-mono text-neutral-500 pt-1">
                      <div className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-neutral-400" />
                        <span>Prior: {formatCurrency(poConsumption.prior_invoiced, poConsumption.currency)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-emerald-500" />
                        <span>This invoice: {formatCurrency(poConsumption.this_invoice, poConsumption.currency)}</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="h-2 w-2 rounded-full bg-neutral-200" />
                        <span>Remaining: {formatCurrency(poConsumption.remaining_after, poConsumption.currency)}</span>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="p-4 rounded-xl border border-neutral-200 bg-neutral-50 text-xs text-neutral-600 font-sans">
                    No purchase order balance tracking for this invoice.
                  </div>
                )}

                {/* Header Diff Table */}
                {run.comparison?.header_diffs && run.comparison.header_diffs.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-mono uppercase tracking-wider text-neutral-500 font-medium">
                      Header Field Comparisons
                    </h4>
                    <div className="rounded-xl border border-neutral-200 overflow-hidden">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-neutral-100 text-neutral-600 border-b border-neutral-200">
                          <tr>
                            <th className="px-4 py-2.5 font-medium">Field</th>
                            <th className="px-4 py-2.5 font-medium">Invoice Value</th>
                            <th className="px-4 py-2.5 font-medium">Purchase Order Value</th>
                            <th className="px-4 py-2.5 font-medium text-right">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-neutral-100 bg-white">
                          {run.comparison.header_diffs.map((diff, idx) => (
                            <tr key={idx} className="hover:bg-neutral-50/50">
                              <td className="px-4 py-2.5 font-sans font-medium text-neutral-800">
                                {diff.label}
                              </td>
                              <td className="px-4 py-2.5 text-neutral-700">
                                {diff.invoice_value || '—'}
                              </td>
                              <td className="px-4 py-2.5 text-neutral-500">
                                {diff.reference_value || '—'}
                              </td>
                              <td className="px-4 py-2.5 text-right font-sans">
                                {diff.status === 'MATCH' ? (
                                  <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 font-medium">
                                    <Check className="h-3 w-3" /> Match
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 font-medium">
                                    <AlertTriangle className="h-3 w-3" /> Variance
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Line Items Variance Table */}
                {run.comparison?.line_diffs && run.comparison.line_diffs.length > 0 && (
                  <div className="space-y-2">
                    <h4 className="text-xs font-mono uppercase tracking-wider text-neutral-500 font-medium">
                      Line Item Pricing & Quantity Comparison
                    </h4>
                    <div className="rounded-xl border border-neutral-200 overflow-hidden">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-neutral-100 text-neutral-600 border-b border-neutral-200">
                          <tr>
                            <th className="px-3 py-2.5 font-medium">#</th>
                            <th className="px-3 py-2.5 font-medium font-sans">Description</th>
                            <th className="px-3 py-2.5 font-medium text-right">Inv Qty</th>
                            <th className="px-3 py-2.5 font-medium text-right">PO Qty</th>
                            <th className="px-3 py-2.5 font-medium text-right">Inv Unit</th>
                            <th className="px-3 py-2.5 font-medium text-right">PO Unit</th>
                            <th className="px-3 py-2.5 font-medium text-right">Variance</th>
                            <th className="px-3 py-2.5 font-medium text-right font-sans">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-neutral-100 bg-white">
                          {run.comparison.line_diffs.map((line, idx) => (
                            <tr key={idx} className="hover:bg-neutral-50/50">
                              <td className="px-3 py-2.5 text-neutral-400">{line.line_no}</td>
                              <td className="px-3 py-2.5 font-sans font-medium text-neutral-800">
                                {line.description}
                              </td>
                              <td className="px-3 py-2.5 text-right text-neutral-700">{line.inv_qty}</td>
                              <td className="px-3 py-2.5 text-right text-neutral-500">{line.po_qty ?? '—'}</td>
                              <td className="px-3 py-2.5 text-right text-neutral-700">
                                {formatCurrency(line.inv_unit_price, currency)}
                              </td>
                              <td className="px-3 py-2.5 text-right text-neutral-500">
                                {line.po_unit_price ? formatCurrency(line.po_unit_price, currency) : '—'}
                              </td>
                              <td className="px-3 py-2.5 text-right">
                                {line.variance_pct !== 0 ? (
                                  <span className={line.variance_pct > 0 ? 'text-rose-600' : 'text-emerald-600'}>
                                    {line.variance_pct > 0 ? '+' : ''}{line.variance_pct.toFixed(1)}%
                                  </span>
                                ) : (
                                  <span className="text-neutral-400">0%</span>
                                )}
                              </td>
                              <td className="px-3 py-2.5 text-right font-sans">
                                {line.status === 'MATCH' ? (
                                  <span className="text-emerald-600 font-medium text-[11px]">Match</span>
                                ) : (
                                  <span className="text-amber-600 font-medium text-[11px]">{line.status.replace(/_/g, ' ')}</span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: DOCUMENT */}
            {activeTab === 'DOCUMENT' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Left: Original Preview Image */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-mono uppercase tracking-wider text-neutral-500 font-medium flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5" />
                      Original Document
                    </h4>

                    {filename && (
                      <a
                        href={`/api/files/${encodeURIComponent(filename)}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-[11px] text-neutral-600 hover:text-neutral-900 font-mono transition-colors"
                      >
                        <span>Open file</span>
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>

                  <div className="rounded-2xl border border-neutral-200 bg-neutral-100 min-h-[460px] flex items-center justify-center overflow-hidden p-2">
                    {filename && !imageError ? (
                      <img
                        src={`/api/files/${encodeURIComponent(filename)}/preview-image`}
                        alt="Invoice Preview"
                        onError={() => setImageError(true)}
                        className="max-h-[560px] w-auto object-contain rounded-lg shadow-xs bg-white"
                      />
                    ) : (
                      <div className="text-center p-8 space-y-3">
                        <FileText className="h-10 w-10 text-neutral-400 mx-auto" />
                        <p className="text-xs text-neutral-500">
                          Preview image unavailable.
                        </p>
                        {filename && (
                          <a
                            href={`/api/files/${encodeURIComponent(filename)}`}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-900 text-white text-xs font-medium"
                          >
                            <span>Download {filename}</span>
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right: Extracted Structured Fields */}
                <div className="space-y-4">
                  <h4 className="text-xs font-mono uppercase tracking-wider text-neutral-500 font-medium">
                    Extracted Document Fields
                  </h4>

                  {/* Vendor & Entity Card */}
                  <div className="p-4 rounded-xl border border-neutral-200 bg-white space-y-3">
                    <div className="text-xs font-semibold text-neutral-900 flex items-center gap-1.5">
                      <Building2 className="h-3.5 w-3.5 text-neutral-500" />
                      Vendor Information
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Vendor Name</div>
                        <div className="text-neutral-800 font-medium truncate font-sans">
                          {inv?.vendor_name?.value || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Tax ID / GSTIN</div>
                        <div className="text-neutral-800 font-medium">
                          {inv?.vendor_tax_id?.value || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Bank Account</div>
                        <div className="text-neutral-800 font-medium">
                          {inv?.vendor_bank_account?.value || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Country / Code</div>
                        <div className="text-neutral-800 font-medium">
                          {inv?.vendor_country?.value || '—'}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Invoice Header Card */}
                  <div className="p-4 rounded-xl border border-neutral-200 bg-white space-y-3">
                    <div className="text-xs font-semibold text-neutral-900 flex items-center gap-1.5">
                      <Hash className="h-3.5 w-3.5 text-neutral-500" />
                      Invoice Reference
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Invoice Number</div>
                        <div className="text-neutral-800 font-medium">
                          {inv?.invoice_number?.value || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">PO Reference</div>
                        <div className="text-neutral-800 font-medium">
                          {inv?.po_reference?.value || run.matched_po_number || '—'}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Invoice Date</div>
                        <div className="text-neutral-800 font-medium">
                          {formatDate(inv?.invoice_date?.value)}
                        </div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Due Date</div>
                        <div className="text-neutral-800 font-medium">
                          {formatDate(inv?.due_date?.value)}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Financial Summary Card */}
                  <div className="p-4 rounded-xl border border-neutral-200 bg-white space-y-3">
                    <div className="text-xs font-semibold text-neutral-900 flex items-center gap-1.5">
                      <CreditCard className="h-3.5 w-3.5 text-neutral-500" />
                      Financial Totals
                    </div>
                    <div className="space-y-2 text-xs font-mono">
                      <div className="flex justify-between text-neutral-600">
                        <span>Subtotal</span>
                        <span>{formatCurrency(inv?.subtotal?.value, currency)}</span>
                      </div>
                      <div className="flex justify-between text-neutral-600">
                        <span>Tax Amount ({inv?.tax_label || 'Tax'})</span>
                        <span>{formatCurrency(inv?.tax_amount?.value, currency)}</span>
                      </div>
                      <div className="pt-2 border-t border-neutral-100 flex justify-between font-semibold text-neutral-900 text-sm">
                        <span>Gross Total</span>
                        <span>{formatCurrency(totalAmount, currency)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
