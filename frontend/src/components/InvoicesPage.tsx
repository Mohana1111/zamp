import React, { useState, useRef, useMemo } from 'react';
import {
  Search,
  UploadCloud,
  FileText,
  Loader2,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock
} from 'lucide-react';
import { InvoiceRunResult, DecisionType, FileProcessingState, StreamStage } from '../types';
import { formatCurrency, formatDate, getDecisionBadge } from '../utils/formatters';
import { TableSkeleton } from './Skeletons';
import { ProcessingPanel } from './ProcessingPanel';
import { api } from '../services/api';

interface InvoicesPageProps {
  runs: InvoiceRunResult[];
  isLoading: boolean;
  onSelectRun: (run: InvoiceRunResult) => void;
  onRunsUpdated: (newRuns: InvoiceRunResult[]) => void;
}

export const InvoicesPage: React.FC<InvoicesPageProps> = ({
  runs,
  isLoading,
  onSelectRun,
  onRunsUpdated
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<DecisionType | 'ALL'>('ALL');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Live stage streaming state
  const [processingFiles, setProcessingFiles] = useState<FileProcessingState[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isStreamComplete, setIsStreamComplete] = useState(false);

  // Compute stat counts
  const stats = useMemo(() => {
    const awaitingReview = runs.filter((r) => r.decision === 'NEEDS_REVIEW').length;
    const approved = runs.filter((r) => r.decision === 'AUTO_APPROVE').length;
    const onHold = runs.filter((r) => r.decision === 'ON_HOLD').length;
    const rejected = runs.filter((r) => r.decision === 'REJECT').length;
    return { awaitingReview, approved, onHold, rejected, total: runs.length };
  }, [runs]);

  // Filtered runs
  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      if (activeFilter !== 'ALL' && run.decision !== activeFilter) {
        return false;
      }

      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const vendor = (run.matched_vendor_name || run.standard_invoice?.vendor_name?.value || '').toLowerCase();
        const invNo = (run.standard_invoice?.invoice_number?.value || run.run_id).toLowerCase();
        const poRef = (run.matched_po_number || run.standard_invoice?.po_reference?.value || '').toLowerCase();
        return vendor.includes(query) || invNo.includes(query) || poRef.includes(query);
      }

      return true;
    });
  }, [runs, activeFilter, searchQuery]);

  // Handle file drop & selection
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;
    await startStreamUpload(files);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    await startStreamUpload(files);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const startStreamUpload = async (files: File[]) => {
    setIsStreaming(true);
    setIsStreamComplete(false);

    // Initial state for each file
    const initialStates: FileProcessingState[] = files.map((f, idx) => ({
      file: f.name,
      index: idx,
      total: files.length,
      stages: [],
      status: 'PROCESSING'
    }));
    setProcessingFiles(initialStates);

    const newlyCompletedRuns: InvoiceRunResult[] = [];

    try {
      await api.uploadFilesStream(files, (event: any) => {
        if (!event || !event.type) return;

        if (event.type === 'file_start') {
          setProcessingFiles((prev) =>
            prev.map((item) =>
              item.file === event.file
                ? { ...item, status: 'PROCESSING' }
                : item
            )
          );
        } else if (event.type === 'stage') {
          setProcessingFiles((prev) =>
            prev.map((item) => {
              if (item.file === event.file) {
                const stageObj: StreamStage = {
                  key: event.stage.key || event.stage.name,
                  name: event.stage.name,
                  status: event.stage.status || 'PASS',
                  summary: event.stage.summary,
                  duration_ms: event.stage.duration_ms
                };

                // Append stage if not already in stages
                const existingIdx = item.stages.findIndex((s) => s.key === stageObj.key);
                const updatedStages = existingIdx >= 0
                  ? item.stages.map((s, idx) => (idx === existingIdx ? stageObj : s))
                  : [...item.stages, stageObj];

                return {
                  ...item,
                  stages: updatedStages
                };
              }
              return item;
            })
          );
        } else if (event.type === 'run_complete') {
          if (event.run) {
            newlyCompletedRuns.push(event.run);
            onRunsUpdated([event.run]);
          }

          setProcessingFiles((prev) =>
            prev.map((item) =>
              item.file === event.file
                ? {
                    ...item,
                    status: 'DONE',
                    run: event.run
                  }
                : item
            )
          );
        } else if (event.type === 'error') {
          setProcessingFiles((prev) =>
            prev.map((item) =>
              item.file === event.file
                ? {
                    ...item,
                    status: 'ERROR',
                    error: event.message || 'Verification error'
                  }
                : item
            )
          );
        } else if (event.type === 'done') {
          setIsStreamComplete(true);
        }
      });
    } catch (err: any) {
      console.warn('Upload streaming error', err);
    } finally {
      setIsStreaming(false);
      setIsStreamComplete(true);
    }
  };

  return (
    <div className="space-y-6">
      {/* 4 Compact Stat Tiles (Filter Buttons) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        {/* Stat 1: Awaiting Review */}
        <button
          onClick={() => setActiveFilter(activeFilter === 'NEEDS_REVIEW' ? 'ALL' : 'NEEDS_REVIEW')}
          className={`p-4 rounded-2xl border text-left transition-all cursor-pointer ${
            activeFilter === 'NEEDS_REVIEW'
              ? 'border-amber-400 bg-amber-50/60 ring-2 ring-amber-400/30 shadow-xs'
              : 'border-neutral-200/80 bg-white hover:border-amber-200 hover:bg-amber-50/20'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-amber-700 font-medium">
            <span>Awaiting review</span>
            <AlertTriangle className="h-4 w-4 text-amber-500" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono tracking-tight text-neutral-900">
            {stats.awaitingReview}
          </div>
        </button>

        {/* Stat 2: Approved */}
        <button
          onClick={() => setActiveFilter(activeFilter === 'AUTO_APPROVE' ? 'ALL' : 'AUTO_APPROVE')}
          className={`p-4 rounded-2xl border text-left transition-all cursor-pointer ${
            activeFilter === 'AUTO_APPROVE'
              ? 'border-emerald-400 bg-emerald-50/60 ring-2 ring-emerald-400/30 shadow-xs'
              : 'border-neutral-200/80 bg-white hover:border-emerald-200 hover:bg-emerald-50/20'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-emerald-700 font-medium">
            <span>Approved</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono tracking-tight text-neutral-900">
            {stats.approved}
          </div>
        </button>

        {/* Stat 3: On Hold */}
        <button
          onClick={() => setActiveFilter(activeFilter === 'ON_HOLD' ? 'ALL' : 'ON_HOLD')}
          className={`p-4 rounded-2xl border text-left transition-all cursor-pointer ${
            activeFilter === 'ON_HOLD'
              ? 'border-slate-400 bg-slate-100/60 ring-2 ring-slate-400/30 shadow-xs'
              : 'border-neutral-200/80 bg-white hover:border-slate-200 hover:bg-slate-50/30'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-slate-700 font-medium">
            <span>On hold</span>
            <Clock className="h-4 w-4 text-slate-400" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono tracking-tight text-neutral-900">
            {stats.onHold}
          </div>
        </button>

        {/* Stat 4: Rejected */}
        <button
          onClick={() => setActiveFilter(activeFilter === 'REJECT' ? 'ALL' : 'REJECT')}
          className={`p-4 rounded-2xl border text-left transition-all cursor-pointer ${
            activeFilter === 'REJECT'
              ? 'border-rose-400 bg-rose-50/60 ring-2 ring-rose-400/30 shadow-xs'
              : 'border-neutral-200/80 bg-white hover:border-rose-200 hover:bg-rose-50/20'
          }`}
        >
          <div className="flex items-center justify-between text-xs text-rose-700 font-medium">
            <span>Rejected</span>
            <XCircle className="h-4 w-4 text-rose-500" />
          </div>
          <div className="mt-2 text-2xl font-bold font-mono tracking-tight text-neutral-900">
            {stats.rejected}
          </div>
        </button>
      </div>

      {/* Big Friendly Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative border-2 border-dashed rounded-2xl p-6 sm:p-8 text-center transition-all cursor-pointer ${
          isDragOver
            ? 'border-neutral-900 bg-neutral-100/70 scale-[0.995]'
            : 'border-neutral-300/80 bg-white hover:border-neutral-400 hover:bg-neutral-50/50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp,.tiff,.xlsx,.docx,.txt"
          onChange={handleFileSelect}
          className="hidden"
        />

        <div className="max-w-md mx-auto space-y-2.5 pointer-events-none">
          <div className="h-11 w-11 rounded-2xl bg-neutral-100 flex items-center justify-center mx-auto text-neutral-700">
            {isStreaming ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <UploadCloud className="h-5 w-5" />
            )}
          </div>

          <div>
            <div className="text-sm font-semibold text-neutral-900">
              Drop invoices here — PDF, image, Excel or Word
            </div>
            <p className="text-xs text-neutral-400 mt-0.5">
              Drag multiple files or click to browse from your computer
            </p>
          </div>
        </div>
      </div>

      {/* Live Processing Panel (When streaming / processing) */}
      {processingFiles.length > 0 && (
        <ProcessingPanel
          files={processingFiles}
          isComplete={isStreamComplete}
          onClose={() => setProcessingFiles([])}
          onSelectRun={(run) => onSelectRun(run)}
        />
      )}

      {/* Invoices List Header & Search */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by vendor, invoice #, PO..."
            className="w-full text-xs rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
          />
        </div>

        {activeFilter !== 'ALL' && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-neutral-500 font-mono">Filtered by:</span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-neutral-100 text-neutral-800 font-medium">
              <span>{getDecisionBadge(activeFilter).label}</span>
              <button
                onClick={() => setActiveFilter('ALL')}
                className="hover:text-rose-600 ml-1 cursor-pointer font-bold"
              >
                ×
              </button>
            </span>
          </div>
        )}
      </div>

      {/* Main Invoices Table */}
      <div className="rounded-2xl border border-neutral-200/90 bg-white overflow-hidden shadow-2xs">
        {isLoading ? (
          <TableSkeleton rows={6} />
        ) : filteredRuns.length === 0 ? (
          <div className="py-20 text-center space-y-3 px-4">
            <FileText className="h-9 w-9 text-neutral-300 mx-auto" />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-neutral-800">
                {runs.length === 0 ? 'No invoices received yet' : 'No matching invoices'}
              </h3>
              <p className="text-xs text-neutral-400 max-w-sm mx-auto">
                {runs.length === 0
                  ? 'Drop an invoice file in the box above to extract line items and verify against purchase orders.'
                  : 'Try adjusting your search criteria or resetting the active status filter.'}
              </p>
            </div>
            {runs.length === 0 && (
              <button
                onClick={() => fileInputRef.current?.click()}
                className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-neutral-900 text-white text-xs font-medium hover:bg-black transition-colors cursor-pointer"
              >
                <span>Upload invoice</span>
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-50/80 text-neutral-500 font-mono uppercase tracking-wider text-[11px] border-b border-neutral-200">
                <tr>
                  <th className="px-5 py-3 font-medium">Vendor</th>
                  <th className="px-4 py-3 font-medium">Invoice #</th>
                  <th className="px-4 py-3 font-medium">PO Ref</th>
                  <th className="px-4 py-3 font-medium text-right">Amount</th>
                  <th className="px-4 py-3 font-medium text-center">Status</th>
                  <th className="px-5 py-3 font-medium text-right">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 font-sans">
                {filteredRuns.map((run) => {
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
                      <td className="px-5 py-3.5 font-medium text-neutral-900 truncate max-w-[220px]">
                        <span className="truncate group-hover:text-black">
                          {vendor}
                        </span>
                      </td>

                      <td className="px-4 py-3.5 font-mono text-neutral-600">
                        {invNumber}
                      </td>

                      <td className="px-4 py-3.5 font-mono text-neutral-500">
                        {poRef}
                      </td>

                      <td className="px-4 py-3.5 text-right font-mono font-medium text-neutral-900">
                        {formatCurrency(total, currency)}
                      </td>

                      <td className="px-4 py-3.5 text-center">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${badge.className}`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-full ${badge.dotClass}`} />
                          {badge.label}
                        </span>
                      </td>

                      <td className="px-5 py-3.5 text-right font-mono text-neutral-400">
                        {formatDate(date)}
                      </td>
                    </tr>
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
