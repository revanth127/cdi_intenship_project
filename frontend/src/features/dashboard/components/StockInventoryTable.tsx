import * as React from 'react';
import { formatQuantityWithUnit } from '@/lib/format';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { StatusChip } from '@/components/ui/status-chip';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';
import { EmptyState } from '@/components/ui/empty-state';

export interface InventoryItemRow {
  id: string;
  name: string;
  category: 'FINISHED_GOODS' | 'RAW_MATERIAL' | 'PACKAGING';
  unit: string;
  onHand: number;
  available: number;
  reorderLevel: number;
}

export interface StockInventoryTableProps {
  items?: InventoryItemRow[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const StockInventoryTable: React.FC<StockInventoryTableProps> = ({
  items = [],
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Finished Goods & Low Raw Materials</CardTitle>
        </CardHeader>
        <CardContent>
          <InlineError message="Could not load inventory stock status." onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card data-testid="stock-inventory-skeleton">
        <CardHeader>
          <CardTitle>Finished Goods & Low Raw Materials</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex justify-between items-center py-2 border-b border-border">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-28" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!items || items.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Finished Goods & Low Raw Materials</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Healthy stock levels"
            description="All finished goods and raw materials are above their reorder thresholds."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Finished Goods & Low Raw Materials</CardTitle>
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          {items.length} monitored items
        </span>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-surface-subtle border-y border-border text-text-muted font-semibold">
              <tr>
                <th className="py-2 px-3">Item</th>
                <th className="py-2 px-3 text-right">On hand</th>
                <th className="py-2 px-3 text-right">Available</th>
                <th className="py-2 px-3 text-right">Reorder level</th>
                <th className="py-2 px-3 min-w-[130px]">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((item) => {
                const ratio = item.reorderLevel > 0 ? (item.available / item.reorderLevel) : 1;
                const percent = Math.min(Math.max(Math.round(ratio * 100), 5), 100);

                let statusVariant: 'ok' | 'warning' | 'breach' = 'ok';
                let statusText = 'Normal';
                let barColor = 'bg-status-ok-text';

                if (item.available <= 0) {
                  statusVariant = 'breach';
                  statusText = 'Stockout';
                  barColor = 'bg-status-breach-text';
                } else if (item.available <= item.reorderLevel) {
                  statusVariant = 'warning';
                  statusText = 'Below reorder';
                  barColor = 'bg-status-warning-text';
                }

                return (
                  <tr key={item.id} className="hover:bg-surface-subtle transition-colors">
                    <td className="py-2 px-3 font-medium text-text-primary">
                      <div className="font-semibold">{item.name}</div>
                      <span className="text-[10px] text-text-muted uppercase tracking-wide">
                        {item.category.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums font-medium text-text-primary">
                      {formatQuantityWithUnit(item.onHand, item.unit)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-text-primary">
                      {formatQuantityWithUnit(item.available, item.unit)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-text-muted">
                      {formatQuantityWithUnit(item.reorderLevel, item.unit)}
                    </td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-2">
                        <div
                          className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden"
                          role="progressbar"
                          aria-valuenow={percent}
                          aria-valuemin={0}
                          aria-valuemax={100}
                          aria-label={`${item.name} stock ratio`}
                        >
                          <div
                            className={`h-full ${barColor}`}
                            style={{ width: `${percent}%` }}
                          />
                        </div>
                        <StatusChip variant={statusVariant} label={statusText} size="sm" />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};
