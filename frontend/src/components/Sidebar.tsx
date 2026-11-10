import React from 'react';
import {
  LayoutDashboard,
  FileText,
  Building2,
  Package,
  Settings,
  LogOut,
  X,
  Sparkles
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { AIStatus } from '../types';

export type NavSection = 'DASHBOARD' | 'INVOICES' | 'VENDORS' | 'PURCHASE_ORDERS' | 'SETTINGS';

interface SidebarProps {
  currentSection: NavSection;
  onSelectSection: (section: NavSection) => void;
  isOpenMobile: boolean;
  onCloseMobile: () => void;
  aiStatus: AIStatus | null;
  invoicesCount?: number;
  vendorsCount?: number;
  posCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentSection,
  onSelectSection,
  isOpenMobile,
  onCloseMobile,
  aiStatus,
  invoicesCount,
  vendorsCount,
  posCount
}) => {
  const { user, logout } = useAuth();

  const navItems = [
    {
      id: 'DASHBOARD' as NavSection,
      label: 'Dashboard',
      icon: LayoutDashboard
    },
    {
      id: 'INVOICES' as NavSection,
      label: 'Invoices',
      icon: FileText,
      count: invoicesCount
    },
    {
      id: 'VENDORS' as NavSection,
      label: 'Vendors',
      icon: Building2,
      count: vendorsCount
    },
    {
      id: 'PURCHASE_ORDERS' as NavSection,
      label: 'Purchase orders',
      icon: Package,
      count: posCount
    },
    {
      id: 'SETTINGS' as NavSection,
      label: 'Settings',
      icon: Settings
    }
  ];

  const isAiOn = aiStatus?.enabled ?? true;

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpenMobile && (
        <div
          className="fixed inset-0 z-40 bg-black/30 backdrop-blur-xs md:hidden"
          onClick={onCloseMobile}
        />
      )}

      {/* Main Sidebar */}
      <aside
        className={`fixed md:sticky top-0 left-0 z-50 h-screen w-64 bg-white border-r border-neutral-200/80 flex flex-col transition-transform duration-200 ease-in-out md:translate-x-0 ${
          isOpenMobile ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="h-16 px-6 flex items-center justify-between border-b border-neutral-100">
          <div className="flex items-center gap-2.5">
            {/* Zamp Geometric Mark */}
            <svg
              width="24"
              height="20"
              viewBox="0 0 28 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              className="text-neutral-900 shrink-0"
            >
              <polygon points="6,2 26,2 21,10 1,10" fill="currentColor" />
              <polygon points="5,13 25,13 20,21 0,21" fill="currentColor" />
            </svg>
            <div className="flex items-baseline gap-1.5">
              <span className="text-xl font-semibold tracking-tight text-neutral-900 leading-none">
                zamp
              </span>
              <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400 font-medium">
                AP
              </span>
            </div>
          </div>

          <button
            onClick={onCloseMobile}
            className="md:hidden p-1.5 text-neutral-400 hover:text-neutral-900 rounded-lg hover:bg-neutral-100 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Navigation List */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  onSelectSection(item.id);
                  onCloseMobile();
                }}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition-all cursor-pointer group ${
                  isActive
                    ? 'bg-neutral-900 text-white shadow-xs'
                    : 'text-neutral-600 hover:bg-neutral-100/80 hover:text-neutral-900'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon
                    className={`h-4 w-4 transition-colors ${
                      isActive ? 'text-white' : 'text-neutral-400 group-hover:text-neutral-600'
                    }`}
                    strokeWidth={isActive ? 2 : 1.75}
                  />
                  <span>{item.label}</span>
                </div>

                {item.count !== undefined && item.count > 0 && (
                  <span
                    className={`text-[11px] font-mono px-2 py-0.5 rounded-full font-medium transition-colors ${
                      isActive
                        ? 'bg-white/20 text-white'
                        : 'bg-neutral-100 text-neutral-500 group-hover:bg-neutral-200/70'
                    }`}
                  >
                    {item.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Bottom Section: AI Status & User Capsule */}
        <div className="p-3 border-t border-neutral-100 space-y-2">
          {/* AI Status Dot */}
          <button
            onClick={() => {
              onSelectSection('SETTINGS');
              onCloseMobile();
            }}
            className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs bg-neutral-50 hover:bg-neutral-100/80 text-neutral-600 transition-colors cursor-pointer"
            title="Configure AI reasoning in Settings"
          >
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full transition-colors ${
                  isAiOn ? 'bg-emerald-500 ring-2 ring-emerald-500/20' : 'bg-neutral-400'
                }`}
              />
              <span className="font-medium text-neutral-700">
                {isAiOn ? 'AI review on' : 'AI review off'}
              </span>
            </div>
            <Sparkles className="h-3.5 w-3.5 text-neutral-400" />
          </button>

          {/* User Account Capsule */}
          <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-white border border-neutral-200/70 text-xs">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="h-6 w-6 rounded-full bg-neutral-900 text-white flex items-center justify-center font-semibold text-[10px] shrink-0">
                {user?.username ? user.username.charAt(0).toUpperCase() : 'U'}
              </div>
              <div className="min-w-0">
                <p className="font-medium text-neutral-800 truncate leading-tight">
                  {user?.name || user?.username || 'AP Team'}
                </p>
                <p className="text-[10px] font-mono text-neutral-400 truncate">
                  {user?.email || 'ap@company.com'}
                </p>
              </div>
            </div>

            <button
              onClick={logout}
              className="text-neutral-400 hover:text-rose-600 p-1 rounded-lg hover:bg-neutral-100 transition-colors cursor-pointer"
              title="Sign out"
            >
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </aside>
    </>
  );
};
