import * as React from 'react';
import { Link } from 'react-router-dom';
import { formatIndianCurrency } from '@/lib/format';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { StatusChip } from '@/components/ui/status-chip';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';
import { EmptyState } from '@/components/ui/empty-state';

export interface PendingOrder {
  id: string;
  orderNumber: string;
  customerName: string;
  salesmanName: string;
  totalPaise: number;
  stockStatus: 'IN_STOCK' | 'PARTIAL' | 'OUT_OF_STOCK';
  shortageCount?: number;
  createdAt: string;
}

export interface OrdersAwaitingApprovalTableProps {
  orders?: PendingOrder[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const OrdersAwaitingApprovalTable: React.FC<OrdersAwaitingApprovalTableProps> = ({
  orders = [],
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Orders Awaiting Approval</CardTitle>
        </CardHeader>
        <CardContent>
          <InlineError message="Could not load pending orders." onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card data-testid="orders-awaiting-skeleton">
        <CardHeader>
          <CardTitle>Orders Awaiting Approval</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex justify-between items-center py-2 border-b border-border">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-36" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-5 w-24" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!orders || orders.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Orders Awaiting Approval</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="All clear"
            description="No orders currently awaiting approval."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Orders Awaiting Approval</CardTitle>
        <span className="text-xs font-semibold text-text-muted uppercase tracking-wider">
          {orders.length} {orders.length === 1 ? 'order' : 'orders'}
        </span>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-surface-subtle border-y border-border text-text-muted font-semibold">
              <tr>
                <th className="py-2 px-3 min-w-[150px] whitespace-nowrap">Order no</th>
                <th className="py-2 px-3">Customer</th>
                <th className="py-2 px-3">Salesman</th>
                <th className="py-2 px-3 text-right">Value</th>
                <th className="py-2 px-3 text-center">Stock status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {orders.map((ord) => {
                const isShort = ord.stockStatus !== 'IN_STOCK';
                const chipVariant = ord.stockStatus === 'IN_STOCK' ? 'ok' : 'breach';
                const chipLabel = ord.stockStatus === 'IN_STOCK'
                  ? 'In stock'
                  : `Short by ${ord.shortageCount ?? 1}`;

                return (
                  <tr key={ord.id} className="hover:bg-surface-subtle transition-colors">
                    <td className="py-2 px-3 min-w-[150px] whitespace-nowrap font-semibold">
                      <Link
                        to={`/orders/${ord.id}`}
                        className="text-accent hover:underline whitespace-nowrap focus:outline-none focus:ring-1 focus:ring-accent rounded"
                      >
                        {ord.orderNumber}
                      </Link>
                    </td>
                    <td className="py-2 px-3 font-medium text-text-primary max-w-[140px] truncate" title={ord.customerName}>
                      {ord.customerName}
                    </td>
                    <td className="py-2 px-3 text-text-secondary truncate max-w-[110px]" title={ord.salesmanName}>
                      {ord.salesmanName}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-text-primary">
                      {formatIndianCurrency(ord.totalPaise / 100)}
                    </td>
                    <td className="py-2 px-3 text-center">
                      <StatusChip variant={chipVariant} label={chipLabel} size="sm" />
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
