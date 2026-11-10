import React from 'react';
import {
  Loader2,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  X,
  ArrowRight,
  Sparkles,
  Check
} from 'lucide-react';
import { FileProcessingState, InvoiceRunResult } from '../types';
import {
  STANDARD_STAGES,
  mapStageKeyToFriendlyName,
  getDecisionBadge
} from '../utils/formatters';

interface ProcessingPanelProps {
  files: FileProcessingState[];
  isComplete: boolean;
  onClose: () => void;
  onSelectRun: (run: InvoiceRunResult) => void;
}

export const ProcessingPanel: React.FC<ProcessingPanelProps> = ({
  files,
  isComplete,
  onClose,
  onSelectRun
}) => {
  if (files.length === 0) return null;

  const completedCount = files.filter((f) => f.status === 'DONE').length;

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white shadow-md overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200">
      {/* Top Banner Header */}
      <div className="px-5 py-4 border-b border-neutral-100 flex items-center justify-between gap-4 bg-neutral-50/60">
        <div className="flex items-center gap-2.5">
          {isComplete ? (
            <div className="h-7 w-7 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
              <Check className="h-4 w-4" />
            </div>
          ) : (
            <div className="h-7 w-7 rounded-full bg-neutral-900 text-white flex items-center justify-center shrink-0">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          )}
          <div>
            <h3 className="text-sm font-semibold text-neutral-900 leading-tight">
              {isComplete
                ? `Completed ${files.length} invoice${files.length > 1 ? 's' : ''}`
                : `Processing ${completedCount + 1} of ${files.length} invoice${files.length > 1 ? 's' : ''}...`}
            </h3>
            <p className="text-xs text-neutral-500 mt-0.5">
              Live deterministic verification, 2-way matching, and safety review
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isComplete && (
            <button
              onClick={onClose}
              className="px-3 py-1.5 rounded-lg bg-neutral-900 hover:bg-black text-white text-xs font-medium transition-colors cursor-pointer"
            >
              Done
            </button>
          )}

          <button
            onClick={onClose}
            className="p-1.5 text-neutral-400 hover:text-neutral-900 rounded-lg hover:bg-neutral-100 transition-colors cursor-pointer"
            title="Dismiss panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Per-File Progress Cards */}
      <div className="p-5 space-y-4 max-h-[520px] overflow-y-auto">
        {files.map((fileState, fIdx) => {
          const isFileDone = fileState.status === 'DONE';
          const isFileError = fileState.status === 'ERROR';
          const decisionBadge = fileState.run ? getDecisionBadge(fileState.run.decision) : null;

          return (
            <div
              key={`${fileState.file}-${fIdx}`}
              className="rounded-xl border border-neutral-200/90 bg-neutral-50/40 p-4 space-y-3.5 transition-all"
            >
              {/* File Title Bar */}
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <FileText className="h-4 w-4 text-neutral-500 shrink-0" />
                  <span className="font-mono text-xs font-medium text-neutral-900 truncate">
                    {fileState.file}
                  </span>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {decisionBadge && (
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${decisionBadge.className}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${decisionBadge.dotClass}`} />
                      {decisionBadge.label}
                    </span>
                  )}

                  {!isFileDone && !isFileError && (
                    <span className="inline-flex items-center gap-1.5 text-xs text-neutral-500 font-mono">
                      <Loader2 className="h-3 w-3 animate-spin text-neutral-700" />
                      Analyzing...
                    </span>
                  )}
                </div>
              </div>

              {/* Error Notice */}
              {isFileError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-800 flex items-start gap-2">
                  <XCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
                  <span>{fileState.error || 'Failed to process document'}</span>
                </div>
              )}

              {/* Stages Timeline */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                {STANDARD_STAGES.map((stdStage, sIdx) => {
                  // Find if stage completed or is active in fileState.stages
                  const matched = fileState.stages.find(
                    (s) =>
                      mapStageKeyToFriendlyName(s.key, s.name).toLowerCase() ===
                      stdStage.name.toLowerCase()
                  );

                  // Current active stage is the first one that is pending or fileState.stages.length
                  const isCurrentActive =
                    !isFileDone &&
                    !isFileError &&
                    fileState.stages.length === sIdx;

                  const hasPassed = matched && (matched.status === 'PASS' || matched.status === 'WARN');
                  const hasFailed = matched && matched.status === 'FAIL';
                  const isPending = !matched && !isCurrentActive;

                  return (
                    <div
                      key={stdStage.key}
                      className={`flex items-start gap-2.5 p-2 rounded-lg text-xs transition-colors ${
                        isCurrentActive
                          ? 'bg-white border border-neutral-300 shadow-2xs'
                          : matched
                          ? 'bg-white/70 border border-neutral-100'
                          : 'opacity-40'
                      }`}
                    >
                      {/* Status Icon */}
                      <div className="shrink-0 mt-0.5">
                        {isCurrentActive ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-neutral-900" />
                        ) : hasPassed ? (
                          matched.status === 'WARN' ? (
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                          ) : (
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                          )
                        ) : hasFailed ? (
                          <XCircle className="h-3.5 w-3.5 text-rose-500" />
                        ) : (
                          <div className="h-3.5 w-3.5 rounded-full border border-neutral-300" />
                        )}
                      </div>

                      {/* Content */}
                      <div className="min-w-0 flex-1 leading-snug">
                        <div className="flex items-center justify-between gap-1">
                          <span
                            className={`font-medium truncate ${
                              isCurrentActive
                                ? 'text-neutral-900 font-semibold'
                                : matched
                                ? 'text-neutral-800'
                                : 'text-neutral-500'
                            }`}
                          >
                            {stdStage.name}
                          </span>

                          {matched?.duration_ms !== undefined && (
                            <span className="text-[10px] font-mono text-neutral-400 shrink-0">
                              {matched.duration_ms}ms
                            </span>
                          )}
                        </div>

                        {matched?.summary && (
                          <p className="text-[11px] text-neutral-500 truncate mt-0.5">
                            {matched.summary}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Completed Footer with "View details" button */}
              {isFileDone && fileState.run && (
                <div className="pt-2 border-t border-neutral-200/60 flex items-center justify-between">
                  <div className="text-xs text-neutral-600 font-mono">
                    {fileState.run.matched_vendor_name || 'Vendor verified'} •{' '}
                    {fileState.run.invoice_currency}{' '}
                    {fileState.run.invoice_total.toLocaleString()}
                  </div>

                  <button
                    onClick={() => onSelectRun(fileState.run!)}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-neutral-900 hover:text-black hover:underline cursor-pointer"
                  >
                    <span>View details</span>
                    <ArrowRight className="h-3 w-3" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
