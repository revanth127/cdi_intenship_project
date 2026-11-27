import * as React from 'react';
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import {
  formatIndianCurrency,
  formatIndianDate,
  formatBaseQuantity,
  formatUnitCost,
} from '@/lib/format';
import { ArrowLeft, RotateCcw, ExternalLink } from 'lucide-react';
import { cn } from '@/components/ui/button';

type StockTab = 'RAW_MATERIAL' | 'PACKAGING' | 'FINISHED_GOOD';

interface StockSummaryItem {
  item_id: number;
  name: string;
  item_type: string;
  base_unit: string;
  display_unit: string;
  opening_balance_base: number;
  receipts_base: number;
  issues_base: number;
  adjustments_base: number;
  closing_balance_base: number;
  closing_balance_display: string;
  weighted_avg_cost_paise: number | string;
  total_value_paise: number;
  total_value_rupees: string;
  reconciled: boolean;
}

interface StockLedgerEntry {
  id: number;
  date: string;
  movement_type: string;
  in_qty_base: number;
  out_qty_base: number;
  running_balance_base: number;
  unit_cost: number | string;
  value_paise: number;
  source_type: string;
  source_id?: string;
  reverses_movement_id?: number;
  created_by?: number;
  note?: string;
}

const TABS: { key: StockTab; label: string }[] = [
  { key: 'RAW_MATERIAL', label: 'Raw materials' },
  { key: 'PACKAGING', label: 'Packaging' },
  { key: 'FINISHED_GOOD', label: 'Finished goods' },
];

const MOVEMENT_LABELS: Record<string, string> = {
  OPENING: 'Opening balance',
  PURCHASE: 'Purchase receipt',
  PRODUCTION_ISSUE: 'Production issue',
  PRODUCTION_OUTPUT: 'Production output',
  DISPATCH: 'Sales dispatch',
  ADJUSTMENT: 'Stock adjustment',
  REVERSAL: 'Reversal',
  SALES_RETURN: 'Sales return',
};

export const StockLedgerPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<StockTab>('RAW_MATERIAL');
  const [summaryData, setSummaryData] = useState<StockSummaryItem[]>([]);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const [selectedItem, setSelectedItem] = useState<StockSummaryItem | null>(null);
  const [ledgerData, setLedgerData] = useState<StockLedgerEntry[]>([]);
  const [isLoadingLedger, setIsLoadingLedger] = useState(false);
  const [ledgerError, setLedgerError] = useState<string | null>(null);

  const fetchSummary = async (tab: StockTab) => {
    setIsLoadingSummary(true);
    setSummaryError(null);
    try {
      const data = await apiClient.get<StockSummaryItem[]>(
        `/stock/summary?item_type=${tab}`
      );
      setSummaryData(data);
    } catch (err: any) {
      setSummaryError(err?.message || 'Failed to load stock inventory summary.');
    } finally {
      setIsLoadingSummary(false);
    }
  };

  useEffect(() => {
    fetchSummary(activeTab);
  }, [activeTab]);

  const fetchLedger = async (item: StockSummaryItem) => {
    setSelectedItem(item);
    setIsLoadingLedger(true);
    setLedgerError(null);
    try {
      const data = await apiClient.get<StockLedgerEntry[]>(
        `/stock/ledger?item_id=${item.item_id}`
      );
      setLedgerData(data);
    } catch (err: any) {
      setLedgerError(err?.message || `Failed to load ledger for ${item.name}.`);
    } finally {
      setIsLoadingLedger(false);
    }
  };

  const renderSource = (row: StockLedgerEntry) => {
    if (!row.source_type) return '—';

    let href: string | null = null;
    if (row.source_type === 'PURCHASE' && row.source_id) {
      href = `/purchases?purchase=${encodeURIComponent(row.source_id)}`;
    } else if (row.source_type === 'PRODUCTION_RUN' && row.source_id) {
      href = `/production?run=${encodeURIComponent(row.source_id)}`;
    } else if (row.source_type === 'INVOICE' && row.source_id) {
      href = `/invoices?id=${encodeURIComponent(row.source_id)}`;
    } else if (row.source_type === 'CREDIT_NOTE') {
      href = '/invoices';
    }

    const label = row.source_id
      ? `${row.source_type} · ${row.source_id}`
      : row.source_type;

    if (!href) return <span>{label}</span>;

    return (
      <Link
        to={href}
        className="inline-flex items-center gap-1 text-accent hover:underline"
        onClick={(e) => e.stopPropagation()}
      >
        <span>{label}</span>
        <ExternalLink className="w-3 h-3" aria-hidden="true" />
      </Link>
    );
  };

  const totalTabValueRupees = summaryData.reduce(
    (acc, it) => acc + (it.total_value_paise || 0) / 100,
    0
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Stock inventory</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Perpetual stock ledger, moving weighted-average valuation, and audit drill-down by
            source document.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => (selectedItem ? fetchLedger(selectedItem) : fetchSummary(activeTab))}
          className="h-8 text-xs gap-1.5 self-start"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {selectedItem ? (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-3">
            <div className="flex items-start gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSelectedItem(null)}
                className="h-7 text-xs gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back</span>
              </Button>
              <div>
                <h2 className="text-sm font-semibold text-text-primary">
                  {selectedItem.name}{' '}
                  <span className="text-xs font-normal text-text-muted">
                    · {selectedItem.item_type.replace('_', ' ').toLowerCase()}
                  </span>
                </h2>
                <p className="text-xs text-text-secondary">
                  Closing balance:{' '}
                  <span className="font-semibold text-accent tabular-nums">
                    {formatBaseQuantity(
                      selectedItem.closing_balance_base,
                      selectedItem.base_unit,
                      selectedItem.display_unit
                    )}{' '}
                    {selectedItem.display_unit}
                  </span>{' '}
                  · Average cost:{' '}
                  <span className="font-semibold">
                    {formatUnitCost(
                      selectedItem.weighted_avg_cost_paise,
                      selectedItem.base_unit,
                      selectedItem.display_unit
                    )}
                    /{selectedItem.display_unit}
                  </span>
                </p>
              </div>
            </div>
            <span className="text-xs text-text-muted">{ledgerData.length} movements</span>
          </div>

          {isLoadingLedger ? (
            <div className="space-y-2 border-t border-border pt-3" aria-label="Loading ledger">
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
            </div>
          ) : ledgerError ? (
            <InlineError message={ledgerError} onRetry={() => fetchLedger(selectedItem)} />
          ) : ledgerData.length === 0 ? (
            <EmptyState
              message="No ledger movements found for this item"
              description="Purchases, production issues, outputs and dispatches appear here chronologically."
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="stock-ledger-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Date</th>
                    <th className="py-2.5 px-3">Movement</th>
                    <th className="py-2.5 px-3 text-right">In</th>
                    <th className="py-2.5 px-3 text-right">Out</th>
                    <th className="py-2.5 px-3 text-right">Running balance</th>
                    <th className="py-2.5 px-3 text-right">Unit cost</th>
                    <th className="py-2.5 px-3 text-right">Value</th>
                    <th className="py-2.5 pl-3">Source document</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {ledgerData.map((row) => (
                    <tr key={row.id} className="hover:bg-surface-subtle/50 transition-colors">
                      <td className="py-2.5 pr-3 text-text-secondary whitespace-nowrap">
                        {formatIndianDate(row.date)}
                      </td>
                      <td className="py-2.5 px-3 text-text-primary">
                        {MOVEMENT_LABELS[row.movement_type] || row.movement_type}
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-status-ok-text tabular-nums">
                        {row.in_qty_base > 0
                          ? formatBaseQuantity(
                              row.in_qty_base,
                              selectedItem.base_unit,
                              selectedItem.display_unit
                            )
                          : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-status-warning-text tabular-nums">
                        {row.out_qty_base > 0
                          ? formatBaseQuantity(
                              row.out_qty_base,
                              selectedItem.base_unit,
                              selectedItem.display_unit
                            )
                          : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-semibold text-text-primary tabular-nums">
                        {formatBaseQuantity(
                          row.running_balance_base,
                          selectedItem.base_unit,
                          selectedItem.display_unit
                        )}{' '}
                        <span className="font-normal text-text-muted">
                          {selectedItem.display_unit}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-right text-text-secondary tabular-nums">
                        {formatUnitCost(
                          row.unit_cost,
                          selectedItem.base_unit,
                          selectedItem.display_unit
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-text-primary tabular-nums">
                        {formatIndianCurrency(Number(row.value_paise || 0) / 100)}
                      </td>
                      <td className="py-2.5 pl-3 text-accent">
                        {renderSource(row)}
                        {row.note && (
                          <span className="block text-[11px] text-text-muted">{row.note}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-border">
            <div className="flex gap-1">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    'py-2 px-3 text-xs font-semibold border-b-2 -mb-px transition-colors',
                    activeTab === tab.key
                      ? 'border-accent text-accent'
                      : 'border-transparent text-text-secondary hover:text-text-primary'
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="text-xs text-text-secondary pb-1">
              Category valuation:{' '}
              <span className="font-semibold text-text-primary tabular-nums">
                {formatIndianCurrency(totalTabValueRupees)}
              </span>
            </div>
          </div>

          {isLoadingSummary ? (
            <div className="space-y-2 border-t border-border pt-3" aria-label="Loading stock summary">
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
            </div>
          ) : summaryError ? (
            <InlineError message={summaryError} onRetry={() => fetchSummary(activeTab)} />
          ) : summaryData.length === 0 ? (
            <EmptyState
              message={`No ${TABS.find((t) => t.key === activeTab)?.label.toLowerCase()} found`}
              description="Items appear here once they exist in the item master and have stock movements."
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="stock-summary-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Item</th>
                    <th className="py-2.5 px-3">Unit</th>
                    <th className="py-2.5 px-3 text-right">Opening</th>
                    <th className="py-2.5 px-3 text-right">Received</th>
                    <th className="py-2.5 px-3 text-right">Issued</th>
                    <th className="py-2.5 px-3 text-right">Adjusted</th>
                    <th className="py-2.5 px-3 text-right">Closing</th>
                    <th className="py-2.5 px-3 text-right">Avg cost</th>
                    <th className="py-2.5 px-3 text-right">Value</th>
                    <th className="py-2.5 pl-3 text-right">Reconciled</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {summaryData.map((item) => (
                    <tr
                      key={item.item_id}
                      onClick={() => fetchLedger(item)}
                      className="hover:bg-surface-subtle/60 cursor-pointer transition-colors group"
                    >
                      <td className="py-2.5 pr-3 font-semibold text-text-primary group-hover:text-accent">
                        <span className="inline-flex items-center gap-1.5">
                          {item.name}
                          <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-accent transition-opacity" />
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-text-muted">{item.display_unit}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {formatBaseQuantity(
                          item.opening_balance_base,
                          item.base_unit,
                          item.display_unit
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-status-ok-text">
                        {item.receipts_base > 0
                          ? `+${formatBaseQuantity(
                              item.receipts_base,
                              item.base_unit,
                              item.display_unit
                            )}`
                          : '0'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-status-warning-text">
                        {item.issues_base > 0
                          ? `−${formatBaseQuantity(
                              item.issues_base,
                              item.base_unit,
                              item.display_unit
                            )}`
                          : '0'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {item.adjustments_base !== 0
                          ? formatBaseQuantity(
                              item.adjustments_base,
                              item.base_unit,
                              item.display_unit
                            )
                          : '0'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-accent">
                        {formatBaseQuantity(
                          item.closing_balance_base,
                          item.base_unit,
                          item.display_unit
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {formatUnitCost(
                          item.weighted_avg_cost_paise,
                          item.base_unit,
                          item.display_unit
                        )}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                        {formatIndianCurrency(item.total_value_paise / 100)}
                      </td>
                      <td className="py-2.5 pl-3 text-right">
                        <StatusChip
                          label={item.reconciled ? 'BALANCED' : 'MISMATCH'}
                          status={item.reconciled ? 'ok' : 'breach'}
                          size="sm"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
