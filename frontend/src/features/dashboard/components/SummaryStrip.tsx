import * as React from 'react';
import { formatIndianCurrency, formatIndianNumber } from '@/lib/format';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';

export interface SummaryMetric {
  label: string;
  value: string | number;
  context: string;
  delta?: {
    value: string;
    isPositiveGood?: boolean;
    isIncrease?: boolean;
  };
}

export interface SummaryStripProps {
  data?: {
    ordersTodayCount: number;
    ordersTodayValuePaise: number;
    awaitingApprovalCount: number;
    awaitingApprovalValuePaise: number;
    stockShortagesCount: number;
    varianceAlertsCount: number;
    outstandingDuesPaise: number;
    costPerPacketRupees: number | string;
    standardCostRupees?: number | string;
  };
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const SummaryStrip: React.FC<SummaryStripProps> = ({
  data,
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  if (isError) {
    return <InlineError message="Could not load summary metrics." onRetry={onRetry} />;
  }

  if (isLoading || !data) {
    return (
      <div
        className="border border-border rounded-[6px] bg-surface grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-y sm:divide-y-0 sm:divide-x divide-border"
        data-testid="summary-strip-skeleton"
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="p-3.5 space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3 w-28" />
          </div>
        ))}
      </div>
    );
  }

  const metrics: SummaryMetric[] = [
    {
      label: 'Orders in range',
      value: formatIndianNumber(data.ordersTodayCount),
      context: `${data.ordersTodayCount} orders, ${formatIndianCurrency(data.ordersTodayValuePaise / 100, { showPaise: false })} value`,
    },
    {
      label: 'Awaiting approval',
      value: formatIndianNumber(data.awaitingApprovalCount),
      context: data.awaitingApprovalCount > 0
        ? `${data.awaitingApprovalCount} ${data.awaitingApprovalCount === 1 ? 'order' : 'orders'}, ${formatIndianCurrency(data.awaitingApprovalValuePaise / 100, { showPaise: false })}`
        : 'All orders processed',
    },
    {
      label: 'Stock shortages',
      value: formatIndianNumber(data.stockShortagesCount),
      context: data.stockShortagesCount > 0 ? `${data.stockShortagesCount} items below reorder` : 'Normal inventory levels',
    },
    {
      label: 'Variance alerts',
      value: formatIndianNumber(data.varianceAlertsCount),
      context: data.varianceAlertsCount > 0 ? `${data.varianceAlertsCount} runs over tolerance` : 'All within 3.0% tolerance',
    },
    {
      label: 'Outstanding dues',
      value: formatIndianCurrency(data.outstandingDuesPaise / 100, { showPaise: false }),
      context: 'Receivables balance',
    },
    {
      label: 'Cost per packet',
      value: typeof data.costPerPacketRupees === 'number'
        ? `₹${data.costPerPacketRupees.toFixed(2)}`
        : `₹${Number(data.costPerPacketRupees || 0).toFixed(2)}`,
      context: data.standardCostRupees ? `Std: ₹${Number(data.standardCostRupees).toFixed(2)}` : 'Actual avg per packet',
    },
  ];

  return (
    <div
      className="border border-border rounded-[6px] bg-surface grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 divide-y sm:divide-y-0 sm:divide-x divide-border"
      data-testid="summary-strip"
      role="region"
      aria-label="Executive Operations Summary"
    >
      {metrics.map((m, idx) => (
        <div key={idx} className="p-3.5 flex flex-col justify-between">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted truncate block">
            {m.label}
          </span>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="text-xl font-semibold text-text-primary tabular-nums tracking-tight">
              {m.value}
            </span>
            {m.delta && (
              <span
                className={`text-[11px] font-semibold tabular-nums ${
                  m.delta.isPositiveGood
                    ? m.delta.isIncrease ? 'text-status-ok-text' : 'text-status-breach-text'
                    : m.delta.isIncrease ? 'text-status-breach-text' : 'text-status-ok-text'
                }`}
              >
                {m.delta.value}
              </span>
            )}
          </div>
          <span className="mt-1 text-xs text-text-secondary block break-words" title={m.context}>
            {m.context}
          </span>
        </div>
      ))}
    </div>
  );
};
