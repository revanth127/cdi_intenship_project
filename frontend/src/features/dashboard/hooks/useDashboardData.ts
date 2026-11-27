import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api/client';
import type { DailySalesPoint } from '../components/SalesTrendChart';
import type { PendingOrder } from '../components/OrdersAwaitingApprovalTable';
import type { InventoryItemRow } from '../components/StockInventoryTable';
import type { VarianceAlert } from '../components/VarianceAlertsList';
import type { AgeingBucket, DebtorCustomer } from '../components/ReceivablesAgeingBlock';
import type { ProductMarginRow } from '../components/ProductMarginTable';

export type DashboardPeriod = 'TODAY' | '7_DAYS' | '30_DAYS' | 'MTD';

export interface DashboardData {
  summary: {
    ordersTodayCount: number;
    ordersTodayValuePaise: number;
    awaitingApprovalCount: number;
    awaitingApprovalValuePaise: number;
    stockShortagesCount: number;
    varianceAlertsCount: number;
    outstandingDuesPaise: number;
    costPerPacketRupees: number;
    standardCostRupees?: number;
  };
  salesTrend: DailySalesPoint[];
  ordersAwaitingApproval: PendingOrder[];
  stockInventory: InventoryItemRow[];
  varianceAlerts: VarianceAlert[];
  receivables: {
    totalDuesPaise: number;
    ageingBuckets: AgeingBucket[];
    topDebtors: DebtorCustomer[];
  };
  productMargins: ProductMarginRow[];
  lastUpdated: string;
}

interface DashboardSummaryResponse {
  as_of: string;
  today: {
    orders_received_count: number;
    orders_received_value_paise: number;
    orders_pending_approval_count: number;
  };
  stock: {
    finished_goods: Array<{
      product_id: number;
      product_name: string;
      pack_size_desc: string;
      on_hand_packets: number;
      available_to_promise_packets: number;
    }>;
    reorder_alerts: Array<{
      item_id: number;
      item_name: string;
      item_type: string;
      display_unit: string;
      current_stock_base: number;
      reorder_level_base: number | null;
      deficit_base: number | null;
    }>;
  };
  variance_alerts: Array<{
    run_id: number;
    run_no: string;
    run_date: string;
    product_name: string;
    item_name: string;
    planned_qty_base: number;
    actual_qty_base: number;
    variance_pct: number;
    display_unit: string;
  }>;
  receivables: {
    total_outstanding_paise: number;
    bucket_0_30_paise: number;
    bucket_31_60_paise: number;
    bucket_61_90_paise: number;
    bucket_90_plus_paise: number;
    top_debtors: Array<{
      customer_id: number;
      customer_name: string;
      total_outstanding_paise: number;
      oldest_invoice_date: string | null;
    }>;
  };
  costing: Array<{
    product_id: number;
    product_name: string;
    cost_per_packet: number;
    selling_price: number;
    margin_pct: number;
  }>;
  sales_trend: Array<{
    date: string;
    taxable_sales_paise: number;
    invoice_count: number;
  }>;
}

interface OrderResponse {
  id: number;
  order_no: string;
  customer_name: string | null;
  salesman_name: string | null;
  total_amount_paise: number;
  created_at: string;
  stock_availability: Array<{ shortage: number }>;
}

const PERIOD_TO_RANGE: Record<DashboardPeriod, string> = {
  TODAY: 'today',
  '7_DAYS': '7d',
  '30_DAYS': '30d',
  MTD: 'mtd',
};

const AGEING_BUCKETS: Array<{
  label: string;
  amountKey: keyof DashboardSummaryResponse['receivables'];
  colorClass: string;
}> = [
  { label: '0-30 days', amountKey: 'bucket_0_30_paise', colorClass: 'bg-blue-600' },
  { label: '31-60 days', amountKey: 'bucket_31_60_paise', colorClass: 'bg-amber-500' },
  { label: '61-90 days', amountKey: 'bucket_61_90_paise', colorClass: 'bg-orange-500' },
  { label: '90+ days', amountKey: 'bucket_90_plus_paise', colorClass: 'bg-red-600' },
];

function displayQuantity(baseQuantity: number, displayUnit: string): number {
  return displayUnit === 'kg' || displayUnit === 'L' ? baseQuantity / 1000 : baseQuantity;
}

function formatDayLabel(date: string): string {
  const [year, month, day] = date.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
  });
}

function oldestInvoiceBucket(invoiceDate: string | null, asOf: string): string {
  if (!invoiceDate) return '—';

  const ageDays = Math.max(
    0,
    Math.floor((Date.parse(asOf) - Date.parse(invoiceDate)) / (24 * 60 * 60 * 1000))
  );
  if (ageDays <= 30) return '0-30 days';
  if (ageDays <= 60) return '31-60 days';
  if (ageDays <= 90) return '61-90 days';
  return '90+ days';
}

function mapDashboardData(
  summary: DashboardSummaryResponse,
  orders: OrderResponse[]
): DashboardData {
  const receivablesTotal = summary.receivables.total_outstanding_paise;
  const costing = summary.costing.map((item): ProductMarginRow => ({
    productId: String(item.product_id),
    packName: item.product_name,
    familyName: item.product_name,
    costPerPacketRupees: Number(item.cost_per_packet),
    sellingPriceRupees: Number(item.selling_price),
    marginPercent: Number(item.margin_pct),
  }));
  const orderRows = orders.map((order): PendingOrder => {
    const shortageCount = order.stock_availability.reduce((sum, line) => sum + line.shortage, 0);
    return {
      id: String(order.id),
      orderNumber: order.order_no,
      customerName: order.customer_name || 'Unknown customer',
      salesmanName: order.salesman_name || 'Unknown salesman',
      totalPaise: order.total_amount_paise,
      stockStatus: shortageCount > 0 ? 'PARTIAL' : 'IN_STOCK',
      shortageCount,
      createdAt: order.created_at,
    };
  });

  return {
    summary: {
      ordersTodayCount: summary.today.orders_received_count,
      ordersTodayValuePaise: summary.today.orders_received_value_paise,
      awaitingApprovalCount: summary.today.orders_pending_approval_count,
      awaitingApprovalValuePaise: orderRows.reduce((total, order) => total + order.totalPaise, 0),
      stockShortagesCount: summary.stock.reorder_alerts.filter((item) => item.deficit_base !== null).length,
      varianceAlertsCount: summary.variance_alerts.length,
      outstandingDuesPaise: receivablesTotal,
      costPerPacketRupees: costing[0]?.costPerPacketRupees ?? 0,
    },
    salesTrend: summary.sales_trend.map((point): DailySalesPoint => ({
      date: point.date,
      label: formatDayLabel(point.date),
      salesPaise: point.taxable_sales_paise,
      orderCount: point.invoice_count,
    })),
    ordersAwaitingApproval: orderRows,
    stockInventory: [
      ...summary.stock.finished_goods.map((item): InventoryItemRow => ({
        id: String(item.product_id),
        name: item.product_name,
        category: 'FINISHED_GOODS',
        unit: 'packets',
        onHand: item.on_hand_packets,
        available: item.available_to_promise_packets,
      })),
      ...summary.stock.reorder_alerts.map((item): InventoryItemRow => ({
        id: String(item.item_id),
        name: item.item_name,
        category: item.item_type as InventoryItemRow['category'],
        unit: item.display_unit,
        onHand: displayQuantity(item.current_stock_base, item.display_unit),
        available: displayQuantity(item.current_stock_base, item.display_unit),
        reorderLevel: item.reorder_level_base === null
          ? undefined
          : displayQuantity(item.reorder_level_base, item.display_unit),
      })),
    ],
    varianceAlerts: summary.variance_alerts.map((alert): VarianceAlert => ({
      id: `${alert.run_id}-${alert.item_name}`,
      runId: String(alert.run_id),
      runNumber: alert.run_no,
      itemName: alert.item_name === 'finished packets'
        ? `Yield (${alert.product_name})`
        : alert.item_name,
      unit: alert.display_unit,
      plannedQty: displayQuantity(alert.planned_qty_base, alert.display_unit),
      actualQty: displayQuantity(alert.actual_qty_base, alert.display_unit),
      variancePercent: Number(alert.variance_pct),
      severity: 'BREACH',
      timestamp: alert.run_date,
    })),
    receivables: {
      totalDuesPaise: receivablesTotal,
      ageingBuckets: AGEING_BUCKETS.map(({ label, amountKey, colorClass }) => {
        const amountPaise = summary.receivables[amountKey] as number;
        return {
          label,
          amountPaise,
          percentage: receivablesTotal > 0 ? (amountPaise / receivablesTotal) * 100 : 0,
          colorClass,
        };
      }),
      topDebtors: summary.receivables.top_debtors.map((customer): DebtorCustomer => ({
        id: String(customer.customer_id),
        name: customer.customer_name,
        totalDuesPaise: customer.total_outstanding_paise,
        oldestBucket: oldestInvoiceBucket(customer.oldest_invoice_date, summary.as_of),
      })),
    },
    productMargins: costing,
    lastUpdated: new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }),
  };
}

export function useDashboardData(period: DashboardPeriod) {
  const rangeParam = PERIOD_TO_RANGE[period];

  return useQuery<DashboardData>({
    queryKey: ['dashboard-data', rangeParam],
    queryFn: async () => {
      const [summary, orders] = await Promise.all([
        apiClient.get<DashboardSummaryResponse>(`/dashboard/summary?range=${rangeParam}`),
        apiClient.get<OrderResponse[]>('/orders?status=SUBMITTED'),
      ]);
      return mapDashboardData(summary, orders);
    },
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  });
}
