import * as React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';
import { formatIndianCurrency } from '@/lib/format';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { InlineError } from '@/components/ui/inline-error';
import { EmptyState } from '@/components/ui/empty-state';

export interface DailySalesPoint {
  date: string; // YYYY-MM-DD
  label: string; // e.g. "01 Nov"
  salesPaise: number;
  orderCount: number;
}

export interface SalesTrendChartProps {
  data?: DailySalesPoint[];
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export const SalesTrendChart: React.FC<SalesTrendChartProps> = ({
  data = [],
  isLoading = false,
  isError = false,
  onRetry,
}) => {
  const [showTableFallback, setShowTableFallback] = React.useState(false);

  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Sales, Last 30 Days</CardTitle>
        </CardHeader>
        <CardContent>
          <InlineError message="Could not load 30-day sales trend." onRetry={onRetry} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card data-testid="sales-trend-skeleton">
        <CardHeader>
          <CardTitle>Sales, Last 30 Days</CardTitle>
        </CardHeader>
        <CardContent className="h-64 flex flex-col justify-end space-y-4">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-48 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!data || data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Sales, Last 30 Days</CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No sales in period"
            description="No invoiced sales recorded during the last 30 days."
          />
        </CardContent>
      </Card>
    );
  }

  const chartData = data.map((d) => ({
    ...d,
    salesRupees: d.salesPaise / 100,
  }));

  const totalSalesRupees = chartData.reduce((acc, d) => acc + d.salesRupees, 0);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle>Sales, Last 30 Days</CardTitle>
          <p className="text-xs text-text-secondary mt-0.5">
            Total:{' '}
            <span className="font-semibold text-text-primary tabular-nums">
              {formatIndianCurrency(totalSalesRupees, { showPaise: false })}
            </span>
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowTableFallback((prev) => !prev)}
          className="text-xs text-text-muted hover:text-accent underline focus:outline-none focus:ring-1 focus:ring-accent rounded"
          aria-label="Toggle accessible data table view for sales trend"
        >
          {showTableFallback ? 'Show chart' : 'Accessible table'}
        </button>
      </CardHeader>

      <CardContent>
        {showTableFallback ? (
          <div className="overflow-x-auto max-h-60 border border-border rounded text-xs">
            <table className="w-full text-left">
              <thead className="bg-surface-subtle border-b border-border text-text-muted">
                <tr>
                  <th className="py-1.5 px-3 font-semibold">Date</th>
                  <th className="py-1.5 px-3 font-semibold text-right">Orders</th>
                  <th className="py-1.5 px-3 font-semibold text-right">Sales</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {chartData.map((d) => (
                  <tr key={d.date} className="hover:bg-surface-subtle">
                    <td className="py-1.5 px-3 tabular-nums">{d.date}</td>
                    <td className="py-1.5 px-3 text-right tabular-nums">{d.orderCount}</td>
                    <td className="py-1.5 px-3 text-right tabular-nums font-medium">
                      {formatIndianCurrency(d.salesRupees)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div
            className="h-60 w-full"
            role="region"
            aria-label="30-day sales line chart. Toggle accessible table for full list."
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart
                data={chartData}
                margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
              >
                <CartesianGrid stroke="#e5e7eb" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="label"
                  tickLine={false}
                  axisLine={{ stroke: '#e5e7eb' }}
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  interval="preserveStartEnd"
                />
                <YAxis
                  tickLine={false}
                  axisLine={{ stroke: '#e5e7eb' }}
                  tick={{ fontSize: 11, fill: '#6b7280' }}
                  tickFormatter={(val: number) =>
                    val >= 100000 ? `₹${(val / 100000).toFixed(1)}L` : `₹${(val / 1000).toFixed(0)}k`
                  }
                  width={48}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const dataPoint = payload[0].payload as DailySalesPoint & { salesRupees: number };
                      return (
                        <div className="bg-surface border border-border shadow-subtle p-2 rounded text-xs space-y-1">
                          <p className="font-semibold text-text-primary">{dataPoint.date}</p>
                          <p className="text-text-secondary">
                            Sales:{' '}
                            <span className="font-semibold text-text-primary tabular-nums">
                              {formatIndianCurrency(dataPoint.salesRupees)}
                            </span>
                          </p>
                          <p className="text-text-muted">
                            Orders:{' '}
                            <span className="font-medium tabular-nums">{dataPoint.orderCount}</span>
                          </p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="salesRupees"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, stroke: 'var(--accent)', strokeWidth: 2, fill: '#ffffff' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
};
