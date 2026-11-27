import * as React from 'react';
import { formatIndianCurrency } from '@/lib/format';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { StatusChip } from '@/components/ui/status-chip';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';
import { EmptyState } from '@/components/ui/empty-state';

export interface ProductMarginRow {
  productId: string;
  packName: string;
  familyName: string;
  costPerPacketRupees: number;
  sellingPriceRupees: number;
  marginPercent: number; // e.g. 25.5
}

export interface ProductMarginTableProps {
  products?: ProductMarginRow[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const ProductMarginTable: React.FC<ProductMarginTableProps> = ({
  products = [],
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Margin by Product</CardTitle>
        </CardHeader>
        <CardContent>
          <InlineError message="Could not load product margin data." onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card data-testid="product-margin-skeleton">
        <CardHeader>
          <CardTitle>Margin by Product</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex justify-between items-center py-2 border-b border-border">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!products || products.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Margin by Product</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No product data"
            description="No active product variants found to calculate margins."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Margin by Product</CardTitle>
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          {products.length} {products.length === 1 ? 'pack size' : 'pack sizes'}
        </span>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-surface-subtle border-y border-border text-text-muted font-semibold">
              <tr>
                <th className="py-2 px-3">Product variant</th>
                <th className="py-2 px-3 text-right">Cost / packet</th>
                <th className="py-2 px-3 text-right">Selling price</th>
                <th className="py-2 px-3 text-right">Margin %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {products.map((p) => {
                const chipVariant = p.marginPercent >= 20 ? 'ok' : p.marginPercent >= 10 ? 'warning' : 'breach';
                return (
                  <tr key={p.productId} className="hover:bg-surface-subtle transition-colors">
                    <td className="py-2 px-3 font-medium text-text-primary">
                      <div className="font-semibold">{p.packName}</div>
                      <span className="text-[10px] text-text-muted uppercase tracking-wide">
                        {p.familyName}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-text-muted">
                      {formatIndianCurrency(p.costPerPacketRupees)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-text-primary">
                      {formatIndianCurrency(p.sellingPriceRupees)}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <StatusChip
                        variant={chipVariant}
                        label={`${p.marginPercent >= 0 ? '+' : ''}${p.marginPercent.toFixed(1)}%`}
                        size="sm"
                      />
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
