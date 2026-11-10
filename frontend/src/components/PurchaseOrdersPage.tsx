import React, { useState, useMemo } from 'react';
import {
  Search,
  Package,
  ChevronDown,
  ChevronUp,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  ArrowRight
} from 'lucide-react';
import { PurchaseOrder, InvoiceRunResult } from '../types';
import { formatCurrency, formatDate, getDecisionBadge } from '../utils/formatters';
import { TableSkeleton } from './Skeletons';

interface PurchaseOrdersPageProps {
  pos: PurchaseOrder[];
  runs: InvoiceRunResult[];
  isLoading: boolean;
  onSelectRun?: (run: InvoiceRunResult) => void;
}

export const PurchaseOrdersPage: React.FC<PurchaseOrdersPageProps> = ({
  pos,
  runs,
  isLoading,
  onSelectRun
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedPo, setExpandedPo] = useState<string | null>(null);

  // Filtered POs
  const filteredPos = useMemo(() => {
    if (!searchQuery.trim()) return pos;
    const q = searchQuery.toLowerCase();
    return pos.filter((p) =>
      p.po_number.toLowerCase().includes(q) ||
      (p.vendor_name && p.vendor_name.toLowerCase().includes(q)) ||
      p.vendor_id.toLowerCase().includes(q)
    );
  }, [pos, searchQuery]);

  // Find linked invoices for a given PO
  const getLinkedRuns = (poNumber: string) => {
    return runs.filter(
      (r) =>
        r.matched_po_number === poNumber ||
        r.standard_invoice?.po_reference?.value === poNumber
    );
  };

  const getPoStatusBadge = (po: PurchaseOrder) => {
    const isOverbilled = po.remaining_amount < 0 || po.status === 'OVERBILLED';
    const isClosed = po.status === 'PO_CLOSED' || po.status === 'CLOSED';
    const isConsumed = po.remaining_amount === 0 || po.status === 'EXACTLY_CONSUMED';

    if (isOverbilled) {
      return {
        label: 'Overbilled',
        className: 'bg-rose-50 text-rose-700 border-rose-200'
      };
    }
    if (isClosed || isConsumed) {
      return {
        label: 'Closed',
        className: 'bg-slate-100 text-slate-700 border-slate-200'
      };
    }
    return {
      label: 'Open',
      className: 'bg-emerald-50 text-emerald-700 border-emerald-200'
    };
  };

  return (
    <div className="space-y-6">
      {/* Search Input */}
      <div className="flex items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search purchase orders by PO #, vendor..."
            className="w-full text-xs rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
          />
        </div>
      </div>

      {/* PO Table */}
      <div className="rounded-2xl border border-neutral-200/90 bg-white overflow-hidden shadow-2xs">
        {isLoading ? (
          <TableSkeleton rows={5} />
        ) : filteredPos.length === 0 ? (
          <div className="py-20 text-center space-y-3 px-4">
            <Package className="h-9 w-9 text-neutral-300 mx-auto" />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-neutral-800">
                {pos.length === 0 ? 'No purchase orders recorded' : 'No matching purchase orders'}
              </h3>
              <p className="text-xs text-neutral-400 max-w-sm mx-auto">
                {pos.length === 0
                  ? 'Purchase orders entered in your ERP or PO repository will appear here for 2-way invoice reconciliation.'
                  : 'Try searching with a different purchase order number or vendor name.'}
              </p>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-50/80 text-neutral-500 font-mono uppercase tracking-wider text-[11px] border-b border-neutral-200">
                <tr>
                  <th className="px-5 py-3 font-medium">PO Number</th>
                  <th className="px-4 py-3 font-medium">Vendor</th>
                  <th className="px-4 py-3 font-medium text-right">Total</th>
                  <th className="px-4 py-3 font-medium text-right">Billed</th>
                  <th className="px-5 py-3 font-medium min-w-[200px]">Remaining Balance</th>
                  <th className="px-4 py-3 font-medium text-center">Status</th>
                  <th className="px-3 py-3 w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 font-sans">
                {filteredPos.map((po) => {
                  const isExpanded = expandedPo === po.po_number;
                  const linkedRuns = getLinkedRuns(po.po_number);
                  const statusBadge = getPoStatusBadge(po);
                  const currency = po.currency || 'INR';
                  const total = po.total_amount || (po.subtotal + (po.tax_amount || 0));
                  const billed = po.invoiced_amount ?? 0;
                  const remaining = po.remaining_amount ?? (total - billed);
                  const percentBilled = total > 0 ? Math.min(100, Math.max(0, (billed / total) * 100)) : 0;
                  const isOverbilled = remaining < 0;

                  return (
                    <React.Fragment key={po.po_number}>
                      <tr
                        onClick={() => setExpandedPo(isExpanded ? null : po.po_number)}
                        className={`hover:bg-neutral-50/80 transition-colors cursor-pointer group ${
                          isExpanded ? 'bg-neutral-50/60' : ''
                        }`}
                      >
                        {/* PO Number */}
                        <td className="px-5 py-3.5 font-mono font-medium text-neutral-900">
                          {po.po_number}
                        </td>

                        {/* Vendor */}
                        <td className="px-4 py-3.5 font-medium text-neutral-800 truncate max-w-[200px]">
                          {po.vendor_name || po.vendor_id}
                        </td>

                        {/* Total */}
                        <td className="px-4 py-3.5 text-right font-mono text-neutral-900 font-medium">
                          {formatCurrency(total, currency)}
                        </td>

                        {/* Billed */}
                        <td className="px-4 py-3.5 text-right font-mono text-neutral-600">
                          {formatCurrency(billed, currency)}
                        </td>

                        {/* Remaining with Progress Bar */}
                        <td className="px-5 py-3.5">
                          <div className="space-y-1.5">
                            <div className="flex justify-between items-center text-[11px] font-mono">
                              <span className={isOverbilled ? 'text-rose-600 font-bold' : 'text-neutral-700'}>
                                {formatCurrency(remaining, currency)}
                              </span>
                              <span className="text-neutral-400">
                                {percentBilled.toFixed(0)}%
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-neutral-100 rounded-full overflow-hidden">
                              <div
                                style={{ width: `${percentBilled}%` }}
                                className={`h-full rounded-full transition-all ${
                                  isOverbilled ? 'bg-rose-500' : 'bg-emerald-500'
                                }`}
                              />
                            </div>
                          </div>
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3.5 text-center">
                          <span
                            className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium border ${statusBadge.className}`}
                          >
                            {statusBadge.label}
                          </span>
                        </td>

                        {/* Expand Chevron */}
                        <td className="px-3 py-3.5 text-center text-neutral-400 group-hover:text-neutral-900">
                          {isExpanded ? (
                            <ChevronUp className="h-4 w-4 mx-auto" />
                          ) : (
                            <ChevronDown className="h-4 w-4 mx-auto" />
                          )}
                        </td>
                      </tr>

                      {/* Expanded Accordion: Line Items + Linked Invoices */}
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} className="px-6 py-5 bg-neutral-50/70 border-b border-neutral-200">
                            <div className="space-y-5 animate-in fade-in duration-150">
                              {/* PO Line Items Table */}
                              <div className="space-y-2">
                                <div className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 font-semibold">
                                  Ordered Line Items ({po.lines?.length || 0})
                                </div>

                                {po.lines && po.lines.length > 0 ? (
                                  <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden shadow-2xs">
                                    <table className="w-full text-left text-xs font-mono">
                                      <thead className="bg-neutral-100/70 text-neutral-500 border-b border-neutral-200 text-[11px]">
                                        <tr>
                                          <th className="px-3 py-2">#</th>
                                          <th className="px-3 py-2 font-sans">Description</th>
                                          <th className="px-3 py-2 text-right">Qty</th>
                                          <th className="px-3 py-2 text-right">Unit Price</th>
                                          <th className="px-3 py-2 text-right">Tax Rate</th>
                                          <th className="px-3 py-2 text-right">Amount</th>
                                        </tr>
                                      </thead>
                                      <tbody className="divide-y divide-neutral-100">
                                        {po.lines.map((line) => (
                                          <tr key={line.line_no} className="hover:bg-neutral-50/50">
                                            <td className="px-3 py-2 text-neutral-400">{line.line_no}</td>
                                            <td className="px-3 py-2 font-sans font-medium text-neutral-800">
                                              {line.description}
                                            </td>
                                            <td className="px-3 py-2 text-right text-neutral-600">{line.qty}</td>
                                            <td className="px-3 py-2 text-right text-neutral-600">
                                              {formatCurrency(line.unit_price, currency)}
                                            </td>
                                            <td className="px-3 py-2 text-right text-neutral-500">
                                              {line.tax_rate ? `${(line.tax_rate * 100).toFixed(0)}%` : '—'}
                                            </td>
                                            <td className="px-3 py-2 text-right font-medium text-neutral-900">
                                              {formatCurrency(line.amount, currency)}
                                            </td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                ) : (
                                  <div className="p-3 text-xs text-neutral-400 rounded-xl bg-white border border-neutral-200">
                                    No itemized line items entered for this purchase order.
                                  </div>
                                )}
                              </div>

                              {/* Linked Invoices Section */}
                              <div className="space-y-2">
                                <div className="text-[11px] font-mono uppercase tracking-wider text-neutral-500 font-semibold">
                                  Billed Invoices Linked to PO ({linkedRuns.length})
                                </div>

                                {linkedRuns.length > 0 ? (
                                  <div className="rounded-xl border border-neutral-200 bg-white overflow-hidden shadow-2xs divide-y divide-neutral-100">
                                    {linkedRuns.map((r) => {
                                      const rBadge = getDecisionBadge(r.decision);
                                      const inv = r.standard_invoice;
                                      return (
                                        <div
                                          key={r.run_id}
                                          onClick={() => onSelectRun && onSelectRun(r)}
                                          className="p-3 flex items-center justify-between text-xs hover:bg-neutral-50/80 transition-colors cursor-pointer group"
                                        >
                                          <div className="flex items-center gap-3">
                                            <FileText className="h-4 w-4 text-neutral-400 group-hover:text-neutral-900" />
                                            <div>
                                              <span className="font-mono font-medium text-neutral-900">
                                                {inv?.invoice_number?.value || r.run_id}
                                              </span>
                                              <span className="text-neutral-400 mx-2">•</span>
                                              <span className="text-neutral-500 font-mono">
                                                {formatDate(inv?.invoice_date?.value || r.created_at)}
                                              </span>
                                            </div>
                                          </div>

                                          <div className="flex items-center gap-4">
                                            <span className="font-mono font-medium text-neutral-900">
                                              {formatCurrency(r.invoice_total, r.invoice_currency)}
                                            </span>

                                            <span
                                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium border ${rBadge.className}`}
                                            >
                                              {rBadge.label}
                                            </span>

                                            <ArrowRight className="h-3.5 w-3.5 text-neutral-400 group-hover:text-neutral-900 group-hover:translate-x-0.5 transition-all" />
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <div className="p-3 text-xs text-neutral-400 rounded-xl bg-white border border-neutral-200">
                                    No incoming invoices have been billed against this purchase order yet.
                                  </div>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
