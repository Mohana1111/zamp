import React, { useState, useMemo } from 'react';
import {
  Search,
  Plus,
  Building2,
  X,
  Check,
  ShieldCheck,
  AlertTriangle,
  Ban,
  Shield,
  Trash2,
  Loader2,
  ExternalLink
} from 'lucide-react';
import { VendorMaster, VendorTrustLevel } from '../types';
import { formatCurrency, formatDate, getTrustBadge } from '../utils/formatters';
import { TableSkeleton } from './Skeletons';

interface VendorsPageProps {
  vendors: VendorMaster[];
  isLoading: boolean;
  onUpdateVendor: (vendorId: string, data: Partial<VendorMaster>) => Promise<void>;
  onUpdatePolicy: (vendorId: string, policy: any) => Promise<void>;
  onCreateVendor: (vendor: Partial<VendorMaster>) => Promise<void>;
  onDeleteVendor: (vendorId: string) => Promise<void>;
}

export const VendorsPage: React.FC<VendorsPageProps> = ({
  vendors,
  isLoading,
  onUpdateVendor,
  onUpdatePolicy,
  onCreateVendor,
  onDeleteVendor
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedVendor, setSelectedVendor] = useState<VendorMaster | null>(null);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Edit form state for side panel
  const [editForm, setEditForm] = useState<Partial<VendorMaster>>({});

  // When a vendor is selected, populate edit form
  const handleSelectVendor = (vendor: VendorMaster) => {
    setSelectedVendor(vendor);
    setEditForm({
      legal_name: vendor.legal_name,
      aliases: vendor.aliases,
      country: vendor.country,
      tax_id: vendor.tax_id,
      default_currency: vendor.default_currency || 'INR',
      bank_account: vendor.bank_account,
      bank_code: vendor.bank_code,
      payment_terms: vendor.payment_terms || 'NET30',
      status: vendor.status || 'ACTIVE',
      trust: vendor.trust || vendor.policy?.trust || 'STANDARD',
      auto_approve_limit: vendor.auto_approve_limit ?? vendor.policy?.auto_approve_limit ?? null,
      price_tolerance_pct: vendor.price_tolerance_pct ?? vendor.policy?.price_tolerance_pct ?? 2,
      total_tolerance_pct: vendor.total_tolerance_pct ?? vendor.policy?.total_tolerance_pct ?? 1,
      allow_without_po: vendor.allow_without_po ?? vendor.policy?.allow_without_po ?? false,
      notes: vendor.notes || vendor.policy?.notes || ''
    });
  };

  // Filter vendors
  const filteredVendors = useMemo(() => {
    if (!searchQuery.trim()) return vendors;
    const q = searchQuery.toLowerCase();
    return vendors.filter((v) =>
      v.legal_name.toLowerCase().includes(q) ||
      (v.aliases && v.aliases.toLowerCase().includes(q)) ||
      (v.tax_id && v.tax_id.toLowerCase().includes(q)) ||
      v.vendor_id.toLowerCase().includes(q)
    );
  }, [vendors, searchQuery]);

  const handleSavePolicyAndMaster = async () => {
    if (!selectedVendor) return;
    setIsSaving(true);
    try {
      // Update master & policy
      await onUpdateVendor(selectedVendor.vendor_id, editForm);
      await onUpdatePolicy(selectedVendor.vendor_id, {
        trust: editForm.trust,
        auto_approve_limit: editForm.auto_approve_limit,
        price_tolerance_pct: editForm.price_tolerance_pct,
        total_tolerance_pct: editForm.total_tolerance_pct,
        allow_without_po: editForm.allow_without_po,
        notes: editForm.notes
      });
      setSelectedVendor(null);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!selectedVendor) return;
    if (confirm(`Are you sure you want to delete vendor "${selectedVendor.legal_name}"?`)) {
      setIsSaving(true);
      try {
        await onDeleteVendor(selectedVendor.vendor_id);
        setSelectedVendor(null);
      } finally {
        setIsSaving(false);
      }
    }
  };

  // Add Vendor Modal Form state
  const [newVendor, setNewVendor] = useState<Partial<VendorMaster>>({
    legal_name: '',
    aliases: '',
    country: 'IN',
    tax_id: '',
    default_currency: 'INR',
    bank_account: '',
    bank_code: '',
    payment_terms: 'NET30',
    trust: 'STANDARD',
    auto_approve_limit: null,
    price_tolerance_pct: 2,
    total_tolerance_pct: 1,
    allow_without_po: false,
    notes: ''
  });

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newVendor.legal_name?.trim()) return;
    setIsSaving(true);
    try {
      await onCreateVendor(newVendor);
      setIsAddModalOpen(false);
      setNewVendor({
        legal_name: '',
        aliases: '',
        country: 'IN',
        tax_id: '',
        default_currency: 'INR',
        bank_account: '',
        bank_code: '',
        payment_terms: 'NET30',
        trust: 'STANDARD',
        auto_approve_limit: null,
        price_tolerance_pct: 2,
        total_tolerance_pct: 1,
        allow_without_po: false,
        notes: ''
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Search */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-neutral-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search vendors by name, alias, tax ID..."
            className="w-full text-xs rounded-xl border border-neutral-200 bg-white pl-9 pr-3.5 py-2 text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900 transition-colors"
          />
        </div>

        <button
          onClick={() => setIsAddModalOpen(true)}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-neutral-900 hover:bg-black text-white text-xs font-medium shadow-xs transition-colors cursor-pointer shrink-0"
        >
          <Plus className="h-4 w-4" />
          <span>Add vendor</span>
        </button>
      </div>

      {/* Vendors Table */}
      <div className="rounded-2xl border border-neutral-200/90 bg-white overflow-hidden shadow-2xs">
        {isLoading ? (
          <TableSkeleton rows={5} />
        ) : filteredVendors.length === 0 ? (
          <div className="py-20 text-center space-y-3 px-4">
            <Building2 className="h-9 w-9 text-neutral-300 mx-auto" />
            <div className="space-y-1">
              <h3 className="text-sm font-semibold text-neutral-800">
                {vendors.length === 0 ? 'No vendors in database' : 'No matching vendors'}
              </h3>
              <p className="text-xs text-neutral-400 max-w-sm mx-auto">
                {vendors.length === 0
                  ? 'Add your first supplier or import existing vendor masters to configure approval rules.'
                  : 'Try searching with a different legal name or tax ID.'}
              </p>
            </div>
            {vendors.length === 0 && (
              <button
                onClick={() => setIsAddModalOpen(true)}
                className="mt-2 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-neutral-900 text-white text-xs font-medium hover:bg-black transition-colors cursor-pointer"
              >
                <Plus className="h-4 w-4" />
                <span>Add first vendor</span>
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-neutral-50/80 text-neutral-500 font-mono uppercase tracking-wider text-[11px] border-b border-neutral-200">
                <tr>
                  <th className="px-5 py-3 font-medium">Vendor</th>
                  <th className="px-4 py-3 font-medium">Tax ID</th>
                  <th className="px-4 py-3 font-medium">Country</th>
                  <th className="px-4 py-3 font-medium text-center">Trust Level</th>
                  <th className="px-4 py-3 font-medium text-right">Auto-Approve Limit</th>
                  <th className="px-4 py-3 font-medium text-center">Invoices</th>
                  <th className="px-5 py-3 font-medium text-right">Last Invoice</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100 font-sans">
                {filteredVendors.map((vendor) => {
                  const trust = vendor.trust || vendor.policy?.trust || 'STANDARD';
                  const badge = getTrustBadge(trust);
                  const limit = vendor.auto_approve_limit ?? vendor.policy?.auto_approve_limit;
                  const currency = vendor.default_currency || 'INR';

                  return (
                    <tr
                      key={vendor.vendor_id}
                      onClick={() => handleSelectVendor(vendor)}
                      className="hover:bg-neutral-50/80 transition-colors cursor-pointer group"
                    >
                      <td className="px-5 py-3.5 max-w-[240px]">
                        <div className="font-medium text-neutral-900 truncate group-hover:text-black">
                          {vendor.legal_name}
                        </div>
                        {vendor.aliases && (
                          <div className="text-[11px] text-neutral-400 truncate font-mono">
                            aka {vendor.aliases}
                          </div>
                        )}
                      </td>

                      <td className="px-4 py-3.5 font-mono text-neutral-600">
                        {vendor.tax_id || '—'}
                      </td>

                      <td className="px-4 py-3.5 font-mono text-neutral-500 uppercase">
                        {vendor.country || 'IN'}
                      </td>

                      <td className="px-4 py-3.5 text-center">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${badge.className}`}
                        >
                          <span className={`h-1.5 w-1.5 rounded-full ${badge.dotClass}`} />
                          {badge.label}
                        </span>
                      </td>

                      <td className="px-4 py-3.5 text-right font-mono font-medium text-neutral-800">
                        {limit ? formatCurrency(limit, currency) : '—'}
                      </td>

                      <td className="px-4 py-3.5 text-center font-mono text-neutral-600">
                        {vendor.invoice_count ?? 0}
                      </td>

                      <td className="px-5 py-3.5 text-right font-mono text-neutral-400">
                        {formatDate(vendor.last_invoice_date)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit Vendor Master + Policy Side Panel (Drawer) */}
      {selectedVendor && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
            onClick={() => setSelectedVendor(null)}
          />

          <div className="fixed inset-y-0 right-0 max-w-xl w-full flex pl-6 sm:pl-10">
            <div className="w-full bg-white shadow-2xl flex flex-col border-l border-neutral-200 animate-in slide-in-from-right duration-200">
              {/* Header */}
              <div className="px-6 py-5 border-b border-neutral-200/80 flex items-start justify-between gap-4 bg-neutral-50/50">
                <div className="space-y-1">
                  <h3 className="text-lg font-semibold text-neutral-900 tracking-tight">
                    {selectedVendor.legal_name}
                  </h3>
                  <div className="text-xs font-mono text-neutral-400">
                    ID: {selectedVendor.vendor_id}
                  </div>
                </div>

                <button
                  onClick={() => setSelectedVendor(null)}
                  className="p-1.5 text-neutral-400 hover:text-neutral-900 rounded-lg hover:bg-neutral-100 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              {/* Form Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                {/* SECTION 1: POLICY CONTROLS */}
                <div className="space-y-4">
                  <h4 className="text-xs font-mono uppercase tracking-wider text-neutral-500 font-semibold">
                    Approval Policy
                  </h4>

                  {/* Trust Segmented Control */}
                  <div className="space-y-1.5">
                    <label className="block text-xs font-medium text-neutral-700">
                      Trust Tier
                    </label>
                    <div className="grid grid-cols-4 p-1 rounded-xl bg-neutral-100 border border-neutral-200 text-xs font-medium">
                      {(['PREAPPROVED', 'STANDARD', 'WATCHLIST', 'BLOCKED'] as VendorTrustLevel[]).map((level) => {
                        const isCurrent = (editForm.trust || 'STANDARD') === level;
                        const badge = getTrustBadge(level);
                        return (
                          <button
                            key={level}
                            type="button"
                            onClick={() => setEditForm({ ...editForm, trust: level })}
                            className={`py-2 rounded-lg transition-all cursor-pointer text-center truncate px-1 ${
                              isCurrent
                                ? 'bg-white text-neutral-900 shadow-xs font-semibold'
                                : 'text-neutral-500 hover:text-neutral-900'
                            }`}
                          >
                            {badge.label}
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-[11px] text-neutral-400 leading-tight">
                      Pre-approved vendors auto-approve within limit. Blocked vendors are immediately rejected.
                    </p>
                  </div>

                  {/* Auto-Approve Limit */}
                  <div className="space-y-1.5">
                    <label className="block text-xs font-medium text-neutral-700">
                      Auto-Approve Spending Limit ({editForm.default_currency || 'INR'})
                    </label>
                    <input
                      type="number"
                      value={editForm.auto_approve_limit ?? ''}
                      onChange={(e) =>
                        setEditForm({
                          ...editForm,
                          auto_approve_limit: e.target.value ? parseFloat(e.target.value) : null
                        })
                      }
                      placeholder="e.g. 50000 (leave blank for standard rules)"
                      className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                    />
                    <p className="text-[11px] text-neutral-400 leading-tight">
                      Maximum invoice total eligible for automatic approval without human sign-off.
                    </p>
                  </div>

                  {/* Price & Total Tolerance Grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-medium text-neutral-700">
                        Line Price Tolerance %
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={editForm.price_tolerance_pct ?? 2}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            price_tolerance_pct: e.target.value ? parseFloat(e.target.value) : 2
                          })
                        }
                        className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                      />
                      <p className="text-[11px] text-neutral-400 leading-tight">
                        Allowed line item unit price variance against PO.
                      </p>
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-xs font-medium text-neutral-700">
                        Total Amount Tolerance %
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={editForm.total_tolerance_pct ?? 1}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            total_tolerance_pct: e.target.value ? parseFloat(e.target.value) : 1
                          })
                        }
                        className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                      />
                      <p className="text-[11px] text-neutral-400 leading-tight">
                        Allowed total variance against purchase order sum.
                      </p>
                    </div>
                  </div>

                  {/* Allow without PO Toggle */}
                  <div className="flex items-center justify-between p-3 rounded-xl border border-neutral-200 bg-neutral-50/50">
                    <div className="space-y-0.5">
                      <label className="text-xs font-medium text-neutral-800">
                        Allow Without Purchase Order
                      </label>
                      <p className="text-[11px] text-neutral-400">
                        Permit recurring invoices (e.g. SaaS, rent, utilities) without an issued PO.
                      </p>
                    </div>
                    <input
                      type="checkbox"
                      checked={Boolean(editForm.allow_without_po)}
                      onChange={(e) => setEditForm({ ...editForm, allow_without_po: e.target.checked })}
                      className="h-4 w-4 rounded border-neutral-300 text-neutral-900 focus:ring-neutral-900 cursor-pointer"
                    />
                  </div>

                  {/* Notes */}
                  <div className="space-y-1.5">
                    <label className="block text-xs font-medium text-neutral-700">
                      Policy Notes & Controller Instructions
                    </label>
                    <textarea
                      rows={2}
                      value={editForm.notes || ''}
                      onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                      placeholder="e.g. Verified recurring SaaS subscription; authorized under Department Budget."
                      className="w-full text-xs rounded-xl border border-neutral-200 bg-white p-2.5 text-neutral-900 placeholder-neutral-400 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                    />
                    <p className="text-[11px] text-neutral-400 leading-tight">
                      Internal guidelines and instructions shown during AP review.
                    </p>
                  </div>
                </div>

                {/* SECTION 2: MASTER RECORD */}
                <div className="space-y-4 pt-4 border-t border-neutral-200">
                  <h4 className="text-xs font-mono uppercase tracking-wider text-neutral-500 font-semibold">
                    Master Record
                  </h4>

                  <div className="space-y-1.5">
                    <label className="block text-xs font-medium text-neutral-700">
                      Legal Name
                    </label>
                    <input
                      type="text"
                      value={editForm.legal_name || ''}
                      onChange={(e) => setEditForm({ ...editForm, legal_name: e.target.value })}
                      className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-xs font-medium text-neutral-700">
                      Aliases (Comma-separated)
                    </label>
                    <input
                      type="text"
                      value={editForm.aliases || ''}
                      onChange={(e) => setEditForm({ ...editForm, aliases: e.target.value })}
                      placeholder="e.g. Acme, Acme Corp, Acme India"
                      className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono text-[11px] focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-medium text-neutral-700">
                        Tax ID / GSTIN
                      </label>
                      <input
                        type="text"
                        value={editForm.tax_id || ''}
                        onChange={(e) => setEditForm({ ...editForm, tax_id: e.target.value })}
                        className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-xs font-medium text-neutral-700">
                        Country
                      </label>
                      <input
                        type="text"
                        value={editForm.country || 'IN'}
                        onChange={(e) => setEditForm({ ...editForm, country: e.target.value.toUpperCase() })}
                        className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono uppercase focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-medium text-neutral-700">
                        Bank Account Number
                      </label>
                      <input
                        type="text"
                        value={editForm.bank_account || ''}
                        onChange={(e) => setEditForm({ ...editForm, bank_account: e.target.value })}
                        className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-xs font-medium text-neutral-700">
                        Bank Code / IFSC / SWIFT
                      </label>
                      <input
                        type="text"
                        value={editForm.bank_code || ''}
                        onChange={(e) => setEditForm({ ...editForm, bank_code: e.target.value })}
                        className="w-full text-xs rounded-xl border border-neutral-200 bg-white px-3 py-2 text-neutral-900 font-mono focus:outline-hidden focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                      />
                    </div>
                  </div>
                </div>
              </div>

              {/* Drawer Bottom Actions */}
              <div className="p-4 border-t border-neutral-200/80 flex items-center justify-between gap-3 bg-neutral-50/50">
                <button
                  type="button"
                  onClick={handleDelete}
                  disabled={isSaving}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-rose-600 hover:text-rose-700 hover:bg-rose-50 rounded-xl transition-colors cursor-pointer"
                >
                  <Trash2 className="h-4 w-4" />
                  <span>Delete</span>
                </button>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setSelectedVendor(null)}
                    className="px-4 py-2 text-xs font-medium text-neutral-600 hover:text-neutral-900 rounded-xl hover:bg-neutral-100 transition-colors cursor-pointer"
                  >
                    Cancel
                  </button>

                  <button
                    type="button"
                    onClick={handleSavePolicyAndMaster}
                    disabled={isSaving}
                    className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium bg-neutral-900 text-white hover:bg-black rounded-xl transition-colors cursor-pointer disabled:opacity-50"
                  >
                    {isSaving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    <span>Save changes</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Vendor Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-xs"
            onClick={() => setIsAddModalOpen(false)}
          />

          <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-xl border border-neutral-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-6 py-4 border-b border-neutral-200/80 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-neutral-900">
                Register New Vendor
              </h3>
              <button
                onClick={() => setIsAddModalOpen(false)}
                className="text-neutral-400 hover:text-neutral-900 p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-neutral-700">
                  Legal Entity Name *
                </label>
                <input
                  type="text"
                  required
                  value={newVendor.legal_name || ''}
                  onChange={(e) => setNewVendor({ ...newVendor, legal_name: e.target.value })}
                  placeholder="e.g. Acme Technologies Private Limited"
                  className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 focus:outline-hidden focus:border-neutral-900"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-medium text-neutral-700">
                  Aliases (Comma-separated)
                </label>
                <input
                  type="text"
                  value={newVendor.aliases || ''}
                  onChange={(e) => setNewVendor({ ...newVendor, aliases: e.target.value })}
                  placeholder="e.g. Acme, Acme Tech"
                  className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono text-[11px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="block text-xs font-medium text-neutral-700">
                    Tax ID / GSTIN
                  </label>
                  <input
                    type="text"
                    value={newVendor.tax_id || ''}
                    onChange={(e) => setNewVendor({ ...newVendor, tax_id: e.target.value })}
                    className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-medium text-neutral-700">
                    Country
                  </label>
                  <input
                    type="text"
                    value={newVendor.country || 'IN'}
                    onChange={(e) => setNewVendor({ ...newVendor, country: e.target.value.toUpperCase() })}
                    className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono uppercase"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="block text-xs font-medium text-neutral-700">
                    Bank Account Number
                  </label>
                  <input
                    type="text"
                    value={newVendor.bank_account || ''}
                    onChange={(e) => setNewVendor({ ...newVendor, bank_account: e.target.value })}
                    className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-medium text-neutral-700">
                    Bank IFSC / SWIFT Code
                  </label>
                  <input
                    type="text"
                    value={newVendor.bank_code || ''}
                    onChange={(e) => setNewVendor({ ...newVendor, bank_code: e.target.value })}
                    className="w-full text-xs rounded-xl border border-neutral-200 px-3 py-2 text-neutral-900 font-mono"
                  />
                </div>
              </div>

              {/* Initial Trust Level */}
              <div className="space-y-1.5 pt-2 border-t border-neutral-100">
                <label className="block text-xs font-medium text-neutral-700">
                  Initial Trust Level
                </label>
                <div className="grid grid-cols-4 p-1 rounded-xl bg-neutral-100 border border-neutral-200 text-xs font-medium">
                  {(['PREAPPROVED', 'STANDARD', 'WATCHLIST', 'BLOCKED'] as VendorTrustLevel[]).map((level) => (
                    <button
                      key={level}
                      type="button"
                      onClick={() => setNewVendor({ ...newVendor, trust: level })}
                      className={`py-1.5 rounded-lg text-center cursor-pointer ${
                        newVendor.trust === level
                          ? 'bg-white text-neutral-900 shadow-xs font-semibold'
                          : 'text-neutral-500 hover:text-neutral-900'
                      }`}
                    >
                      {getTrustBadge(level).label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="pt-4 border-t border-neutral-200 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium text-neutral-600 hover:bg-neutral-100 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="px-4 py-2 text-xs font-medium bg-neutral-900 text-white hover:bg-black rounded-xl"
                >
                  {isSaving ? 'Registering...' : 'Register Vendor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
