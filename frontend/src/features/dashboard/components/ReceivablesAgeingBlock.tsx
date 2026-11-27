import * as React from 'react';
import { formatIndianCurrency } from '@/lib/format';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';
import { EmptyState } from '@/components/ui/empty-state';

export interface AgeingBucket {
  label: string; // "0-30 days", "31-60 days", etc.
  amountPaise: number;
  percentage: number;
  colorClass: string;
}

export interface DebtorCustomer {
  id: string;
  name: string;
  totalDuesPaise: number;
  oldestBucket: string;
}

export interface ReceivablesAgeingProps {
  ageingBuckets?: AgeingBucket[];
  topDebtors?: DebtorCustomer[];
  totalDuesPaise?: number;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const ReceivablesAgeingBlock: React.FC<ReceivablesAgeingProps> = ({
  ageingBuckets = [],
  topDebtors = [],
  totalDuesPaise = 0,
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Receivables Ageing</CardTitle>
        </CardHeader>
        <CardContent>
          <InlineError message="Could not load receivables ageing." onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card data-testid="receivables-skeleton">
        <CardHeader>
          <CardTitle>Receivables Ageing</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-6 w-full" />
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex justify-between py-1.5 border-b border-border">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-4 w-20" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (totalDuesPaise <= 0 && topDebtors.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Receivables Ageing</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Zero outstanding dues"
            description="All invoices have been paid in full."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle>Receivables Ageing</CardTitle>
          <p className="text-xs text-text-secondary mt-0.5">
            Total dues:{' '}
            <span className="font-semibold text-text-primary tabular-nums">
              {formatIndianCurrency(totalDuesPaise / 100)}
            </span>
          </p>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Horizontal Stacked Bar */}
        <div>
          <div
            className="h-4 w-full rounded flex overflow-hidden bg-gray-100"
            role="progressbar"
            aria-label="Receivables age breakdown"
          >
            {ageingBuckets.map((bucket, idx) => (
              <div
                key={idx}
                className={`${bucket.colorClass} transition-all duration-300`}
                style={{ width: `${Math.max(bucket.percentage, bucket.amountPaise > 0 ? 2 : 0)}%` }}
                title={`${bucket.label}: ${formatIndianCurrency(bucket.amountPaise / 100)} (${bucket.percentage.toFixed(1)}%)`}
              />
            ))}
          </div>

          {/* Legend */}
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
            {ageingBuckets.map((bucket, idx) => (
              <div key={idx} className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${bucket.colorClass}`} />
                <span className="text-text-secondary truncate">{bucket.label}:</span>
                <span className="font-semibold tabular-nums text-text-primary">
                  {formatIndianCurrency(bucket.amountPaise / 100, { showPaise: false })}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Top 5 Customers by Dues */}
        <div>
          <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-2">
            Top 5 Customers by Dues
          </h4>
          <div className="overflow-x-auto border border-border rounded">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-surface-subtle border-b border-border text-text-muted font-semibold">
                <tr>
                  <th className="py-1.5 px-3">Customer</th>
                  <th className="py-1.5 px-3">Oldest bucket</th>
                  <th className="py-1.5 px-3 text-right">Dues</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {topDebtors.map((deb) => (
                  <tr key={deb.id} className="hover:bg-surface-subtle">
                    <td className="py-1.5 px-3 font-medium text-text-primary truncate max-w-[140px]" title={deb.name}>
                      {deb.name}
                    </td>
                    <td className="py-1.5 px-3 text-text-secondary">{deb.oldestBucket}</td>
                    <td className="py-1.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                      {formatIndianCurrency(deb.totalDuesPaise / 100)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};
