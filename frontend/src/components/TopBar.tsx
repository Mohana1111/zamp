import React, { useState } from 'react';
import { Menu, Mail, Loader2 } from 'lucide-react';
import { NavSection } from './Sidebar';

interface TopBarProps {
  currentSection: NavSection;
  onOpenMobileSidebar: () => void;
  onImportEmail: () => Promise<void>;
}

export const TopBar: React.FC<TopBarProps> = ({
  currentSection,
  onOpenMobileSidebar,
  onImportEmail
}) => {
  const [isImporting, setIsImporting] = useState(false);

  const titles: Record<NavSection, { title: string; subtitle: string }> = {
    DASHBOARD: {
      title: 'Dashboard',
      subtitle: 'Overview of accounts payable activity, performance, and audit trends'
    },
    INVOICES: {
      title: 'Invoices',
      subtitle: 'Review, verify, and approve incoming supplier invoices'
    },
    VENDORS: {
      title: 'Vendors',
      subtitle: 'Manage supplier profiles, trust levels, and auto-approval limits'
    },
    PURCHASE_ORDERS: {
      title: 'Purchase orders',
      subtitle: 'Track purchase order balances, line items, and billed amounts'
    },
    SETTINGS: {
      title: 'Settings',
      subtitle: 'Configure tolerances, policy rules, and AI reasoning'
    }
  };

  const current = titles[currentSection];

  const handleImport = async () => {
    setIsImporting(true);
    try {
      await onImportEmail();
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <header className="sticky top-0 z-30 bg-white/95 backdrop-blur-md border-b border-neutral-200/80 px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobileSidebar}
          className="md:hidden p-1.5 text-neutral-500 hover:text-neutral-900 rounded-lg hover:bg-neutral-100 transition-colors"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div>
          <h1 className="text-base font-semibold text-neutral-900 tracking-tight leading-none">
            {current.title}
          </h1>
          <p className="text-xs text-neutral-400 hidden sm:block mt-0.5">
            {current.subtitle}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {/* Compact "Import from email" button */}
        <button
          onClick={handleImport}
          disabled={isImporting}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-neutral-200 bg-white hover:bg-neutral-50 text-neutral-700 text-xs font-medium shadow-2xs hover:border-neutral-300 transition-all disabled:opacity-50 cursor-pointer"
          title="Check for new invoices sent via email"
        >
          {isImporting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-neutral-600" />
          ) : (
            <Mail className="h-3.5 w-3.5 text-neutral-500" />
          )}
          <span>{isImporting ? 'Checking email...' : 'Import from email'}</span>
        </button>
      </div>
    </header>
  );
};
