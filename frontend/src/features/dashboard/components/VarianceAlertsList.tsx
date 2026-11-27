import * as React from 'react';
import { Link } from 'react-router-dom';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { StatusChip } from '@/components/ui/status-chip';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';
import { EmptyState } from '@/components/ui/empty-state';
import { formatQuantityWithUnit } from '@/lib/format';

export interface VarianceAlert {
  id: string;
  runId: string;
  runNumber: string;
  itemName: string;
  unit: string;
  plannedQty: number;
  actualQty: number;
  variancePercent: number; // e.g. +5.2 or -6.0
  severity: 'BREACH' | 'WARNING';
  timestamp: string;
}

export interface VarianceAlertsListProps {
  alerts?: VarianceAlert[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const VarianceAlertsList: React.FC<VarianceAlertsListProps> = ({
  alerts = [],
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Variance Alerts</CardTitle>
        </CardHeader>
        <CardContent>
          <InlineError message="Could not load production variance alerts." onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card data-testid="variance-alerts-skeleton">
        <CardHeader>
          <CardTitle>Variance Alerts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex justify-between items-center py-2 border-b border-border">
              <Skeleton className="h-4 w-28" />
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-5 w-16" />
            </div>
          ))}
        </CardContent>
      </Card>
    );
  }

  if (!alerts || alerts.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Variance Alerts</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Within tolerance"
            description="All posted production runs are within standard 3.0% tolerance."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Variance Alerts</CardTitle>
        <span className="text-xs font-semibold text-status-breach-text uppercase tracking-wider">
          {alerts.length} {alerts.length === 1 ? 'flagged alert' : 'flagged alerts'}
        </span>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-surface-subtle border-y border-border text-text-muted font-semibold">
              <tr>
                <th className="py-2 px-3">Run</th>
                <th className="py-2 px-3">Item</th>
                <th className="py-2 px-3 text-right">Planned</th>
                <th className="py-2 px-3 text-right">Actual</th>
                <th className="py-2 px-3 text-right">Variance %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {alerts.map((alert) => {
                const isOver = alert.variancePercent > 0;
                const formattedVar = `${isOver ? '+' : ''}${alert.variancePercent.toFixed(1)}%`;
                const chipVariant = alert.severity === 'BREACH' ? 'breach' : 'warning';

                return (
                  <tr key={alert.id} className="hover:bg-surface-subtle transition-colors">
                    <td className="py-2 px-3 font-semibold">
                      <Link
                        to={`/production/runs/${alert.runId}`}
                        className="text-accent hover:underline focus:outline-none focus:ring-1 focus:ring-accent rounded"
                      >
                        {alert.runNumber}
                      </Link>
                    </td>
                    <td className="py-2 px-3 font-medium text-text-primary">
                      {alert.itemName}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-text-muted">
                      {formatQuantityWithUnit(alert.plannedQty, alert.unit)}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums font-semibold text-text-primary">
                      {formatQuantityWithUnit(alert.actualQty, alert.unit)}
                    </td>
                    <td className="py-2 px-3 text-right">
                      <StatusChip
                        variant={chipVariant}
                        label={formattedVar}
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
