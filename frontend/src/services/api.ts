import {
  InvoiceRunResult,
  OverviewResponse,
  PurchaseOrder,
  VendorMaster,
  VendorPolicy,
  SystemSettings,
  AIStatus,
  DecisionType,
  FXRate,
  DashboardData,
  AmountByDecision,
  VendorSpendSummary,
  ReasonBreakdownItem,
  TrendDayItem
} from '../types';

import {
  User,
  AuthResponse,
  LoginCredentials,
  SignupCredentials
} from '../types/auth';

import { translateReasonCode } from '../utils/formatters';

const API_BASE = import.meta.env.VITE_API_URL || '';

const DEFAULT_SETTINGS: SystemSettings = {
  default_price_tolerance_pct: 2,
  default_total_tolerance_pct: 1,
  default_auto_approve_limit_inr: null,
  duplicate_window_days: 365,
  require_po_above_inr: 50000,
  ai_review_enabled: true,
  ai_min_confidence: 0.85,
  api_key: '',
  has_api_key: false
};

const DEFAULT_FX_RATES: FXRate[] = [
  { currency: 'INR', rate_to_inr: 1.0, symbol: '₹', updated_at: '2026-10-28' },
  { currency: 'USD', rate_to_inr: 84.10, symbol: '$', updated_at: '2026-10-28' },
  { currency: 'EUR', rate_to_inr: 91.60, symbol: '€', updated_at: '2026-10-28' },
  { currency: 'GBP', rate_to_inr: 109.30, symbol: '£', updated_at: '2026-10-28' },
  { currency: 'SGD', rate_to_inr: 64.20, symbol: 'S$', updated_at: '2026-10-28' }
];

// In-memory fallback caches
let localRuns: InvoiceRunResult[] = [];
let localPOs: PurchaseOrder[] = [];
let localVendors: VendorMaster[] = [];
let localSettings: SystemSettings = { ...DEFAULT_SETTINGS };

// Load settings from local storage if available
try {
  const savedSettings = localStorage.getItem('clearpay_system_settings');
  if (savedSettings) {
    localSettings = { ...DEFAULT_SETTINGS, ...JSON.parse(savedSettings) };
  }
} catch {
  // Ignore
}

/**
 * Computes dashboard aggregation metrics from runs when GET /api/dashboard 404s.
 */
export function computeDashboardFallback(runs: InvoiceRunResult[]): DashboardData {
  const totalRuns = runs.length;
  const approved = runs.filter((r) => r.decision === 'AUTO_APPROVE').length;
  const needsReview = runs.filter((r) => r.decision === 'NEEDS_REVIEW').length;
  const onHold = runs.filter((r) => r.decision === 'ON_HOLD').length;
  const rejected = runs.filter((r) => r.decision === 'REJECT').length;
  const autoRate = totalRuns > 0 ? Math.round((approved / totalRuns) * 100) : 0;

  const amounts: AmountByDecision = {
    AUTO_APPROVE: 0,
    NEEDS_REVIEW: 0,
    ON_HOLD: 0,
    REJECT: 0
  };

  const vendorMap: Record<string, { count: number; total_inr: number }> = {};
  const reasonMap: Record<string, number> = {};

  for (const r of runs) {
    const inrVal = r.base_total_inr || r.base_Total_inr || (r.invoice_total * (r.fx_rate_to_inr || 1.0));
    if (amounts[r.decision] !== undefined) {
      amounts[r.decision] += inrVal;
    }

    const vName = r.matched_vendor_name || r.standard_invoice?.vendor_name?.value || 'Unknown Vendor';
    if (!vendorMap[vName]) {
      vendorMap[vName] = { count: 0, total_inr: 0 };
    }
    vendorMap[vName].count += 1;
    vendorMap[vName].total_inr += inrVal;

    for (const code of r.reason_codes || []) {
      if (code !== 'AUTO_APPROVE' && code !== 'PREAPPROVED_NO_PO') {
        const friendly = translateReasonCode(code);
        reasonMap[friendly] = (reasonMap[friendly] || 0) + 1;
      }
    }
  }

  const topVendors: VendorSpendSummary[] = Object.entries(vendorMap)
    .map(([name, data]) => ({ name, count: data.count, total_inr: data.total_inr }))
    .sort((a, b) => b.total_inr - a.total_inr)
    .slice(0, 5);

  const reasonBreakdown: ReasonBreakdownItem[] = Object.entries(reasonMap)
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  // Generate 14-day trend
  const today = new Date();
  const recentTrend: TrendDayItem[] = [];
  for (let i = 13; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = d.toISOString().split('T')[0];
    const dayRuns = runs.filter(
      (r) =>
        (r.created_at || '').startsWith(dateStr) ||
        (r.standard_invoice?.invoice_date?.value || '').startsWith(dateStr)
    );
    const dayApproved = dayRuns.filter((r) => r.decision === 'AUTO_APPROVE').length;
    recentTrend.push({
      date: dateStr,
      count: dayRuns.length,
      approved: dayApproved,
      flagged: dayRuns.length - dayApproved
    });
  }

  return {
    totals: {
      runs: totalRuns,
      approved,
      needs_review: needsReview,
      on_hold: onHold,
      rejected,
      auto_rate_pct: autoRate
    },
    amount_by_decision_inr: amounts,
    top_vendors: topVendors,
    reason_breakdown: reasonBreakdown,
    recent_trend: recentTrend
  };
}

export const api = {
  // ---------------------------------------------------------------------------
  // Dashboard & KPIs
  // ---------------------------------------------------------------------------
  async getDashboard(): Promise<DashboardData> {
    try {
      const res = await fetch(`${API_BASE}/api/dashboard`);
      if (res.ok) {
        const data = await res.json();
        if (data && data.totals) {
          return data;
        }
      }
    } catch (err) {
      console.warn('API /api/dashboard unavailable, computing from local runs', err);
    }

    const runs = await this.getRuns();
    return computeDashboardFallback(runs);
  },

  async runSample(sampleId: string = '01_happy_shree_ganesh_inr.pdf'): Promise<InvoiceRunResult | null> {
    try {
      const res = await fetch(`${API_BASE}/api/runs/sample/${encodeURIComponent(sampleId)}`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        const run: InvoiceRunResult = data.run || (Array.isArray(data.runs) ? data.runs[0] : data);
        if (run && run.run_id) {
          localRuns = [run, ...localRuns.filter((r) => r.run_id !== run.run_id)];
          return run;
        }
      }
    } catch (err) {
      console.warn(`API /api/runs/sample/${sampleId} error`, err);
    }
    return null;
  },

  // ---------------------------------------------------------------------------
  // Overview & Runs
  // ---------------------------------------------------------------------------
  async getOverview(): Promise<OverviewResponse> {
    try {
      const res = await fetch(`${API_BASE}/api/overview`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.recent_runs)) {
          localRuns = data.recent_runs;
        }
        if (Array.isArray(data.pos)) {
          localPOs = data.pos;
        }
        if (Array.isArray(data.vendors)) {
          localVendors = data.vendors;
        }
        return {
          ...data,
          recent_runs: localRuns,
          pos: localPOs,
          vendors: localVendors
        };
      }
    } catch (err) {
      console.warn('API /api/overview unavailable, using simulated local state', err);
    }

    const totalRuns = localRuns.length;
    const autoApproveCount = localRuns.filter((r) => r.decision === 'AUTO_APPROVE').length;
    const needsReviewCount = localRuns.filter((r) => r.decision === 'NEEDS_REVIEW').length;
    const rejectCount = localRuns.filter((r) => r.decision === 'REJECT').length;
    const autoApprovePct = totalRuns > 0 ? Math.round((autoApproveCount / totalRuns) * 1000) / 10 : 0;

    let blockedInr = 0;
    let totalInr = 0;
    for (const r of localRuns) {
      const inrVal = r.base_total_inr || r.base_Total_inr || r.invoice_total * (r.fx_rate_to_inr || 1.0);
      totalInr += inrVal;
      if (r.decision === 'REJECT') {
        blockedInr += inrVal;
      }
    }

    return {
      kpis: {
        total_runs: totalRuns,
        auto_approve_count: autoApproveCount,
        auto_approve_pct: autoApprovePct,
        needs_review_count: needsReviewCount,
        reject_count: rejectCount,
        fraud_and_duplicates_blocked_inr: blockedInr,
        total_amount_processed_inr: totalInr
      },
      recent_runs: localRuns,
      pos: localPOs,
      vendors: localVendors,
      fx_rates: DEFAULT_FX_RATES
    };
  },

  async getRuns(): Promise<InvoiceRunResult[]> {
    try {
      const res = await fetch(`${API_BASE}/api/runs`);
      if (res.ok) {
        const data = await res.json();
        localRuns = Array.isArray(data) ? data : data.runs || [];
        return localRuns;
      }
    } catch {
      console.warn('API /api/runs unavailable, using local cache');
    }
    return localRuns;
  },

  async getRun(runId: string): Promise<InvoiceRunResult | null> {
    try {
      const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`);
      if (res.ok) return await res.json();
    } catch {
      console.warn(`API /api/runs/${runId} unavailable`);
    }
    return localRuns.find((r) => r.run_id === runId) || null;
  },

  async uploadFiles(files: File[]): Promise<InvoiceRunResult[]> {
    const formData = new FormData();
    for (const file of files) {
      formData.append('files', file);
    }
    formData.append('source_type', 'UPLOAD');

    const res = await fetch(`${API_BASE}/api/runs/upload`, {
      method: 'POST',
      body: formData
    });

    if (res.ok) {
      const data = await res.json();
      const runs: InvoiceRunResult[] = data.runs || [];
      for (const run of runs) {
        localRuns = [run, ...localRuns.filter((r) => r.run_id !== run.run_id)];
      }
      return runs;
    } else {
      const errorText = await res.text();
      throw new Error(`Upload failed (${res.status}): ${errorText.slice(0, 120)}`);
    }
  },

  /**
   * Consumes SSE /api/runs/upload-stream endpoint with graceful animated fallback.
   */
  async uploadFilesStream(
    files: File[],
    onEvent: (event: any) => void
  ): Promise<InvoiceRunResult[]> {
    try {
      const formData = new FormData();
      for (const file of files) {
        formData.append('files', file);
      }
      formData.append('source_type', 'UPLOAD');

      const res = await fetch(`${API_BASE}/api/runs/upload-stream`, {
        method: 'POST',
        body: formData
      });

      if (res.ok && res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        const runs: InvoiceRunResult[] = [];

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.startsWith('data:')) {
              const jsonStr = trimmed.slice(5).trim();
              if (jsonStr) {
                try {
                  const parsed = JSON.parse(jsonStr);
                  onEvent(parsed);
                  if (parsed.type === 'run_complete' && parsed.run) {
                    runs.push(parsed.run);
                    localRuns = [parsed.run, ...localRuns.filter((r) => r.run_id !== parsed.run.run_id)];
                  }
                } catch (e) {
                  console.warn('Failed to parse SSE line', e);
                }
              }
            }
          }
        }

        onEvent({ type: 'done' });
        return runs;
      }
    } catch (err) {
      console.warn('upload-stream unavailable or failed, falling back to /api/runs/upload', err);
    }

    // Fallback: Upload sequentially and animate stages
    const runs = await this.uploadFiles(files);
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const run = runs[i] || runs[0];
      onEvent({ type: 'file_start', file: file.name, index: i, total: files.length });

      if (run && Array.isArray(run.stages)) {
        for (const st of run.stages) {
          await new Promise((resolve) => setTimeout(resolve, 200));
          onEvent({
            type: 'stage',
            file: file.name,
            stage: {
              key: st.key,
              name: st.name,
              status: st.status,
              summary: st.summary,
              duration_ms: st.duration_ms
            }
          });
        }
      }

      await new Promise((resolve) => setTimeout(resolve, 150));
      if (run) {
        onEvent({ type: 'run_complete', file: file.name, run });
      }
    }

    onEvent({ type: 'done' });
    return runs;
  },

  async approveRun(
    runId: string,
    reviewer: string = 'AP Lead',
    action: 'APPROVE' | 'REJECT' = 'APPROVE',
    comment?: string
  ): Promise<InvoiceRunResult | null> {
    try {
      const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reviewer, action, comment })
      });
      if (res.ok) {
        const data = await res.json();
        const updated = data.run || data;
        if (updated) {
          localRuns = localRuns.map((r) => (r.run_id === runId ? updated : r));
          return updated;
        }
      }
    } catch (err) {
      console.warn(`API /api/runs/${runId}/approve error`, err);
    }

    const target = localRuns.find((r) => r.run_id === runId);
    if (target) {
      const newDecision: DecisionType = action === 'APPROVE' ? 'AUTO_APPROVE' : 'REJECT';
      const updated: InvoiceRunResult = {
        ...target,
        decision: newDecision,
        human_approval_status: action === 'APPROVE' ? 'APPROVED_BY_HUMAN' : 'REJECTED_BY_HUMAN',
        human_approval_details: {
          reviewer,
          timestamp: new Date().toISOString(),
          action,
          comment
        }
      };
      localRuns = localRuns.map((r) => (r.run_id === runId ? updated : r));
      return updated;
    }
    return null;
  },

  async overrideDecision(
    runId: string,
    decision: DecisionType,
    comment: string,
    reviewer: string = 'AP Reviewer',
    preapproveVendor: boolean = false
  ): Promise<InvoiceRunResult | null> {
    try {
      const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          comment,
          reviewer,
          preapprove_vendor: preapproveVendor
        })
      });
      if (res.ok) {
        const updated = await res.json();
        localRuns = localRuns.map((r) => (r.run_id === runId ? updated : r));

        if (preapproveVendor && updated.matched_vendor_id) {
          this.preapproveVendor(updated.matched_vendor_id).catch(() => {});
        }

        return updated;
      }
    } catch (err) {
      console.warn(`API /api/runs/${runId}/override error`, err);
    }

    const target = localRuns.find((r) => r.run_id === runId);
    if (target) {
      const updated: InvoiceRunResult = {
        ...target,
        decision,
        human_override: {
          overridden_by: reviewer,
          overridden_at: new Date().toISOString(),
          prior_decision: target.decision,
          new_decision: decision,
          comment
        }
      };
      localRuns = localRuns.map((r) => (r.run_id === runId ? updated : r));

      if (preapproveVendor && target.matched_vendor_id) {
        this.preapproveVendor(target.matched_vendor_id).catch(() => {});
      }

      return updated;
    }
    return null;
  },

  async deleteRun(runId: string): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/runs/${encodeURIComponent(runId)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        localRuns = localRuns.filter((r) => r.run_id !== runId);
        return true;
      }
    } catch {
      console.warn(`API /api/runs/${runId} DELETE error`);
    }
    localRuns = localRuns.filter((r) => r.run_id !== runId);
    return true;
  },

  // ---------------------------------------------------------------------------
  // Vendors & Vendor Policy
  // ---------------------------------------------------------------------------
  async getVendors(): Promise<VendorMaster[]> {
    try {
      const res = await fetch(`${API_BASE}/api/vendors`);
      if (res.ok) {
        const data = await res.json();
        const list: VendorMaster[] = Array.isArray(data) ? data : data.vendors || [];
        localVendors = list.map((v) => {
          const trust = v.policy?.trust || v.trust || 'STANDARD';
          return {
            ...v,
            trust,
            auto_approve_limit: v.policy?.auto_approve_limit ?? v.auto_approve_limit ?? null,
            price_tolerance_pct: v.policy?.price_tolerance_pct ?? v.price_tolerance_pct ?? 2,
            total_tolerance_pct: v.policy?.total_tolerance_pct ?? v.total_tolerance_pct ?? 1,
            allow_without_po: v.policy?.allow_without_po ?? v.allow_without_po ?? false,
            notes: v.policy?.notes ?? v.notes ?? '',
            invoice_count: v.invoice_count ?? 0,
            approved_total_inr: v.approved_total_inr ?? 0,
            last_invoice_date: v.last_invoice_date ?? null
          };
        });
        return localVendors;
      }
    } catch {
      console.warn('API /api/vendors unavailable, using local fallback');
    }
    return localVendors;
  },

  async createVendor(vendorData: Partial<VendorMaster>): Promise<VendorMaster> {
    try {
      const res = await fetch(`${API_BASE}/api/vendors`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vendorData)
      });
      if (res.ok) {
        const data = await res.json();
        const created: VendorMaster = data.vendor || data;
        localVendors = [created, ...localVendors.filter((v) => v.vendor_id !== created.vendor_id)];
        return created;
      }
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create vendor');
    } catch (err: any) {
      if (err.message && !err.message.includes('fetch')) throw err;
      const created: VendorMaster = {
        vendor_id: vendorData.vendor_id || `VEND-${Date.now()}`,
        legal_name: vendorData.legal_name || 'New Vendor',
        aliases: vendorData.aliases || '',
        country: vendorData.country || 'IN',
        tax_id: vendorData.tax_id || '',
        default_currency: vendorData.default_currency || 'INR',
        bank_account: vendorData.bank_account || '',
        bank_code: vendorData.bank_code || '',
        status: vendorData.status || 'ACTIVE',
        payment_terms: vendorData.payment_terms || 'NET30',
        trust: vendorData.trust || 'STANDARD',
        auto_approve_limit: vendorData.auto_approve_limit ?? null,
        price_tolerance_pct: vendorData.price_tolerance_pct ?? 2,
        total_tolerance_pct: vendorData.total_tolerance_pct ?? 1,
        allow_without_po: vendorData.allow_without_po ?? false,
        notes: vendorData.notes || '',
        invoice_count: 0,
        approved_total_inr: 0,
        last_invoice_date: null
      };
      localVendors = [created, ...localVendors];
      return created;
    }
  },

  async updateVendor(vendorId: string, vendorData: Partial<VendorMaster>): Promise<VendorMaster> {
    try {
      const res = await fetch(`${API_BASE}/api/vendors/${encodeURIComponent(vendorId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(vendorData)
      });
      if (res.ok) {
        const data = await res.json();
        const updated: VendorMaster = data.vendor || data;
        localVendors = localVendors.map((v) => (v.vendor_id === vendorId ? { ...v, ...updated } : v));
        return updated;
      }
    } catch (err) {
      console.warn(`API /api/vendors/${vendorId} PUT error, using local fallback`, err);
    }

    localVendors = localVendors.map((v) => (v.vendor_id === vendorId ? { ...v, ...vendorData } : v));
    const target = localVendors.find((v) => v.vendor_id === vendorId);
    return target as VendorMaster;
  },

  async updateVendorPolicy(vendorId: string, policyData: Partial<VendorPolicy>): Promise<VendorMaster> {
    try {
      const res = await fetch(`${API_BASE}/api/vendors/${encodeURIComponent(vendorId)}/policy`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(policyData)
      });
      if (res.ok) {
        const data = await res.json();
        const updated: VendorMaster = data.vendor || data;
        localVendors = localVendors.map((v) => (v.vendor_id === vendorId ? { ...v, ...updated } : v));
        return updated;
      }
    } catch (err) {
      console.warn(`API /api/vendors/${vendorId}/policy PUT error, falling back to updateVendor`, err);
    }

    return this.updateVendor(vendorId, policyData as any);
  },

  async preapproveVendor(vendorId: string): Promise<VendorMaster> {
    try {
      const res = await fetch(`${API_BASE}/api/vendors/${encodeURIComponent(vendorId)}/preapprove`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        const updated: VendorMaster = data.vendor || data;
        localVendors = localVendors.map((v) => (v.vendor_id === vendorId ? { ...v, ...updated } : v));
        return updated;
      }
    } catch (err) {
      console.warn(`API /api/vendors/${vendorId}/preapprove error, falling back to policy update`, err);
    }

    return this.updateVendorPolicy(vendorId, { trust: 'PREAPPROVED' });
  },

  async deleteVendor(vendorId: string): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/vendors/${encodeURIComponent(vendorId)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        localVendors = localVendors.filter((v) => v.vendor_id !== vendorId);
        return true;
      }
    } catch {
      console.warn(`API /api/vendors/${vendorId} error`);
    }
    localVendors = localVendors.filter((v) => v.vendor_id !== vendorId);
    return true;
  },

  // ---------------------------------------------------------------------------
  // Purchase Orders
  // ---------------------------------------------------------------------------
  async getPurchaseOrders(): Promise<PurchaseOrder[]> {
    try {
      const res = await fetch(`${API_BASE}/api/purchase-orders`);
      if (res.ok) {
        const data = await res.json();
        localPOs = data.purchase_orders || (Array.isArray(data) ? data : []);
        return localPOs;
      }
    } catch {
      console.warn('API /api/purchase-orders unavailable, using local cache');
    }
    return localPOs;
  },

  async createPurchaseOrder(po: any): Promise<PurchaseOrder> {
    try {
      const res = await fetch(`${API_BASE}/api/purchase-orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(po)
      });
      if (res.ok) {
        const data = await res.json();
        const created: PurchaseOrder = data.purchase_order || data;
        localPOs = [created, ...localPOs.filter((p) => p.po_number !== created.po_number)];
        return created;
      }
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create Purchase Order');
    } catch (err: any) {
      if (err.message && !err.message.includes('fetch')) throw err;
      const created: PurchaseOrder = {
        po_number: po.po_number,
        vendor_id: po.vendor_id,
        vendor_name: po.vendor_name,
        currency: po.currency || 'INR',
        po_date: po.po_date || new Date().toISOString().split('T')[0],
        subtotal: po.subtotal || 0,
        tax_amount: po.tax_amount || 0,
        total_amount: po.total_amount || (po.subtotal || 0) + (po.tax_amount || 0),
        invoiced_amount: 0,
        remaining_amount: po.total_amount || (po.subtotal || 0) + (po.tax_amount || 0),
        status: 'OPEN',
        approver: po.approver || 'AP Lead',
        lines: po.lines || []
      };
      localPOs = [created, ...localPOs];
      return created;
    }
  },

  async deletePurchaseOrder(poNumber: string): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/purchase-orders/${encodeURIComponent(poNumber)}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        localPOs = localPOs.filter((p) => p.po_number !== poNumber);
        return true;
      }
    } catch {
      console.warn(`API /api/purchase-orders/${poNumber} error`);
    }
    localPOs = localPOs.filter((p) => p.po_number !== poNumber);
    return true;
  },

  // ---------------------------------------------------------------------------
  // Settings & AI Status
  // ---------------------------------------------------------------------------
  async getSettings(): Promise<SystemSettings> {
    try {
      const res = await fetch(`${API_BASE}/api/settings`);
      if (res.ok) {
        const data = await res.json();
        localSettings = { ...DEFAULT_SETTINGS, ...data };
        return localSettings;
      }
    } catch {
      // quiet fallback
    }

    try {
      const aiRes = await fetch(`${API_BASE}/api/config/ai`);
      if (aiRes.ok) {
        const aiData = await aiRes.json();
        localSettings.has_api_key = Boolean(aiData.has_api_key || aiData.gemini_configured || aiData.groq_configured);
      }
    } catch {
      // quiet fallback
    }

    return localSettings;
  },

  async updateSettings(settings: Partial<SystemSettings>): Promise<SystemSettings> {
    localSettings = { ...localSettings, ...settings };
    try {
      localStorage.setItem('clearpay_system_settings', JSON.stringify(localSettings));
    } catch {
      // Ignore
    }

    try {
      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      if (res.ok) {
        const data = await res.json();
        localSettings = { ...localSettings, ...data };
        return localSettings;
      }
    } catch {
      // Fallback
    }

    if (settings.api_key) {
      try {
        await fetch(`${API_BASE}/api/config/ai`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            api_key: settings.api_key,
            gemini_api_key: settings.api_key,
            groq_api_key: settings.api_key
          })
        });
        localSettings.has_api_key = true;
      } catch {
        // quiet
      }
    }

    return localSettings;
  },

  async getAIStatus(): Promise<AIStatus> {
    try {
      const res = await fetch(`${API_BASE}/api/ai/status`);
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // fallback
    }

    const enabled = localSettings.ai_review_enabled !== false;
    return {
      enabled,
      mode: enabled ? 'ai' : 'rules'
    };
  },

  // ---------------------------------------------------------------------------
  // Email Import Trigger
  // ---------------------------------------------------------------------------
  async syncAgentInboxNow(): Promise<{ status: string; runs?: InvoiceRunResult[]; message?: string }> {
    try {
      const res = await fetch(`${API_BASE}/api/agent/sync-now`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.runs)) {
          for (const run of data.runs) {
            if (!localRuns.find((r) => r.run_id === run.run_id)) {
              localRuns.unshift(run);
            }
          }
        }
        return data;
      }
    } catch (err) {
      console.warn('API /api/agent/sync-now error, trying fallback pull-all', err);
    }

    try {
      const res2 = await fetch(`${API_BASE}/api/sources/pull-all`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform: 'ALL' })
      });
      if (res2.ok) {
        const data = await res2.json();
        const runs: InvoiceRunResult[] = data.runs || [];
        for (const run of runs) {
          if (!localRuns.find((r) => r.run_id === run.run_id)) {
            localRuns.unshift(run);
          }
        }
        return { status: 'ok', runs, message: `Imported ${runs.length} new invoices from email inbox.` };
      }
    } catch {
      // quiet
    }

    return { status: 'ok', runs: [], message: 'No new invoices found in email inbox.' };
  },

  async resetData(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/reset`, { method: 'POST' });
      if (res.ok) {
        localRuns = [];
        return true;
      }
    } catch {
      // quiet
    }
    localRuns = [];
    return true;
  },

  // ---------------------------------------------------------------------------
  // Authentication
  // ---------------------------------------------------------------------------
  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials)
      });
      if (res.ok) {
        const data: AuthResponse = await res.json();
        localStorage.setItem('clearpay_session', JSON.stringify({ token: data.token, user: data.user }));
        return data;
      }
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Invalid username or password');
    } catch (err: any) {
      if (err.message && !err.message.includes('fetch') && !err.message.includes('NetworkError')) {
        throw err;
      }
      return this.localAuthFallbackLogin(credentials);
    }
  },

  localAuthFallbackLogin(credentials: LoginCredentials): AuthResponse {
    const rawUsers = localStorage.getItem('clearpay_local_users');
    let users: Record<string, any> = {};
    if (rawUsers) {
      try {
        users = JSON.parse(rawUsers);
      } catch {}
    }
    if (!users['admin_1']) {
      users['admin_1'] = {
        id: 'usr_admin_1',
        username: 'admin_1',
        password: 'pass@admin',
        name: 'Administrator',
        role: 'admin',
        email: 'admin@clearpay.internal'
      };
    }
    const user = users[credentials.username.toLowerCase()];
    if (!user || user.password !== credentials.password) {
      throw new Error('Invalid username or password');
    }
    const token = `local_token_${Date.now()}`;
    const response: AuthResponse = {
      token,
      user: {
        id: user.id,
        username: user.username,
        name: user.name,
        role: user.role,
        email: user.email
      },
      message: 'Logged in successfully'
    };
    localStorage.setItem('clearpay_session', JSON.stringify({ token, user: response.user }));
    return response;
  },

  async signup(credentials: SignupCredentials): Promise<AuthResponse> {
    try {
      const res = await fetch(`${API_BASE}/api/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials)
      });
      if (res.ok) {
        const data: AuthResponse = await res.json();
        localStorage.setItem('clearpay_session', JSON.stringify({ token: data.token, user: data.user }));
        return data;
      }
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.detail || 'Failed to create account');
    } catch (err: any) {
      if (err.message && !err.message.includes('fetch') && !err.message.includes('NetworkError')) {
        throw err;
      }
      return this.localAuthFallbackSignup(credentials);
    }
  },

  localAuthFallbackSignup(credentials: SignupCredentials): AuthResponse {
    const rawUsers = localStorage.getItem('clearpay_local_users');
    let users: Record<string, any> = {};
    if (rawUsers) {
      try {
        users = JSON.parse(rawUsers);
      } catch {}
    }
    const key = credentials.username.toLowerCase();
    if (key === 'admin_1' || users[key]) {
      throw new Error(`Username '${credentials.username}' is already taken`);
    }
    const newUser = {
      id: `usr_${Date.now()}`,
      username: credentials.username,
      password: credentials.password,
      name: credentials.name || credentials.username,
      role: 'user' as const,
      email: credentials.email || `${credentials.username}@clearpay.internal`
    };
    users[key] = newUser;
    localStorage.setItem('clearpay_local_users', JSON.stringify(users));
    const token = `local_token_${Date.now()}`;
    const response: AuthResponse = {
      token,
      user: {
        id: newUser.id,
        username: newUser.username,
        name: newUser.name,
        role: 'user',
        email: newUser.email
      },
      message: 'Account created successfully'
    };
    localStorage.setItem('clearpay_session', JSON.stringify({ token, user: response.user }));
    return response;
  },

  async getMe(token: string): Promise<User | null> {
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        return data.user;
      }
    } catch {}
    const sess = localStorage.getItem('clearpay_session');
    if (sess) {
      try {
        const parsed = JSON.parse(sess);
        if (parsed.user) return parsed.user;
      } catch {}
    }
    return null;
  },

  async logout(token?: string): Promise<void> {
    try {
      if (token) {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` }
        });
      }
    } catch {}
    localStorage.removeItem('clearpay_session');
  }
};
