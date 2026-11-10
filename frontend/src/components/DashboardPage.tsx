import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  Clock,
  XCircle,
  TrendingUp,
  FileText,
  Building2,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  Loader2,
  UploadCloud
} from 'lucide-react';
import { DashboardData, InvoiceRunResult } from '../types';
import { formatCurrency, formatDate, getDecisionBadge } from '../utils/formatters';
import { StatTileSkeleton, TableSkeleton } from './Skeletons';

interface DashboardPageProps {
  data: DashboardData | null;
  recentRuns: InvoiceRunResult[];
  isLoading: boolean;
  onSelectRun: (run: InvoiceRunResult) => void;
  onNavigateToInvoices: () => void;
  onRunSample: () => Promise<void>;
  isRunningSample: boolean;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  data,
  recentRuns,
  isLoading,
  onSelectRun,
  onNavigateToInvoices,
  onRunSample,
  isRunningSample
}) => {
  const [hoveredTrendIdx, setHoveredTrendIdx] = useState<number | null>(null);

  if (isLoading && !data) {
    return (
      <div className="space-y-6">
        <StatTileSkeleton />
        <TableSkeleton rows={5} />
      </div>
    );
  }

  // Handle empty state
  if (!data || data.totals.runs === 0) {
    return (
      <div className="py-16 px-4 max-w-2xl mx-auto text-center space-y-6">
        <div className="h-16 w-16 rounded-3xl bg-neutral-900 text-white flex items-center justify-center mx-auto shadow-md">
          <Sparkles className="h-8 w-8" />
        </div>

        <div className="space-y-2">
          <h2 className="text-2xl font-bold tracking-tight text-neutral-900">
            Welcome to Autonomous AP
          </h2>
          <p className="text-sm text-neutral-500 max-w-md mx-auto leading-relaxed">
            Verify and reconcile invoices with 2-way PO matching, deterministic fraud guards,
            and safety review.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <button
            onClick={onRunSample}
            disabled={isRunningSample}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-neutral-900 hover:bg-black text-white text-xs font-medium shadow-xs transition-colors cursor-pointer disabled:opacity-50"
          >
            {isRunningSample ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            <span>{isRunningSample ? 'Analyzing sample invoice...' : 'Try a sample invoice'}</span>
          </button>

          <button
            onClick={onNavigateToInvoices}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl border border-neutral-300 hover:border-neutral-900 text-neutral-800 text-xs font-medium bg-white hover:bg-neutral-50 transition-colors cursor-pointer"
          >
            <UploadCloud className="h-4 w-4 text-neutral-500" />
            <span>Upload invoices</span>
          </button>
        </div>
      </div>
    );
  }

  const { totals, amount_by_decision_inr, top_vendors, reason_breakdown, recent_trend } = data;

  // Max value for 14-day trend scaling
  const maxDayCount = Math.max(...recent_trend.map((d) => d.count), 4);
  const maxVendorSpend = Math.max(...top_vendors.map((v) => v.total_inr), 1);

  return (
    <div className="space-y-8 animate-in fade-in duration-200">
      {/* 4 Top KPI Tiles */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Invoices Processed */}
        <div className="p-5 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-xs font-medium text-neutral-500">
            <span>Invoices Processed</span>
            <FileText className="h-4 w-4 text-neutral-400" />
          </div>
          <div className="text-3xl font-bold font-mono tracking-tight text-neutral-900">
            {totals.runs}
          </div>
          <div className="text-[11px] font-mono text-neutral-400">
            Total AP volume
          </div>
        </div>

        {/* KPI 2: Auto-approved % */}
        <div className="p-5 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-xs font-medium text-emerald-700">
            <span>Auto-Approved Rate</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="text-3xl font-bold font-mono tracking-tight text-neutral-900">
            {totals.auto_rate_pct}%
          </div>
          <div className="text-[11px] font-mono text-emerald-600">
            {totals.approved} invoices auto-cleared
          </div>
        </div>

        {/* KPI 3: Needs Attention */}
        <div className="p-5 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-xs font-medium text-amber-700">
            <span>Needs Attention</span>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </div>
          <div className="text-3xl font-bold font-mono tracking-tight text-neutral-900">
            {totals.needs_review}
          </div>
          <div className="text-[11px] font-mono text-amber-600">
            Requires AP review
          </div>
        </div>

        {/* KPI 4: Total Approved Value */}
        <div className="p-5 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-2">
          <div className="flex items-center justify-between text-xs font-medium text-neutral-500">
            <span>Approved Spend</span>
            <ShieldCheck className="h-4 w-4 text-neutral-400" />
          </div>
          <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900 truncate">
            {formatCurrency(amount_by_decision_inr?.AUTO_APPROVE || 0, 'INR')}
          </div>
          <div className="text-[11px] font-mono text-neutral-400">
            Cleared for payment
          </div>
        </div>
      </div>

      {/* 14-Day Trend Chart & Decision Breakdown Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 14-Day Trend Chart (Pure SVG / CSS) */}
        <div className="lg:col-span-2 p-6 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-neutral-900">
                14-Day Processing Trend
              </h3>
              <p className="text-xs text-neutral-400">
                Daily volume of auto-approved vs flagged invoices
              </p>
            </div>

            {/* Chart Legend */}
            <div className="flex items-center gap-3 text-xs font-mono text-neutral-500">
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                <span>Approved</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
                <span>Flagged</span>
              </div>
            </div>
          </div>

          {/* SVG Bar Chart */}
          <div className="relative pt-4">
            <svg
              viewBox="0 0 700 170"
              className="w-full h-44 overflow-visible font-mono"
            >
              {/* Horizontal grid lines */}
              <line x1="0" y1="30" x2="700" y2="30" stroke="#f1f5f9" strokeDasharray="3 3" />
              <line x1="0" y1="75" x2="700" y2="75" stroke="#f1f5f9" strokeDasharray="3 3" />
              <line x1="0" y1="120" x2="700" y2="120" stroke="#f1f5f9" strokeDasharray="3 3" />
              <line x1="0" y1="140" x2="700" y2="140" stroke="#e2e8f0" />

              {/* 14 Daily Stacked Bars */}
              {recent_trend.map((day, idx) => {
                const barWidth = 28;
                const gap = (700 - barWidth * 14) / 13;
                const x = idx * (barWidth + gap);
                const chartHeight = 110;

                const approvedHeight = (day.approved / maxDayCount) * chartHeight;
                const flaggedHeight = (day.flagged / maxDayCount) * chartHeight;

                const approvedY = 140 - approvedHeight;
                const flaggedY = approvedY - flaggedHeight;

                const isHovered = hoveredTrendIdx === idx;

                return (
                  <g
                    key={day.date}
                    onMouseEnter={() => setHoveredTrendIdx(idx)}
                    onMouseLeave={() => setHoveredTrendIdx(null)}
                    className="cursor-pointer"
                  >
                    {/* Background hit area */}
                    <rect
                      x={x - 4}
                      y="10"
                      width={barWidth + 8}
                      height="135"
                      fill={isHovered ? 'rgba(0,0,0,0.03)' : 'transparent'}
                      rx="6"
                    />

                    {/* Flagged Bar (top) */}
                    {day.flagged > 0 && (
                      <rect
                        x={x}
                        y={flaggedY}
                        width={barWidth}
                        height={Math.max(3, flaggedHeight)}
                        fill="#fbbf24"
                        rx={day.approved > 0 ? 0 : 4}
                        className="transition-all"
                      />
                    )}

                    {/* Approved Bar (bottom) */}
                    {day.approved > 0 && (
                      <rect
                        x={x}
                        y={approvedY}
                        width={barWidth}
                        height={Math.max(3, approvedHeight)}
                        fill="#10b981"
                        rx="4"
                        className="transition-all"
                      />
                    )}

                    {/* Empty Day bar placeholder */}
                    {day.count === 0 && (
                      <rect
                        x={x + 10}
                        y="136"
                        width="8"
                        height="4"
                        fill="#e2e8f0"
                        rx="2"
                      />
                    )}

                    {/* X-axis date label */}
                    <text
                      x={x + barWidth / 2}
                      y="158"
                      fontSize="9"
                      fill={isHovered ? '#0f172a' : '#94a3b8'}
                      fontWeight={isHovered ? '600' : '400'}
                      textAnchor="middle"
                    >
                      {day.date.slice(5)}
                    </text>
                  </g>
                );
              })}
            </svg>

            {/* Hover Tooltip Overlay */}
            {hoveredTrendIdx !== null && recent_trend[hoveredTrendIdx] && (
              <div
                className="absolute top-0 right-4 p-2.5 rounded-xl bg-neutral-900 text-white text-[11px] font-mono shadow-xl pointer-events-none space-y-1 animate-in fade-in duration-100"
              >
                <div className="font-semibold text-neutral-200">
                  {recent_trend[hoveredTrendIdx].date}
                </div>
                <div className="text-emerald-400">
                  Approved: {recent_trend[hoveredTrendIdx].approved}
                </div>
                <div className="text-amber-400">
                  Flagged: {recent_trend[hoveredTrendIdx].flagged}
                </div>
                <div className="pt-0.5 border-t border-neutral-700 text-neutral-300">
                  Total: {recent_trend[hoveredTrendIdx].count}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Decision Breakdown & Financial Impact */}
        <div className="p-6 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold text-neutral-900">
              Decision Breakdown
            </h3>
            <p className="text-xs text-neutral-400">
              Distribution across verification states
            </p>
          </div>

          {/* Segmented Progress Bar */}
          <div className="space-y-3">
            <div className="h-3 w-full bg-neutral-100 rounded-full overflow-hidden flex shadow-inner">
              <div
                style={{ width: `${totals.runs > 0 ? (totals.approved / totals.runs) * 100 : 0}%` }}
                className="bg-emerald-500 h-full transition-all"
                title={`Approved: ${totals.approved}`}
              />
              <div
                style={{ width: `${totals.runs > 0 ? (totals.needs_review / totals.runs) * 100 : 0}%` }}
                className="bg-amber-400 h-full transition-all"
                title={`Needs Review: ${totals.needs_review}`}
              />
              <div
                style={{ width: `${totals.runs > 0 ? (totals.on_hold / totals.runs) * 100 : 0}%` }}
                className="bg-slate-400 h-full transition-all"
                title={`On Hold: ${totals.on_hold}`}
              />
              <div
                style={{ width: `${totals.runs > 0 ? (totals.rejected / totals.runs) * 100 : 0}%` }}
                className="bg-rose-500 h-full transition-all"
                title={`Rejected: ${totals.rejected}`}
              />
            </div>

            {/* Breakdown List */}
            <div className="space-y-2 text-xs font-mono">
              <div className="flex items-center justify-between text-neutral-700">
                <span className="flex items-center gap-2 font-sans font-medium">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Approved
                </span>
                <span>{totals.approved} ({totals.runs > 0 ? Math.round((totals.approved / totals.runs) * 100) : 0}%)</span>
              </div>

              <div className="flex items-center justify-between text-neutral-700">
                <span className="flex items-center gap-2 font-sans font-medium">
                  <span className="h-2 w-2 rounded-full bg-amber-400" />
                  Needs review
                </span>
                <span>{totals.needs_review} ({totals.runs > 0 ? Math.round((totals.needs_review / totals.runs) * 100) : 0}%)</span>
              </div>

              <div className="flex items-center justify-between text-neutral-700">
                <span className="flex items-center gap-2 font-sans font-medium">
                  <span className="h-2 w-2 rounded-full bg-slate-400" />
                  On hold
                </span>
                <span>{totals.on_hold} ({totals.runs > 0 ? Math.round((totals.on_hold / totals.runs) * 100) : 0}%)</span>
              </div>

              <div className="flex items-center justify-between text-neutral-700">
                <span className="flex items-center gap-2 font-sans font-medium">
                  <span className="h-2 w-2 rounded-full bg-rose-500" />
                  Rejected
                </span>
                <span>{totals.rejected} ({totals.runs > 0 ? Math.round((totals.rejected / totals.runs) * 100) : 0}%)</span>
              </div>
            </div>
          </div>

          {/* Financial Totals */}
          <div className="pt-4 border-t border-neutral-100 space-y-1.5 text-xs font-mono">
            <div className="flex justify-between text-neutral-500">
              <span className="font-sans">Pending Review Spend:</span>
              <span>{formatCurrency(amount_by_decision_inr?.NEEDS_REVIEW || 0, 'INR')}</span>
            </div>
            <div className="flex justify-between text-neutral-500">
              <span className="font-sans">Blocked / Disputed:</span>
              <span className="text-rose-600">{formatCurrency(amount_by_decision_inr?.REJECT || 0, 'INR')}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Two Columns: Top Suppliers & Most Common Issues */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Suppliers */}
        <div className="p-6 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-neutral-700" />
              <h3 className="text-sm font-semibold text-neutral-900">
                Top Suppliers by Spend
              </h3>
            </div>
            <span className="text-xs font-mono text-neutral-400">
              Top {top_vendors.length}
            </span>
          </div>

          <div className="space-y-3">
            {top_vendors.length === 0 ? (
              <p className="text-xs text-neutral-400 py-4 text-center">
                No vendor volume recorded yet.
              </p>
            ) : (
              top_vendors.map((vendor, idx) => {
                const pct = Math.min(100, Math.max(5, (vendor.total_inr / maxVendorSpend) * 100));
                return (
                  <div key={idx} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-neutral-900 truncate max-w-[200px]">
                        {vendor.name}
                      </span>
                      <div className="flex items-center gap-2 font-mono">
                        <span className="text-[11px] text-neutral-400">
                          {vendor.count} inv
                        </span>
                        <span className="font-semibold text-neutral-900">
                          {formatCurrency(vendor.total_inr, 'INR')}
                        </span>
                      </div>
                    </div>

                    <div className="h-1.5 w-full bg-neutral-100 rounded-full overflow-hidden">
                      <div
                        style={{ width: `${pct}%` }}
                        className="bg-neutral-900 h-full rounded-full transition-all"
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Most Common Issues */}
        <div className="p-6 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-neutral-700" />
              <h3 className="text-sm font-semibold text-neutral-900">
                Most Common Issues
              </h3>
            </div>
            <span className="text-xs font-mono text-neutral-400">
              Audit flags
            </span>
          </div>

          <div className="space-y-2.5">
            {reason_breakdown.length === 0 ? (
              <div className="py-6 text-center text-xs text-neutral-400 space-y-1">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 mx-auto" />
                <p>Clean processing records! No policy discrepancies flagged.</p>
              </div>
            ) : (
              reason_breakdown.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-neutral-50 border border-neutral-100 text-xs"
                >
                  <div className="flex items-start gap-2">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                    <span className="text-neutral-700 leading-snug font-sans">
                      {item.label}
                    </span>
                  </div>

                  <span className="px-2 py-0.5 rounded-full bg-white border border-neutral-200 text-neutral-800 font-mono text-[11px] font-medium shrink-0">
                    {item.count}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Recent Invoices Table */}
      <div className="p-6 rounded-2xl border border-neutral-200/90 bg-white shadow-2xs space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-neutral-900">
              Recent Invoices
            </h3>
            <p className="text-xs text-neutral-400">
              Latest incoming supplier runs
            </p>
          </div>

          <button
            onClick={onNavigateToInvoices}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-900 hover:text-black hover:underline cursor-pointer"
          >
            <span>View all in Invoices</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="rounded-xl border border-neutral-200 overflow-hidden">
          <table className="w-full text-left text-xs">
            <thead className="bg-neutral-50/80 text-neutral-500 font-mono uppercase tracking-wider text-[11px] border-b border-neutral-200">
              <tr>
                <th className="px-4 py-2.5 font-medium">Vendor</th>
                <th className="px-4 py-2.5 font-medium">Invoice #</th>
                <th className="px-4 py-2.5 font-medium">PO Ref</th>
                <th className="px-4 py-2.5 font-medium text-right">Amount</th>
                <th className="px-4 py-2.5 font-medium text-center">Status</th>
                <th className="px-4 py-2.5 font-medium text-right">Date</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100 font-sans">
              {recentRuns.slice(0, 6).map((run) => {
                const inv = run.standard_invoice;
                const vendor = run.matched_vendor_name || inv?.vendor_name?.value || 'Unknown Vendor';
                const invNumber = inv?.invoice_number?.value || run.run_id;
                const poRef = run.matched_po_number || inv?.po_reference?.value || '—';
                const currency = run.invoice_currency || inv?.currency?.value || 'INR';
                const total = run.invoice_total ?? inv?.total?.value ?? 0;
                const date = inv?.invoice_date?.value || run.created_at;
                const badge = getDecisionBadge(run.decision);

                return (
                  <tr
                    key={run.run_id}
                    onClick={() => onSelectRun(run)}
                    className="hover:bg-neutral-50/80 transition-colors cursor-pointer group"
                  >
                    <td className="px-4 py-3 font-medium text-neutral-900 truncate max-w-[200px]">
                      {vendor}
                    </td>
                    <td className="px-4 py-3 font-mono text-neutral-600">
                      {invNumber}
                    </td>
                    <td className="px-4 py-3 font-mono text-neutral-500">
                      {poRef}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-medium text-neutral-900">
                      {formatCurrency(total, currency)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${badge.className}`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${badge.dotClass}`} />
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-neutral-400">
                      {formatDate(date)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
