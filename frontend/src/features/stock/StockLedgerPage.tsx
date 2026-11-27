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
import { ArrowLeft, Boxes, RotateCcw, ExternalLink } from 'lucide-react';
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
  weighted_avg_cost_paise: number;
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
  unit_cost: number;
  value_paise: number;
  source_type: string;
  source_id?: string;
  reverses_movement_id?: number;
  created_by?: number;
  note?: string;
}

export const StockLedgerPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<StockTab>('RAW_MATERIAL');
  const [summaryData, setSummaryData] = useState<StockSummaryItem[]>([]);
  const [isLoadingSummary, setIsLoadingSummary] = useState(true);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Drill-down selected item
  const [selectedItem, setSelectedItem] = useState<StockSummaryItem | null>(null);
  const [ledgerData, setLedgerData] = useState<StockLedgerEntry[]>([]);
  const [isLoadingLedger, setIsLoadingLedger] = useState(false);
  const [ledgerError, setLedgerError] = useState<string | null>(null);

  const fetchSummary = async (tab: StockTab) => {
    setIsLoadingSummary(true);
    setSummaryError(null);
    try {
      const data = await apiClient.get<StockSummaryItem[]>(`/stock/summary?item_type=${tab}`);
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
      const data = await apiClient.get<StockLedgerEntry[]>(`/stock/ledger?item_id=${item.item_id}`);
      setLedgerData(data);
    } catch (err: any) {
      setLedgerError(err?.message || `Failed to load ledger for ${item.name}.`);
    } finally {
      setIsLoadingLedger(false);
    }
  };

  const getMovementChip = (mType: string) => {
    switch (mType) {
      case 'PURCHASE_RECEIPT':
      case 'PRODUCTION_OUTPUT':
        return <StatusChip label={mType.replace('_', ' ')} status="ok" size="sm" />;
      case 'PRODUCTION_ISSUE':
        return <StatusChip label={mType.replace('_', ' ')} status="warning" size="sm" />;
      case 'REVERSAL':
        return <StatusChip label={mType} status="breach" size="sm" />;
      default:
        return <StatusChip label={mType} status="neutral" size="sm" />;
    }
  };

  const totalTabValueRupees = summaryData.reduce((acc, it) => acc + (it.total_value_paise || 0) / 100, 0);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Stock Inventory</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Immutable perpetual inventory ledger, moving weighted average cost valuation, and audit drill-down.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => {
            if (selectedItem) {
              fetchLedger(selectedItem);
            } else {
              fetchSummary(activeTab);
            }
          }}
          className="h-8 text-xs gap-1.5"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Refresh</span>
        </Button>
      </div>

      {selectedItem ? (
        /* Ledger Drill-Down View */
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setSelectedItem(null)}
                className="h-7 text-xs gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to Summary</span>
              </Button>
              <div>
                <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <span>{selectedItem.name}</span>
                  <span className="text-xs font-normal text-text-muted">({selectedItem.item_type})</span>
                </h2>
                <p className="text-xs text-text-secondary">
                  Current closing balance:{' '}
                  <span className="font-semibold text-accent">{selectedItem.closing_balance_display}</span>{' '}
                  ({formatIndianNumber(selectedItem.closing_balance_base)} {selectedItem.base_unit}) • WAC:{' '}
                  <span className="font-semibold">
                    {formatIndianCurrency(Number(selectedItem.weighted_avg_cost_paise || 0) / 100)}
                  </span>
                  /{selectedItem.display_unit}
                </p>
              </div>
            </div>
            <span className="text-xs text-text-muted">{ledgerData.length} movements recorded</span>
          </div>

          {isLoadingLedger ? (
            <div className="divide-y divide-border border-y border-border py-4">
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
            </div>
          ) : ledgerError ? (
            <InlineError message={ledgerError} onRetry={() => fetchLedger(selectedItem)} />
          ) : ledgerData.length === 0 ? (
            <EmptyState
              message="No ledger movements found for this item"
              description="Stock transactions (purchases, production issues, outputs) will appear chronologically here."
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="stock-ledger-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Date</th>
                    <th className="py-2.5 px-3">Movement Type</th>
                    <th className="py-2.5 px-3 text-right">In Qty</th>
                    <th className="py-2.5 px-3 text-right">Out Qty</th>
                    <th className="py-2.5 px-3 text-right">Running Balance</th>
                    <th className="py-2.5 px-3 text-right">Unit Cost</th>
                    <th className="py-2.5 px-3 text-right">Value (₹)</th>
                    <th className="py-2.5 pl-3">Source Ref</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {ledgerData.map((row) => (
                    <tr key={row.id} className="hover:bg-surface-subtle/50 transition-colors">
                      <td className="py-2.5 pr-3 text-text-secondary font-mono">
                        {new Date(row.date).toLocaleString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </td>
                      <td className="py-2.5 px-3">{getMovementChip(row.movement_type)}</td>
                      <td className="py-2.5 px-3 text-right font-medium text-emerald-700 tabular-nums">
                        {row.in_qty_base > 0 ? `+${formatIndianNumber(row.in_qty_base)}` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-amber-700 tabular-nums">
                        {row.out_qty_base > 0 ? `-${formatIndianNumber(row.out_qty_base)}` : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right font-semibold text-text-primary tabular-nums">
                        {formatIndianNumber(row.running_balance_base)} {selectedItem.base_unit}
                      </td>
                      <td className="py-2.5 px-3 text-right text-text-secondary tabular-nums">
                        {formatIndianCurrency(Number(row.unit_cost || 0) / 100)}
                      </td>
                      <td className="py-2.5 px-3 text-right font-medium text-text-primary tabular-nums">
                        {formatIndianCurrency(Number(row.value_paise || 0) / 100)}
                      </td>
                      <td className="py-2.5 pl-3 font-mono text-accent font-medium">
                        {row.source_type && row.source_id ? (
                          <span className="inline-flex items-center gap-1">
                            <span>
                              {row.source_type}:{row.source_id}
                            </span>
                          </span>
                        ) : (
                          row.source_type || '—'
                        )}
                        {row.note && <span className="block text-[10px] text-text-muted font-sans">{row.note}</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* Stock Summary View with Category Tabs */
        <div className="space-y-4">
          {/* Tabs */}
          <div className="flex items-center justify-between border-b border-border">
            <div className="flex gap-2">
              {(
                [
                  { key: 'RAW_MATERIAL', label: 'Raw Materials' },
                  { key: 'PACKAGING', label: 'Packaging' },
                  { key: 'FINISHED_GOOD', label: 'Finished Goods' },
                ] as const
              ).map((tab) => (
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
              Category Total:{' '}
              <span className="font-semibold text-text-primary tabular-nums">
                {formatIndianCurrency(totalTabValueRupees)}
              </span>
            </div>
          </div>

          {isLoadingSummary ? (
            <div className="divide-y divide-border border-y border-border py-4">
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
            </div>
          ) : summaryError ? (
            <InlineError message={summaryError} onRetry={() => fetchSummary(activeTab)} />
          ) : summaryData.length === 0 ? (
            <EmptyState
              message={`No ${activeTab.toLowerCase().replace('_', ' ')} items found`}
              description="Master items can be configured in master settings or added via purchases."
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="stock-summary-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Item Name</th>
                    <th className="py-2.5 px-3 text-right">Opening</th>
                    <th className="py-2.5 px-3 text-right">Received</th>
                    <th className="py-2.5 px-3 text-right">Issued</th>
                    <th className="py-2.5 px-3 text-right">Adjusted</th>
                    <th className="py-2.5 px-3 text-right">Closing Balance</th>
                    <th className="py-2.5 px-3 text-right">Avg Cost (₹)</th>
                    <th className="py-2.5 px-3 text-right">Total Value (₹)</th>
                    <th className="py-2.5 pl-3 text-center">Audit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {summaryData.map((item) => (
                    <tr
                      key={item.item_id}
                      onClick={() => fetchLedger(item)}
                      className="hover:bg-surface-subtle/60 cursor-pointer transition-colors group"
                    >
                      <td className="py-2.5 pr-3 font-semibold text-text-primary group-hover:text-accent flex items-center gap-1.5">
                        <span>{item.name}</span>
                        <ExternalLink className="w-3 h-3 opacity-0 group-hover:opacity-100 text-accent transition-opacity" />
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {formatIndianNumber(item.opening_balance_base)}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-emerald-700">
                        {item.receipts_base > 0 ? `+${formatIndianNumber(item.receipts_base)}` : '0'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-amber-700">
                        {item.issues_base > 0 ? `-${formatIndianNumber(item.issues_base)}` : '0'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {item.adjustments_base !== 0
                          ? formatIndianNumber(item.adjustments_base)
                          : '0'}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-accent">
                        {item.closing_balance_display}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {formatIndianCurrency(Number(item.weighted_avg_cost_paise || 0) / 100)}/{item.display_unit}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                        {item.total_value_rupees
                          ? `₹${item.total_value_rupees}`
                          : formatIndianCurrency((item.total_value_paise || 0) / 100)}
                      </td>
                      <td className="py-2.5 pl-3 text-center">
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
