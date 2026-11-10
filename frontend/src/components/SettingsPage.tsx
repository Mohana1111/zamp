import React, { useState, useEffect } from 'react';
import {
  Save,
  Key,
  ShieldCheck,
  CheckCircle2,
  Sparkles,
  Sliders,
  RotateCcw,
  Eye,
  EyeOff,
  Loader2
} from 'lucide-react';
import { SystemSettings } from '../types';

interface SettingsPageProps {
  settings: SystemSettings;
  onSaveSettings: (updated: Partial<SystemSettings>) => Promise<void>;
  onResetData: () => Promise<void>;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  settings,
  onSaveSettings,
  onResetData
}) => {
  const [form, setForm] = useState<SystemSettings>({ ...settings });
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showApiKey, setShowApiKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isResetting, setIsResetting] = useState(false);

  useEffect(() => {
    setForm({ ...settings });
  }, [settings]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      const payload: Partial<SystemSettings> = {
        default_price_tolerance_pct: Number(form.default_price_tolerance_pct),
        default_total_tolerance_pct: Number(form.default_total_tolerance_pct),
        default_auto_approve_limit_inr: form.default_auto_approve_limit_inr ? Number(form.default_auto_approve_limit_inr) : null,
        duplicate_window_days: Number(form.duplicate_window_days),
        require_po_above_inr: Number(form.require_po_above_inr),
        ai_review_enabled: Boolean(form.ai_review_enabled),
        ai_min_confidence: Number(form.ai_min_confidence)
      };

      if (apiKeyInput.trim()) {
        payload.api_key = apiKeyInput.trim();
      }

      await onSaveSettings(payload);
      setApiKeyInput('');
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    if (confirm('Are you sure you want to reset all processed invoices? This clears the AP queue.')) {
      setIsResetting(true);
      try {
        await onResetData();
      } finally {
        setIsResetting(false);
      }
    }
  };

  const isKeyConnected = Boolean(settings.has_api_key || form.has_api_key);

  return (
    <div className="max-w-3xl space-y-8">
      <form onSubmit={handleSave} className="space-y-8">
        {/* Card 1: Tolerances & Validation Limits */}
        <div className="p-6 rounded-2xl border border-neutral-200/90 bg-white space-y-6 shadow-2xs">
          <div className="flex items-center gap-2.5 pb-3 border-b border-neutral-100">
            <Sliders className="h-4 w-4 text-neutral-800" />
            <div>
              <h3 className="text-sm font-semibold text-neutral-900">
                Verification Tolerances & Thresholds
              </h3>
              <p className="text-xs text-neutral-400">
                Configure acceptable variance thresholds for automatic approval
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Price Tolerance */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-neutral-700">
                Default Line Item Price Tolerance %
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={form.default_price_tolerance_pct}
                onChange={(e) => setForm({ ...form, default_price_tolerance_pct: parseFloat(e.target.value) || 0 })}
                className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900"
              />
              <p className="text-[11px] text-neutral-400">
                Allowable variance between invoice unit prices and purchase order line items.
              </p>
            </div>

            {/* Total Tolerance */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-neutral-700">
                Default Total Amount Tolerance %
              </label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={form.default_total_tolerance_pct}
                onChange={(e) => setForm({ ...form, default_total_tolerance_pct: parseFloat(e.target.value) || 0 })}
                className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900"
              />
              <p className="text-[11px] text-neutral-400">
                Allowable variance between total invoice amount and PO total sum.
              </p>
            </div>

            {/* Require PO above limit */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-neutral-700">
                Mandatory PO Threshold (INR)
              </label>
              <input
                type="number"
                step="1000"
                min="0"
                value={form.require_po_above_inr}
                onChange={(e) => setForm({ ...form, require_po_above_inr: parseFloat(e.target.value) || 0 })}
                className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900"
              />
              <p className="text-[11px] text-neutral-400">
                Invoices exceeding this amount require a matching purchase order reference.
              </p>
            </div>

            {/* Duplicate window */}
            <div className="space-y-1.5">
              <label className="block text-xs font-medium text-neutral-700">
                Duplicate Detection Window (Days)
              </label>
              <input
                type="number"
                step="1"
                min="1"
                max="1000"
                value={form.duplicate_window_days}
                onChange={(e) => setForm({ ...form, duplicate_window_days: parseInt(e.target.value, 10) || 365 })}
                className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900"
              />
              <p className="text-[11px] text-neutral-400">
                Historical time window to flag duplicate invoice numbers or identical totals.
              </p>
            </div>

            {/* Global Auto-Approve Limit */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="block text-xs font-medium text-neutral-700">
                Global Auto-Approve Limit (INR, optional)
              </label>
              <input
                type="number"
                step="1000"
                value={form.default_auto_approve_limit_inr ?? ''}
                onChange={(e) =>
                  setForm({
                    ...form,
                    default_auto_approve_limit_inr: e.target.value ? parseFloat(e.target.value) : null
                  })
                }
                placeholder="No global limit (vendor policy applies)"
                className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900"
              />
              <p className="text-[11px] text-neutral-400">
                Ceiling limit for automatic approval across all vendors. Overrides individual limits when exceeded.
              </p>
            </div>
          </div>
        </div>

        {/* Card 2: AI Reasoning Layer */}
        <div className="p-6 rounded-2xl border border-neutral-200/90 bg-white space-y-6 shadow-2xs">
          <div className="flex items-center justify-between pb-3 border-b border-neutral-100">
            <div className="flex items-center gap-2.5">
              <Sparkles className="h-4 w-4 text-neutral-800" />
              <div>
                <h3 className="text-sm font-semibold text-neutral-900">
                  AI Safety & Reasoning Layer
                </h3>
                <p className="text-xs text-neutral-400">
                  Provides autonomous review, risk scoring, and discrepancy analysis
                </p>
              </div>
            </div>

            {/* AI Review Toggle */}
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium text-neutral-700">
                {form.ai_review_enabled ? 'Active' : 'Disabled'}
              </span>
              <button
                type="button"
                onClick={() => setForm({ ...form, ai_review_enabled: !form.ai_review_enabled })}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-hidden ${
                  form.ai_review_enabled ? 'bg-neutral-900' : 'bg-neutral-200'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                    form.ai_review_enabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>
          </div>

          <div className="space-y-4">
            {/* Minimum confidence threshold */}
            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-medium">
                <span className="text-neutral-700">Minimum Review Confidence Threshold</span>
                <span className="font-mono text-neutral-900 font-semibold">
                  {Math.round(form.ai_min_confidence * 100)}%
                </span>
              </div>
              <input
                type="range"
                min="0.5"
                max="0.99"
                step="0.01"
                value={form.ai_min_confidence}
                onChange={(e) => setForm({ ...form, ai_min_confidence: parseFloat(e.target.value) })}
                className="w-full accent-neutral-900 cursor-pointer"
              />
              <p className="text-[11px] text-neutral-400">
                Invoices with confidence scores below this threshold are routed to controller review.
              </p>
            </div>

            {/* API Key field */}
            <div className="space-y-1.5 pt-3 border-t border-neutral-100">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-medium text-neutral-700">
                  Reasoning API Key
                </label>
                {isKeyConnected && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 font-mono font-medium">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Connected
                  </span>
                )}
              </div>

              <div className="relative">
                <Key className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  placeholder={isKeyConnected ? '•••••••••••••••••••••••• (Key configured in environment)' : 'Enter API key...'}
                  className="w-full text-xs rounded-xl border border-neutral-200 bg-white pl-9 pr-10 py-2 text-neutral-900 font-mono placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-3 top-2.5 text-neutral-400 hover:text-neutral-900 cursor-pointer"
                >
                  {showApiKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              <p className="text-[11px] text-neutral-400">
                Keys may also be configured directly via server environment variables.
              </p>
            </div>
          </div>
        </div>

        {/* Save Bar */}
        <div className="flex items-center justify-between gap-4 pt-2">
          <button
            type="button"
            onClick={handleReset}
            disabled={isResetting}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium text-neutral-500 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>{isResetting ? 'Resetting...' : 'Reset demo state'}</span>
          </button>

          <button
            type="submit"
            disabled={isSaving}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-neutral-900 hover:bg-black text-white text-xs font-medium shadow-xs transition-colors cursor-pointer disabled:opacity-50"
          >
            {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            <span>Save settings</span>
          </button>
        </div>
      </form>
    </div>
  );
};
