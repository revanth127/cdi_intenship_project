import * as React from 'react';
import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import {
  formatIndianCurrency,
  formatIndianNumber,
  formatQuantityWithUnit,
} from '@/lib/format';
import { Plus, Trash2, CheckCircle2, ChevronDown, ChevronRight, RotateCcw } from 'lucide-react';

interface Supplier {
  id: number;
  name: string;
  gstin?: string;
  is_active: boolean;
}

interface Item {
  id: number;
  name: string;
  item_type: string;
  base_unit: string;
  display_unit: string;
  is_active: boolean;
}

interface PurchaseLineForm {
  item_id: number;
  quantity_entered: string;
  unit_entered: string;
  rate_rupees: string;
}

interface PurchaseLine {
  id: number;
  purchase_id: number;
  item_id: number;
  quantity_base: number;
  unit_entered: string;
  rate_paise: number;
  line_total_paise: number;
}

interface Purchase {
  id: number;
  purchase_no: string;
  supplier_id: number;
  supplier_invoice_no?: string;
  purchase_date: string;
  status: 'POSTED' | 'CANCELLED';
  total_paise: number;
  lines: PurchaseLine[];
}

export const PurchasesPage: React.FC = () => {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form State
  const [showForm, setShowForm] = useState(false);
  const [selectedSupplierId, setSelectedSupplierId] = useState<number | ''>('');
  const [invoiceNo, setInvoiceNo] = useState('');
  const [purchaseDate, setPurchaseDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [lines, setLines] = useState<PurchaseLineForm[]>([
    { item_id: 0, quantity_entered: '', unit_entered: 'kg', rate_rupees: '' },
  ]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [postSuccess, setPostSuccess] = useState<{
    purchaseNo: string;
    totalPaise: number;
    updatedItems: { name: string; balance: string }[];
  } | null>(null);

  // Expanded row tracking
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const fetchData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [suppliersData, itemsData, purchasesData] = await Promise.all([
        apiClient.get<Supplier[]>('/suppliers'),
        apiClient.get<Item[]>('/items'),
        apiClient.get<Purchase[]>('/purchases'),
      ]);
      setSuppliers(suppliersData.filter((s) => s.is_active));
      setItems(itemsData.filter((i) => i.is_active));
      setPurchases(purchasesData);
    } catch (err: any) {
      setError(err?.message || 'Failed to load purchase records.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleItemChange = (index: number, itemId: number) => {
    const selectedItem = items.find((i) => i.id === itemId);
    const updated = [...lines];
    updated[index].item_id = itemId;
    if (selectedItem) {
      updated[index].unit_entered = selectedItem.display_unit || selectedItem.base_unit;
    }
    setLines(updated);
  };

  const handleLineChange = (index: number, field: keyof PurchaseLineForm, value: string) => {
    const updated = [...lines];
    updated[index] = { ...updated[index], [field]: value };
    setLines(updated);
  };

  const addLine = () => {
    setLines([...lines, { item_id: 0, quantity_entered: '', unit_entered: 'kg', rate_rupees: '' }]);
  };

  const removeLine = (index: number) => {
    if (lines.length > 1) {
      setLines(lines.filter((_, i) => i !== index));
    }
  };

  const calculateTotalPaise = () => {
    return lines.reduce((sum, line) => {
      const qty = parseFloat(line.quantity_entered) || 0;
      const rate = parseFloat(line.rate_rupees) || 0;
      return sum + Math.round(qty * rate * 100);
    }, 0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSupplierId) {
      setSubmitError('Please select a supplier.');
      return;
    }

    const validLines = lines.filter((l) => l.item_id > 0 && parseFloat(l.quantity_entered) > 0);
    if (validLines.length === 0) {
      setSubmitError('Please add at least one line with a valid item and quantity.');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const payload = {
        supplier_id: Number(selectedSupplierId),
        supplier_invoice_no: invoiceNo.trim() || undefined,
        purchase_date: new Date(purchaseDate).toISOString(),
        lines: validLines.map((l) => ({
          item_id: l.item_id,
          quantity_entered: parseFloat(l.quantity_entered),
          unit_entered: l.unit_entered,
          rate_paise: Math.round((parseFloat(l.rate_rupees) || 0) * 100),
        })),
      };

      const res = await apiClient.post<Purchase>('/purchases', payload);

      // Fetch updated stock balance for the purchased items
      let updatedItems: { name: string; balance: string }[] = [];
      try {
        const stockSummary = await apiClient.get<any[]>('/stock/summary');
        updatedItems = validLines.map((l) => {
          const itemMeta = items.find((it) => it.id === l.item_id);
          const stockEntry = stockSummary.find((s) => s.item_id === l.item_id);
          return {
            name: itemMeta?.name || `Item ${l.item_id}`,
            balance: stockEntry ? stockEntry.closing_balance_display : 'Updated',
          };
        });
      } catch {
        // Fallback if summary fetch fails
      }

      setPostSuccess({
        purchaseNo: res.purchase_no,
        totalPaise: res.total_paise,
        updatedItems,
      });

      // Reset form
      setShowForm(false);
      setSelectedSupplierId('');
      setInvoiceNo('');
      setLines([{ item_id: 0, quantity_entered: '', unit_entered: 'kg', rate_rupees: '' }]);

      // Refetch purchases list
      const updatedPurchases = await apiClient.get<Purchase[]>('/purchases');
      setPurchases(updatedPurchases);
    } catch (err: any) {
      setSubmitError(err?.message || 'Failed to record purchase receipt.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSupplierName = (supplierId: number) => {
    return suppliers.find((s) => s.id === supplierId)?.name || `Supplier #${supplierId}`;
  };

  const getItemName = (itemId: number) => {
    return items.find((i) => i.id === itemId)?.name || `Item #${itemId}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Purchases</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Record supplier goods receipts and immediately update raw material and packaging stock.
          </p>
        </div>
        <Button
          onClick={() => {
            setShowForm(!showForm);
            setPostSuccess(null);
          }}
          className="gap-1.5 h-8 text-xs"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{showForm ? 'Close Form' : 'New Purchase Receipt'}</span>
        </Button>
      </div>

      {/* Success Banner */}
      {postSuccess && (
        <div className="p-4 rounded-[6px] bg-emerald-50 border border-emerald-200 text-emerald-900 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" />
            <span className="text-sm font-semibold">
              Purchase {postSuccess.purchaseNo} posted successfully! Total: {formatIndianCurrency(postSuccess.totalPaise / 100)}
            </span>
          </div>
          {postSuccess.updatedItems.length > 0 && (
            <div className="mt-1 pl-7">
              <span className="text-xs font-semibold text-emerald-800">Updated Stock Balances:</span>
              <ul className="mt-1 space-y-0.5 text-xs text-emerald-700">
                {postSuccess.updatedItems.map((ui, idx) => (
                  <li key={idx}>
                    • {ui.name}: <span className="font-semibold">{ui.balance}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* New Purchase Form */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-surface border border-border rounded-[6px] p-5 space-y-5"
          data-testid="purchase-form"
        >
          <div className="border-b border-border pb-3">
            <h2 className="text-sm font-semibold text-text-primary">Record Goods Receipt</h2>
            <p className="text-xs text-text-secondary">
              Values entered immediately write immutable rows into the stock ledger with weighted average cost updates.
            </p>
          </div>

          {submitError && <InlineError message={submitError} />}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1">
                Supplier <span className="text-red-500">*</span>
              </label>
              <select
                value={selectedSupplierId}
                onChange={(e) => setSelectedSupplierId(e.target.value ? Number(e.target.value) : '')}
                required
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] focus:outline-none focus:border-accent"
              >
                <option value="">Select Supplier</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} {s.gstin ? `(${s.gstin})` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1">
                Supplier Invoice No
              </label>
              <input
                type="text"
                value={invoiceNo}
                onChange={(e) => setInvoiceNo(e.target.value)}
                placeholder="e.g. INV-9842"
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] focus:outline-none focus:border-accent"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1">
                Receipt Date <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
                required
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          {/* Line items table */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-text-primary">Items Received</span>
              <Button type="button" variant="secondary" size="sm" onClick={addLine} className="h-7 text-xs gap-1">
                <Plus className="w-3 h-3" />
                <span>Add Item</span>
              </Button>
            </div>

            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2 pr-3">Item</th>
                    <th className="py-2 px-3 w-28">Quantity</th>
                    <th className="py-2 px-3 w-24">Unit</th>
                    <th className="py-2 px-3 w-28">Rate (₹)</th>
                    <th className="py-2 pl-3 text-right w-32">Total (₹)</th>
                    <th className="py-2 pl-2 w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {lines.map((line, idx) => {
                    const lineTotal =
                      (parseFloat(line.quantity_entered) || 0) * (parseFloat(line.rate_rupees) || 0);
                    return (
                      <tr key={idx}>
                        <td className="py-2 pr-3">
                          <select
                            value={line.item_id}
                            onChange={(e) => handleItemChange(idx, Number(e.target.value))}
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                          >
                            <option value={0}>Select Item</option>
                            {items.map((it) => (
                              <option key={it.id} value={it.id}>
                                {it.name} ({it.item_type})
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-3">
                          <input
                            type="number"
                            step="any"
                            min="0.001"
                            value={line.quantity_entered}
                            onChange={(e) => handleLineChange(idx, 'quantity_entered', e.target.value)}
                            placeholder="0"
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] text-right"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <input
                            type="text"
                            value={line.unit_entered}
                            onChange={(e) => handleLineChange(idx, 'unit_entered', e.target.value)}
                            placeholder="kg"
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={line.rate_rupees}
                            onChange={(e) => handleLineChange(idx, 'rate_rupees', e.target.value)}
                            placeholder="0.00"
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] text-right"
                          />
                        </td>
                        <td className="py-2 pl-3 text-right font-medium tabular-nums">
                          {formatIndianCurrency(lineTotal)}
                        </td>
                        <td className="py-2 pl-2 text-center">
                          {lines.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeLine(idx)}
                              className="text-text-muted hover:text-red-600 p-1 rounded"
                              title="Remove item"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex justify-end items-center gap-4 mt-3 pt-3 border-t border-border">
              <span className="text-xs font-semibold text-text-secondary">Estimated Total:</span>
              <span className="text-sm font-semibold text-text-primary tabular-nums">
                {formatIndianCurrency(calculateTotalPaise() / 100)}
              </span>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setShowForm(false)}
              className="text-xs h-8"
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting} className="text-xs h-8 gap-1.5">
              {isSubmitting ? (
                <>
                  <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                  <span>Posting Receipt...</span>
                </>
              ) : (
                <span>Post Purchase Receipt</span>
              )}
            </Button>
          </div>
        </form>
      )}

      {/* Purchases List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-text-primary">Recent Purchase Receipts</h2>
          <span className="text-xs text-text-muted">{purchases.length} records</span>
        </div>

        {isLoading ? (
          <div className="divide-y divide-border border-y border-border py-4">
            <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
            <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
            <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
          </div>
        ) : error ? (
          <InlineError message={error} onRetry={fetchData} />
        ) : purchases.length === 0 ? (
          <EmptyState
            message="No purchase receipts recorded yet"
            description="Use 'New Purchase Receipt' to record supplier deliveries and bring stock into inventory."
            action={
              <Button size="sm" onClick={() => setShowForm(true)} className="text-xs">
                Record First Purchase
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto border-t border-border">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text-secondary text-left font-semibold">
                  <th className="py-2.5 pr-2 w-8"></th>
                  <th className="py-2.5 pr-3">Purchase No</th>
                  <th className="py-2.5 px-3">Supplier</th>
                  <th className="py-2.5 px-3">Invoice No</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Items</th>
                  <th className="py-2.5 px-3 text-right">Total (₹)</th>
                  <th className="py-2.5 pl-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {purchases.map((p) => {
                  const isExpanded = expandedId === p.id;
                  return (
                    <React.Fragment key={p.id}>
                      <tr
                        onClick={() => setExpandedId(isExpanded ? null : p.id)}
                        className="hover:bg-surface-subtle/60 cursor-pointer transition-colors"
                      >
                        <td className="py-2.5 pr-2 text-text-muted">
                          {isExpanded ? (
                            <ChevronDown className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronRight className="w-3.5 h-3.5" />
                          )}
                        </td>
                        <td className="py-2.5 pr-3 font-semibold text-accent">{p.purchase_no}</td>
                        <td className="py-2.5 px-3 font-medium text-text-primary">
                          {getSupplierName(p.supplier_id)}
                        </td>
                        <td className="py-2.5 px-3 text-text-secondary font-mono">
                          {p.supplier_invoice_no || '—'}
                        </td>
                        <td className="py-2.5 px-3 text-text-secondary">
                          {new Date(p.purchase_date).toLocaleDateString('en-IN', {
                            day: '2-digit',
                            month: 'short',
                            year: 'numeric',
                          })}
                        </td>
                        <td className="py-2.5 px-3 text-text-secondary">
                          {p.lines.length} {p.lines.length === 1 ? 'line' : 'lines'}
                        </td>
                        <td className="py-2.5 px-3 text-right font-semibold text-text-primary tabular-nums">
                          {formatIndianCurrency(p.total_paise / 100)}
                        </td>
                        <td className="py-2.5 pl-3 text-right">
                          <StatusChip
                            label={p.status}
                            status={p.status === 'POSTED' ? 'ok' : 'breach'}
                            size="sm"
                          />
                        </td>
                      </tr>

                      {/* Expanded Line Items Detail */}
                      {isExpanded && (
                        <tr className="bg-surface-subtle/40">
                          <td colSpan={8} className="py-3 px-6">
                            <div className="space-y-1.5">
                              <span className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider">
                                Received Items Detail
                              </span>
                              <div className="overflow-x-auto">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b border-border/60 text-text-muted text-left font-medium">
                                      <th className="py-1 pr-3">Item</th>
                                      <th className="py-1 px-3 text-right">Quantity (Base)</th>
                                      <th className="py-1 px-3">Unit</th>
                                      <th className="py-1 px-3 text-right">Rate (₹)</th>
                                      <th className="py-1 pl-3 text-right">Line Total (₹)</th>
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-border/40">
                                    {p.lines.map((l) => (
                                      <tr key={l.id}>
                                        <td className="py-1.5 pr-3 font-medium text-text-primary">
                                          {getItemName(l.item_id)}
                                        </td>
                                        <td className="py-1.5 px-3 text-right tabular-nums text-text-secondary">
                                          {formatIndianNumber(l.quantity_base)}
                                        </td>
                                        <td className="py-1.5 px-3 text-text-muted">{l.unit_entered}</td>
                                        <td className="py-1.5 px-3 text-right tabular-nums text-text-secondary">
                                          {formatIndianCurrency(l.rate_paise / 100)}
                                        </td>
                                        <td className="py-1.5 pl-3 text-right tabular-nums font-semibold text-text-primary">
                                          {formatIndianCurrency(l.line_total_paise / 100)}
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
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
