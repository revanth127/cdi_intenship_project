import * as React from 'react';
import { useState, useEffect } from 'react';
import { useDashboardData, DashboardPeriod } from './hooks/useDashboardData';
import { SummaryStrip } from './components/SummaryStrip';
import { SalesTrendChart } from './components/SalesTrendChart';
import { OrdersAwaitingApprovalTable } from './components/OrdersAwaitingApprovalTable';
import { StockInventoryTable } from './components/StockInventoryTable';
import { VarianceAlertsList } from './components/VarianceAlertsList';
import { ReceivablesAgeingBlock } from './components/ReceivablesAgeingBlock';
import { ProductMarginTable } from './components/ProductMarginTable';
import { cn } from '@/components/ui/button';

const PERIOD_OPTIONS: { label: string; value: DashboardPeriod }[] = [
  { label: 'Today', value: 'TODAY' },
  { label: '7 days', value: '7_DAYS' },
  { label: '30 days', value: '30_DAYS' },
  { label: 'Month to date', value: 'MTD' },
];

export const OwnerDashboardPage: React.FC = () => {
  const [selectedPeriod, setSelectedPeriod] = useState<DashboardPeriod>('TODAY');
  const { data, isLoading, isError, refetch } = useDashboardData(selectedPeriod);

  // Listen to manual top-bar refresh events
  useEffect(() => {
    const handleRefresh = () => {
      refetch();
    };
    window.addEventListener('dashboard:refresh', handleRefresh);
    return () => window.removeEventListener('dashboard:refresh', handleRefresh);
  }, [refetch]);

  return (
    <div className="space-y-6">
      {/* 1. Page Header with Period Control */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Overview</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Operational and financial telemetry for Sri Murugan Foods
          </p>
        </div>

        {/* Period Control */}
        <div
          role="group"
          aria-label="Period selection"
          className="inline-flex items-center p-0.5 bg-surface-subtle border border-border rounded-[6px]"
        >
          {PERIOD_OPTIONS.map((opt) => {
            const isSelected = selectedPeriod === opt.value;
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => setSelectedPeriod(opt.value)}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium rounded-[4px] transition-colors',
                  isSelected
                    ? 'bg-surface text-text-primary font-semibold shadow-sm'
                    : 'text-text-muted hover:text-text-primary'
                )}
                aria-pressed={isSelected}
              >
                {opt.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Summary Strip (one continuous bordered row) */}
      <section aria-label="Key Operational Metrics">
        <SummaryStrip
          data={data?.summary}
          isLoading={isLoading}
          isError={isError}
          onRetry={() => refetch()}
        />
      </section>

      {/* Desktop 12-Column Responsive Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* 3. Sales Trend: last 30 days (col-span-12 lg:col-span-7) */}
        <div className="lg:col-span-7">
          <SalesTrendChart
            data={data?.salesTrend}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
          />
        </div>

        {/* 4. Orders Awaiting Approval (col-span-12 lg:col-span-5) */}
        <div className="lg:col-span-5">
          <OrdersAwaitingApprovalTable
            orders={data?.ordersAwaitingApproval}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
          />
        </div>

        {/* 5. Finished Goods & Low Raw Materials (col-span-12 lg:col-span-7) */}
        <div className="lg:col-span-7">
          <StockInventoryTable
            items={data?.stockInventory}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
          />
        </div>

        {/* 6. Production Variance Alerts (col-span-12 lg:col-span-5) */}
        <div className="lg:col-span-5">
          <VarianceAlertsList
            alerts={data?.varianceAlerts}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
          />
        </div>

        {/* 7. Receivables Ageing & Top Debtors (col-span-12 lg:col-span-6) */}
        <div className="lg:col-span-6">
          <ReceivablesAgeingBlock
            ageingBuckets={data?.receivables.ageingBuckets}
            topDebtors={data?.receivables.topDebtors}
            totalDuesPaise={data?.receivables.totalDuesPaise}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
          />
        </div>

        {/* 8. Margin by Product (col-span-12 lg:col-span-6) */}
        <div className="lg:col-span-6">
          <ProductMarginTable
            products={data?.productMargins}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
          />
        </div>
      </div>
    </div>
  );
};
