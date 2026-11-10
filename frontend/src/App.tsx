import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar, NavSection } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { DashboardPage } from './components/DashboardPage';
import { InvoicesPage } from './components/InvoicesPage';
import { InvoiceDetailDrawer } from './components/InvoiceDetailDrawer';
import { VendorsPage } from './components/VendorsPage';
import { PurchaseOrdersPage } from './components/PurchaseOrdersPage';
import { SettingsPage } from './components/SettingsPage';
import { AuthView } from './components/AuthView';
import { ToastContainer, ToastMessage } from './components/Toast';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AuthProvider, useAuth } from './context/AuthContext';
import { api } from './services/api';
import {
  InvoiceRunResult,
  PurchaseOrder,
  VendorMaster,
  SystemSettings,
  AIStatus,
  DashboardData
} from './types';
import { Loader2 } from 'lucide-react';

function MainApp() {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();

  // Navigation State - Dashboard is first!
  const [currentSection, setCurrentSection] = useState<NavSection>('DASHBOARD');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  // Core Data State
  const [runs, setRuns] = useState<InvoiceRunResult[]>([]);
  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [vendors, setVendors] = useState<VendorMaster[]>([]);
  const [pos, setPos] = useState<PurchaseOrder[]>([]);
  const [settings, setSettings] = useState<SystemSettings>({
    default_price_tolerance_pct: 2,
    default_total_tolerance_pct: 1,
    default_auto_approve_limit_inr: null,
    duplicate_window_days: 365,
    require_po_above_inr: 50000,
    ai_review_enabled: true,
    ai_min_confidence: 0.85
  });
  const [aiStatus, setAiStatus] = useState<AIStatus | null>({ enabled: true, mode: 'ai' });

  // Detail Drawer State
  const [activeRun, setActiveRun] = useState<InvoiceRunResult | null>(null);

  // Loading States
  const [isLoadingData, setIsLoadingData] = useState(true);
  const [isRunningSample, setIsRunningSample] = useState(false);

  // Toast System
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const showToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'success') => {
    const id = `${Date.now()}-${Math.random()}`;
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Fetch all initial data
  const loadAllData = useCallback(async () => {
    try {
      const [dashData, runsData, vendorsData, posData, settingsData, aiStatusData] = await Promise.all([
        api.getDashboard().catch(() => null),
        api.getRuns().catch(() => []),
        api.getVendors().catch(() => []),
        api.getPurchaseOrders().catch(() => []),
        api.getSettings().catch(() => null),
        api.getAIStatus().catch(() => null)
      ]);

      if (dashData) {
        setDashboardData(dashData);
      }
      if (runsData && runsData.length > 0) {
        setRuns(runsData);
      }
      if (vendorsData) {
        setVendors(vendorsData);
      }
      if (posData) {
        setPos(posData);
      }
      if (settingsData) {
        setSettings(settingsData);
      }
      if (aiStatusData) {
        setAiStatus(aiStatusData);
      }
    } finally {
      setIsLoadingData(false);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadAllData();
    }
  }, [isAuthenticated, loadAllData]);

  // Periodic subtle polling for runs & dashboard
  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(async () => {
      try {
        const freshRuns = await api.getRuns();
        if (freshRuns && freshRuns.length > 0) {
          setRuns((prev) => {
            if (freshRuns.length !== prev.length || freshRuns[0]?.run_id !== prev[0]?.run_id) {
              api.getDashboard().then(setDashboardData).catch(() => {});
              return freshRuns;
            }
            return prev;
          });
        }
      } catch {
        // Quiet
      }
    }, 6000);

    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // Handle runs updated from uploads/streaming
  const handleRunsUpdated = useCallback((newRuns: InvoiceRunResult[]) => {
    setRuns((prev) => {
      const merged = [...newRuns, ...prev.filter((r) => !newRuns.some((nr) => nr.run_id === r.run_id))];
      return merged;
    });
    // Refresh dashboard, vendors, and POs
    api.getDashboard().then(setDashboardData).catch(() => {});
    api.getVendors().then(setVendors).catch(() => {});
    api.getPurchaseOrders().then(setPos).catch(() => {});
  }, []);

  // Handle sample invoice execution
  const handleRunSample = async () => {
    setIsRunningSample(true);
    try {
      const sampleRun = await api.runSample('01_happy_shree_ganesh_inr.pdf');
      if (sampleRun) {
        handleRunsUpdated([sampleRun]);
        setActiveRun(sampleRun);
        showToast(`Sample invoice processed: ${sampleRun.matched_vendor_name || 'Shree Ganesh Packaging'}`);
      } else {
        showToast('Sample invoice processed.', 'info');
      }
    } catch {
      showToast('Error running sample invoice.', 'error');
    } finally {
      setIsRunningSample(false);
    }
  };

  // Handle invoice approval or rejection
  const handleApproveInvoice = async (
    runId: string,
    action: 'APPROVE' | 'REJECT',
    comment?: string,
    preapproveVendor: boolean = false
  ) => {
    try {
      let updated: InvoiceRunResult | null = null;
      if (preapproveVendor) {
        updated = await api.overrideDecision(runId, 'AUTO_APPROVE', comment || 'Approved & vendor pre-approved', 'AP Lead', true);
      } else {
        updated = await api.approveRun(runId, 'AP Lead', action, comment);
      }

      if (updated) {
        setRuns((prev) => prev.map((r) => (r.run_id === runId ? updated! : r)));
        setActiveRun(updated);
        showToast(
          action === 'APPROVE'
            ? preapproveVendor
              ? 'Invoice approved and vendor added to Pre-approved policy.'
              : 'Invoice approved successfully.'
            : 'Invoice rejected.'
        );
        api.getDashboard().then(setDashboardData).catch(() => {});
        api.getVendors().then(setVendors).catch(() => {});
      }
    } catch {
      showToast('Error recording decision.', 'error');
    }
  };

  // Handle invoice delete
  const handleDeleteInvoice = async (runId: string) => {
    try {
      await api.deleteRun(runId);
      setRuns((prev) => prev.filter((r) => r.run_id !== runId));
      if (activeRun?.run_id === runId) setActiveRun(null);
      api.getDashboard().then(setDashboardData).catch(() => {});
      showToast('Invoice removed.');
    } catch {
      showToast('Failed to delete invoice.', 'error');
    }
  };

  // Handle Import from email
  const handleImportFromEmail = async () => {
    try {
      const res = await api.syncAgentInboxNow();
      if (res.runs && res.runs.length > 0) {
        handleRunsUpdated(res.runs);
        showToast(`Imported ${res.runs.length} new invoice(s) from email.`);
      } else {
        showToast(res.message || 'No new invoice emails found.', 'info');
      }
    } catch {
      showToast('Failed to sync email inbox.', 'error');
    }
  };

  // Vendor actions
  const handleUpdateVendor = async (vendorId: string, data: Partial<VendorMaster>) => {
    try {
      const updated = await api.updateVendor(vendorId, data);
      setVendors((prev) => prev.map((v) => (v.vendor_id === vendorId ? updated : v)));
      showToast('Vendor details saved.');
    } catch {
      showToast('Failed to update vendor.', 'error');
    }
  };

  const handleUpdateVendorPolicy = async (vendorId: string, policy: any) => {
    try {
      const updated = await api.updateVendorPolicy(vendorId, policy);
      setVendors((prev) => prev.map((v) => (v.vendor_id === vendorId ? updated : v)));
      showToast('Vendor policy updated.');
    } catch {
      showToast('Failed to update policy.', 'error');
    }
  };

  const handleCreateVendor = async (vendorData: Partial<VendorMaster>) => {
    try {
      const created = await api.createVendor(vendorData);
      setVendors((prev) => [created, ...prev.filter((v) => v.vendor_id !== created.vendor_id)]);
      showToast(`Vendor ${created.legal_name} registered successfully.`);
    } catch (err: any) {
      showToast(err.message || 'Failed to create vendor.', 'error');
      throw err;
    }
  };

  const handleDeleteVendor = async (vendorId: string) => {
    try {
      await api.deleteVendor(vendorId);
      setVendors((prev) => prev.filter((v) => v.vendor_id !== vendorId));
      showToast('Vendor removed.');
    } catch {
      showToast('Failed to delete vendor.', 'error');
    }
  };

  // Settings actions
  const handleSaveSettings = async (updated: Partial<SystemSettings>) => {
    try {
      const saved = await api.updateSettings(updated);
      setSettings(saved);
      const ai = await api.getAIStatus();
      setAiStatus(ai);
      showToast('Settings saved successfully.');
    } catch {
      showToast('Failed to save settings.', 'error');
    }
  };

  const handleResetData = async () => {
    try {
      await api.resetData();
      setRuns([]);
      setActiveRun(null);
      api.getDashboard().then(setDashboardData).catch(() => {});
      showToast('System state reset to clean initial state.');
    } catch {
      showToast('Failed to reset state.', 'error');
    }
  };

  // Authentication Loading Screen
  if (isAuthLoading) {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center space-y-3 font-sans text-xs text-neutral-500">
        <Loader2 className="h-5 w-5 animate-spin text-neutral-900" />
        <span>Authenticating session...</span>
      </div>
    );
  }

  // Not authenticated
  if (!isAuthenticated) {
    return <AuthView />;
  }

  return (
    <div className="min-h-screen bg-neutral-50/40 text-neutral-900 flex font-sans selection:bg-neutral-900 selection:text-white">
      {/* Toast Notification Stack */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* Left Navigation Sidebar */}
      <Sidebar
        currentSection={currentSection}
        onSelectSection={(section) => setCurrentSection(section)}
        isOpenMobile={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
        aiStatus={aiStatus}
        invoicesCount={runs.length}
        vendorsCount={vendors.length}
        posCount={pos.length}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Header Bar */}
        <TopBar
          currentSection={currentSection}
          onOpenMobileSidebar={() => setIsMobileSidebarOpen(true)}
          onImportEmail={handleImportFromEmail}
        />

        {/* Page Content Body */}
        <main className="flex-1 p-6 lg:p-8 max-w-7xl w-full mx-auto">
          {currentSection === 'DASHBOARD' && (
            <DashboardPage
              data={dashboardData}
              recentRuns={runs}
              isLoading={isLoadingData}
              onSelectRun={(run) => setActiveRun(run)}
              onNavigateToInvoices={() => setCurrentSection('INVOICES')}
              onRunSample={handleRunSample}
              isRunningSample={isRunningSample}
            />
          )}

          {currentSection === 'INVOICES' && (
            <InvoicesPage
              runs={runs}
              isLoading={isLoadingData}
              onSelectRun={(run) => setActiveRun(run)}
              onRunsUpdated={handleRunsUpdated}
            />
          )}

          {currentSection === 'VENDORS' && (
            <VendorsPage
              vendors={vendors}
              isLoading={isLoadingData}
              onUpdateVendor={handleUpdateVendor}
              onUpdatePolicy={handleUpdateVendorPolicy}
              onCreateVendor={handleCreateVendor}
              onDeleteVendor={handleDeleteVendor}
            />
          )}

          {currentSection === 'PURCHASE_ORDERS' && (
            <PurchaseOrdersPage
              pos={pos}
              runs={runs}
              isLoading={isLoadingData}
              onSelectRun={(run) => {
                setActiveRun(run);
                setCurrentSection('INVOICES');
              }}
            />
          )}

          {currentSection === 'SETTINGS' && (
            <SettingsPage
              settings={settings}
              onSaveSettings={handleSaveSettings}
              onResetData={handleResetData}
            />
          )}
        </main>
      </div>

      {/* Right-Side Wide Drawer for Active Invoice */}
      <InvoiceDetailDrawer
        run={activeRun}
        onClose={() => setActiveRun(null)}
        onApprove={handleApproveInvoice}
        onDelete={handleDeleteInvoice}
      />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <MainApp />
      </AuthProvider>
    </ErrorBoundary>
  );
}
