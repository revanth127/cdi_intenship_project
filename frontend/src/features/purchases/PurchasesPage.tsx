import * as React from 'react';
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import {
  formatIndianCurrency,
  formatIndianDate,
  formatIndianDecimal,
  convertBaseQuantity,
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
  rate_rupees: string;
  unit_entered: string;
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

interface StockSummaryItem {
  item_id: number;
  base_unit: string;
  display_unit: string;
  closing_balance_base: number;
  closing_balance_display?: string;
}

const emptyLine = (): PurchaseLineForm => ({
  item_id: 0,
  quantity_entered: '',
  rate_rupees: '',
  unit_entered: '',
});

export const PurchasesPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [selectedSupplierId, setSelectedSupplierId] = useState<number | ''>('');
  const [invoiceNo, setInvoiceNo] = useState('');
  const [purchaseDate, setPurchaseDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [lines, setLines] = useState<PurchaseLineForm[]>([emptyLine()]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [postSuccess, setPostSuccess] = useState<{
    purchaseNo: string;
    totalPaise: number;
    updatedItems: { name: string; balance: string }[];
  } | null>(null);

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
      setItems(itemsData.filter((i) => i.is_active && i.item_type !== 'FINISHED_GOOD'));
      setPurchases(purchasesData);

      // Deep link from the stock ledger: /purchases?purchase=PO-...
      const deepLink = searchParams.get('purchase');
      if (deepLink) {
        const match = purchasesData.find(
          (p) => p.purchase_no === deepLink || String(p.id) === deepLink
        );
        if (match) setExpandedId(match.id);
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load purchase records.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const getItem = (itemId: number) => items.find((i) => i.id === itemId);

  const handleItemChange = (index: number, itemId: number) => {
    const item = items.find((it) => it.id === itemId);
    setLines((prev) =>
      prev.map((line, i) =>
        i === index
          ? { ...line, item_id: itemId, unit_entered: line.unit_entered || item?.display_unit || item?.base_unit || '' }
          : line
      )
    );
  };

  const handleLineChange = (
    index: number,
    field: keyof PurchaseLineForm,
    value: string
  ) => {
    setLines((prev) =>
      prev.map((line, i) => (i === index ? { ...line, [field]: value } : line))
    );
  };

  const addLine = () => setLines((prev) => [...prev, emptyLine()]);

  const removeLine = (index: number) => {
    setLines((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== index) : prev));
  };

  const calculateTotalPaise = () =>
    lines.reduce((sum, line) => {
      const qty = parseFloat(line.quantity_entered) || 0;
      const rate = parseFloat(line.rate_rupees) || 0;
      return sum + Math.round(qty * rate * 100);
    }, 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSupplierId) {
      setSubmitError('Select a supplier before posting the receipt.');
      return;
    }
    if (!purchaseDate) {
      setSubmitError('Enter the supplier receipt date.');
      return;
    }

    const validLines = lines.filter(
      (l) => l.item_id > 0 && parseFloat(l.quantity_entered) > 0 && parseFloat(l.rate_rupees) >= 0
    );
    if (validLines.length === 0) {
      setSubmitError('Add at least one line with an item, quantity and rate.');
      return;
    }
    const incompleteLine = lines.some(
      (l) =>
        l.item_id > 0 &&
        (!(parseFloat(l.quantity_entered) > 0) || !(parseFloat(l.rate_rupees) >= 0))
    );
    if (incompleteLine) {
      setSubmitError('Every selected item needs a positive quantity and a rate.');
      return;
    }

    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const payload = {
        supplier_id: Number(selectedSupplierId),
        supplier_invoice_no: invoiceNo.trim() || undefined,
        purchase_date: new Date(`${purchaseDate}T00:00:00`).toISOString(),
        lines: validLines.map((l) => {
          const item = getItem(l.item_id);
          return {
            item_id: l.item_id,
            quantity_entered: parseFloat(l.quantity_entered),
            unit_entered: l.unit_entered || item?.display_unit || item?.base_unit || 'kg',
            rate_paise: Math.round((parseFloat(l.rate_rupees) || 0) * 100),
          };
        }),
      };

      const res = await apiClient.post<Purchase>('/purchases', payload);

      // Read the new balance from the stock summary so the receipt shows its effect.
      let updatedItems: { name: string; balance: string }[] = [];
      try {
        const stockSummary = await apiClient.get<StockSummaryItem[]>('/stock/summary');
        updatedItems = validLines.map((l) => {
          const item = getItem(l.item_id);
          const entry = stockSummary.find((s) => s.item_id === l.item_id);
          const balance = entry
            ? `${formatIndianDecimal(
                convertBaseQuantity(
                  entry.closing_balance_base,
                  entry.base_unit,
                  entry.display_unit
                )
              )} ${entry.display_unit}`
            : 'Updated';
          return { name: item?.name || `Item ${l.item_id}`, balance };
        });
      } catch {
        // The receipt is already posted; a failed summary read must not look like a post failure.
      }

      setPostSuccess({ purchaseNo: res.purchase_no, totalPaise: res.total_paise, updatedItems });
      setShowForm(false);
      setSelectedSupplierId('');
      setInvoiceNo('');
      setLines([emptyLine()]);
      const updatedPurchases = await apiClient.get<Purchase[]>('/purchases');
      setPurchases(updatedPurchases);
    } catch (err: any) {
      setSubmitError(err?.message || 'Failed to record purchase receipt.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSupplierName = (supplierId: number) =>
    suppliers.find((s) => s.id === supplierId)?.name || `Supplier #${supplierId}`;

  const getItemName = (itemId: number) =>
    items.find((i) => i.id === itemId)?.name || `Item #${itemId}`;

  const formatLineQuantity = (line: PurchaseLine) => {
    const item = getItem(line.item_id);
    if (!item) return `${line.quantity_base}`;
    return `${formatIndianDecimal(
      convertBaseQuantity(line.quantity_base, item.base_unit, item.display_unit)
    )} ${item.display_unit}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Purchases</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Record supplier goods receipts. Posting writes immutable stock-ledger entries and
            updates the moving weighted-average cost.
          </p>
        </div>
        <Button
          onClick={() => {
            setShowForm((open) => !open);
            setPostSuccess(null);
            setSubmitError(null);
          }}
          className="gap-1.5 h-8 text-xs self-start"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{showForm ? 'Close form' : 'New purchase receipt'}</span>
        </Button>
      </div>

      {postSuccess && (
        <div className="py-3 border-b border-status-ok-border" role="status">
          <div className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-status-ok-text shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-text-primary">
                {postSuccess.purchaseNo} posted ·{' '}
                {formatIndianCurrency(postSuccess.totalPaise / 100)}
              </p>
              {postSuccess.updatedItems.length > 0 && (
                <ul className="mt-1 space-y-0.5 text-xs text-text-secondary">
                  {postSuccess.updatedItems.map((ui) => (
                    <li key={ui.name}>
                      {ui.name}: <span className="font-semibold text-text-primary">{ui.balance}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <form onSubmit={handleSubmit} className="space-y-5 border-b border-border pb-6" data-testid="purchase-form">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Record goods receipt</h2>
            <p className="text-xs text-text-secondary mt-0.5">
              Quantities are entered in each item's display unit. The ledger stores base units.
            </p>
          </div>

          {submitError && <InlineError message={submitError} />}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="purchase-supplier">
                Supplier <span className="text-status-breach-text">*</span>
              </label>
              <select
                id="purchase-supplier"
                value={selectedSupplierId}
                onChange={(e) => setSelectedSupplierId(e.target.value ? Number(e.target.value) : '')}
                required
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] focus:outline-none focus:border-accent"
              >
                <option value="">Select supplier</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.gstin ? ` · ${s.gstin}` : ''}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="purchase-invoice-no">
                Supplier invoice no.
              </label>
              <input
                id="purchase-invoice-no"
                type="text"
                value={invoiceNo}
                onChange={(e) => setInvoiceNo(e.target.value)}
                placeholder="e.g. INV-9842"
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] focus:outline-none focus:border-accent"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="purchase-date">
                Receipt date <span className="text-status-breach-text">*</span>
              </label>
              <input
                id="purchase-date"
                type="date"
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
                required
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-text-primary">Items received</span>
              <Button type="button" variant="secondary" size="sm" onClick={addLine} className="h-7 text-xs gap-1">
                <Plus className="w-3 h-3" />
                <span>Add item</span>
              </Button>
            </div>

            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2 pr-3">Item</th>
                    <th className="py-2 px-3 w-28 text-right">Quantity</th>
                    <th className="py-2 px-3 w-20">Unit</th>
                    <th className="py-2 px-3 w-28 text-right">Rate</th>
                    <th className="py-2 px-3 w-32 text-right">Line total</th>
                    <th className="py-2 pl-2 w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {lines.map((line, idx) => {
                    const item = getItem(line.item_id);
                    const lineTotal =
                      (parseFloat(line.quantity_entered) || 0) * (parseFloat(line.rate_rupees) || 0);
                    return (
                      <tr key={idx}>
                        <td className="py-2 pr-3">
                          <select
                            aria-label={`Item for line ${idx + 1}`}
                            value={line.item_id}
                            onChange={(e) => handleItemChange(idx, Number(e.target.value))}
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                          >
                            <option value={0}>Select item</option>
                            {items.map((it) => (
                              <option key={it.id} value={it.id}>
                                {it.name} · {it.item_type.replace('_', ' ').toLowerCase()}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-3">
                          <input
                            aria-label={`Quantity for line ${idx + 1}`}
                            type="number"
                            step="any"
                            min="0.001"
                            value={line.quantity_entered}
                            onChange={(e) => handleLineChange(idx, 'quantity_entered', e.target.value)}
                            placeholder="0"
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] text-right tabular-nums"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <input
                            aria-label={`Unit for line ${idx + 1}`}
                            type="text"
                            value={line.unit_entered || (item ? item.display_unit : '')}
                            onChange={(e) => handleLineChange(idx, 'unit_entered', e.target.value)}
                            placeholder={item ? item.display_unit : 'unit'}
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <input
                            aria-label={`Rate for line ${idx + 1}`}
                            type="number"
                            step="0.01"
                            min="0"
                            value={line.rate_rupees}
                            onChange={(e) => handleLineChange(idx, 'rate_rupees', e.target.value)}
                            placeholder="0.00"
                            required
                            className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] text-right tabular-nums"
                          />
                        </td>
                        <td className="py-2 px-3 text-right font-medium tabular-nums">
                          {formatIndianCurrency(lineTotal)}
                        </td>
                        <td className="py-2 pl-2 text-center">
                          {lines.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeLine(idx)}
                              className="text-text-muted hover:text-status-breach-text p-1 rounded"
                              title="Remove item"
                              aria-label={`Remove line ${idx + 1}`}
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

            <div className="flex justify-end items-baseline gap-4 mt-3 pt-3 border-t border-border">
              <span className="text-xs font-semibold text-text-secondary">Receipt total</span>
              <span className="text-sm font-semibold text-text-primary tabular-nums">
                {formatIndianCurrency(calculateTotalPaise() / 100)}
              </span>
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setShowForm(false)} className="text-xs h-8">
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting} className="text-xs h-8 gap-1.5">
              {isSubmitting ? (
                <>
                  <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                  <span>Posting receipt…</span>
                </>
              ) : (
                <span>Post purchase receipt</span>
              )}
            </Button>
          </div>
        </form>
      )}

      <section className="space-y-3" aria-labelledby="recent-purchases-heading">
        <div className="flex items-baseline justify-between">
          <h2 id="recent-purchases-heading" className="text-sm font-semibold text-text-primary">
            Recent purchase receipts
          </h2>
          <span className="text-xs text-text-muted">{purchases.length} records</span>
        </div>

        {isLoading ? (
          <div className="space-y-2 border-t border-border pt-3" aria-label="Loading purchases">
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
            <Skeleton className="h-7 w-full" />
          </div>
        ) : error ? (
          <InlineError message={error} onRetry={fetchData} />
        ) : purchases.length === 0 ? (
          <EmptyState
            message="No purchase receipts recorded yet"
            description="Use “New purchase receipt” to record a supplier delivery and bring stock into inventory."
            action={
              <Button size="sm" onClick={() => setShowForm(true)} className="text-xs">
                Record first purchase
              </Button>
            }
          />
        ) : (
          <div className="overflow-x-auto border-t border-border">
            <table className="w-full text-xs" data-testid="purchases-table">
              <thead>
                <tr className="border-b border-border text-text-secondary text-left font-semibold">
                  <th className="py-2.5 pr-2 w-8"></th>
                  <th className="py-2.5 pr-3">Purchase no.</th>
                  <th className="py-2.5 px-3">Supplier</th>
                  <th className="py-2.5 px-3">Supplier invoice</th>
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3 text-right">Items</th>
                  <th className="py-2.5 px-3 text-right">Total</th>
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
                          {formatIndianDate(p.purchase_date)}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                          {p.lines.length}
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

                      {isExpanded && (
                        <tr className="bg-surface-subtle/40">
                          <td colSpan={8} className="py-3 px-6">
                            <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider mb-1.5">
                              Received items
                            </p>
                            <table className="w-full text-xs">
                              <thead>
                                <tr className="border-b border-border/60 text-text-muted text-left font-medium">
                                  <th className="py-1 pr-3">Item</th>
                                  <th className="py-1 px-3 text-right">Quantity</th>
                                  <th className="py-1 px-3 text-right">Rate</th>
                                  <th className="py-1 pl-3 text-right">Line total</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-border/40">
                                {p.lines.map((l) => (
                                  <tr key={l.id}>
                                    <td className="py-1.5 pr-3 font-medium text-text-primary">
                                      {getItemName(l.item_id)}
                                    </td>
                                    <td className="py-1.5 px-3 text-right tabular-nums text-text-secondary">
                                      {formatLineQuantity(l)}
                                    </td>
                                    <td className="py-1.5 px-3 text-right tabular-nums text-text-secondary">
                                      {formatIndianCurrency(l.rate_paise / 100)} / {l.unit_entered}
                                    </td>
                                    <td className="py-1.5 pl-3 text-right tabular-nums font-semibold text-text-primary">
                                      {formatIndianCurrency(l.line_total_paise / 100)}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
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
      </section>
    </div>
  );
};
