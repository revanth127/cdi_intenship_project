import * as React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ShoppingCart, CheckCircle2, AlertTriangle, Save, Send, Plus, Trash2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { formatIndianCurrency } from '@/lib/format';
import { useSyncStatus } from '@/lib/offline/useSyncStatus';
import {
  saveToOutbox,
  getCachedReference,
  setCachedReference,
  getOutboxOrder,
  updateOutboxOrder,
} from '@/lib/offline/db';
import { sendOrderToServer, flushOutbox } from '@/lib/offline/syncEngine';
import type {
  OutboxOrder,
  ReferenceCustomer,
  ReferenceProduct,
  CustomerEffectivePrice,
  OrderPayload,
} from '@/lib/offline/types';

// Default reference catalog for offline fallback
export const FALLBACK_CUSTOMERS: ReferenceCustomer[] = [
  { id: 1, name: 'Annapoorna Sweets', city: 'Madurai', state_code: '33', credit_limit_paise: 5000000 },
  { id: 2, name: 'Murugan Supermarket', city: 'Madurai', state_code: '33', credit_limit_paise: 4000000 },
  { id: 3, name: 'Meenakshi Department Store', city: 'Madurai', state_code: '33', credit_limit_paise: 3000000 },
];

export const FALLBACK_PRODUCTS: ReferenceProduct[] = [
  { id: 1, pack_name: 'Murukku 200 g', family_name: 'Murukku', net_weight_g: 200, packets_per_carton: 20, standard_price_paise: 5000 },
  { id: 2, pack_name: 'Murukku 500 g', family_name: 'Murukku', net_weight_g: 500, packets_per_carton: 10, standard_price_paise: 12000 },
  { id: 3, pack_name: 'Ribbon Pakoda 200 g', family_name: 'Pakoda', net_weight_g: 200, packets_per_carton: 20, standard_price_paise: 5500 },
];

export function formatPricesAsOf(isoDate?: string): string {
  if (!isoDate) {
    return 'Prices as of 26 Nov 2026, 10:42';
  }
  try {
    const d = new Date(isoDate);
    if (isNaN(d.getTime())) return 'Prices as of 26 Nov 2026, 10:42';
    const day = d.getDate();
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[d.getMonth()];
    const year = d.getFullYear();
    const hours = d.getHours().toString().padStart(2, '0');
    const minutes = d.getMinutes().toString().padStart(2, '0');
    return `Prices as of ${day} ${month} ${year}, ${hours}:${minutes}`;
  } catch {
    return 'Prices as of 26 Nov 2026, 10:42';
  }
}

export const SalesmanOrderPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const editUuid = searchParams.get('edit');
  const { status } = useSyncStatus();

  // Reference catalog state
  const [customers, setCustomers] = useState<ReferenceCustomer[]>(FALLBACK_CUSTOMERS);
  const [products, setProducts] = useState<ReferenceProduct[]>(FALLBACK_PRODUCTS);
  const [pricesAsOf, setPricesAsOf] = useState<string>('2026-11-26T10:42:00');

  // Form state
  const [selectedCustomerId, setSelectedCustomerId] = useState<number>(FALLBACK_CUSTOMERS[0].id);
  const [orderLines, setOrderLines] = useState<Array<{ productId: number; quantity: number }>>([
    { productId: FALLBACK_PRODUCTS[0].id, quantity: 20 },
  ]);
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedOrder, setSubmittedOrder] = useState<OutboxOrder | null>(null);

  // Load and refresh reference catalog (Stale-While-Revalidate)
  const loadReferenceData = useCallback(async () => {
    // 1. Read cached data first
    const cachedCust = await getCachedReference<ReferenceCustomer[]>('customers');
    const cachedProd = await getCachedReference<ReferenceProduct[]>('products');

    if (cachedCust) {
      setCustomers(cachedCust.data);
      setPricesAsOf(cachedCust.fetched_at);
    } else {
      await setCachedReference('customers', FALLBACK_CUSTOMERS, '2026-11-26T10:42:00');
    }

    if (cachedProd) {
      setProducts(cachedProd.data);
    } else {
      await setCachedReference('products', FALLBACK_PRODUCTS, '2026-11-26T10:42:00');
    }

    // 2. If online, revalidate in background
    if (typeof navigator !== 'undefined' && navigator.onLine) {
      try {
        const [resCust, resProd] = await Promise.allSettled([
          fetch('/api/v1/customers').then((r) => (r.ok ? r.json() : null)),
          fetch('/api/v1/products').then((r) => (r.ok ? r.json() : null)),
        ]);

        const nowIso = new Date().toISOString();

        if (resCust.status === 'fulfilled' && Array.isArray(resCust.value) && resCust.value.length > 0) {
          const formattedCust: ReferenceCustomer[] = resCust.value.map((c: any) => ({
            id: c.id,
            name: c.name,
            city: c.city || 'Madurai',
            state_code: c.state_code || '33',
            credit_limit_paise: c.credit_limit_paise,
          }));
          setCustomers(formattedCust);
          setPricesAsOf(nowIso);
          await setCachedReference('customers', formattedCust, nowIso);
        }

        if (resProd.status === 'fulfilled' && Array.isArray(resProd.value) && resProd.value.length > 0) {
          const formattedProd: ReferenceProduct[] = resProd.value.map((p: any) => ({
            id: p.id,
            pack_name: p.pack_name || p.name,
            family_name: p.family_name || 'Snacks',
            net_weight_g: p.net_weight_g || 200,
            packets_per_carton: p.packets_per_carton || 20,
            standard_price_paise: p.standard_price_paise || p.base_price_paise || 5000,
          }));
          setProducts(formattedProd);
          await setCachedReference('products', formattedProd, nowIso);
        }
      } catch {
        // Retain existing cached reference data
      }
    }
  }, []);

  useEffect(() => {
    loadReferenceData();
  }, [loadReferenceData]);

  // Load existing order if in edit mode (e.g. order marked needs_attention)
  useEffect(() => {
    if (editUuid) {
      getOutboxOrder(editUuid).then((order) => {
        if (order) {
          setSelectedCustomerId(order.customer_id);
          setNotes(order.notes || '');
          if (order.lines && order.lines.length > 0) {
            setOrderLines(
              order.lines.map((l) => ({
                productId: l.product_id,
                quantity: l.quantity_packets,
              }))
            );
          }
        }
      });
    }
  }, [editUuid]);

  const addLine = () => {
    setOrderLines([...orderLines, { productId: products[0].id, quantity: 10 }]);
  };

  const removeLine = (index: number) => {
    if (orderLines.length > 1) {
      setOrderLines(orderLines.filter((_, i) => i !== index));
    }
  };

  const updateLine = (index: number, field: 'productId' | 'quantity', val: number) => {
    const updated = [...orderLines];
    updated[index] = { ...updated[index], [field]: val };
    setOrderLines(updated);
  };

  const selectedCustomer = customers.find((c) => c.id === selectedCustomerId) || customers[0];

  const calculatedLines = orderLines.map((line) => {
    const product = products.find((p) => p.id === line.productId) || products[0];
    const unitPricePaise = product.standard_price_paise;
    const lineTotalPaise = line.quantity * unitPricePaise;
    return {
      product_id: product.id,
      product_name: product.pack_name,
      quantity_packets: line.quantity,
      unit_price_paise: unitPricePaise,
      line_total_paise: lineTotalPaise,
    };
  });

  const totalAmountPaise = calculatedLines.reduce((acc, l) => acc + l.line_total_paise, 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      // 1. Generate client UUID for idempotency (or reuse when editing an unsubmitted order)
      const client_uuid =
        editUuid ||
        (typeof crypto !== 'undefined' && crypto.randomUUID
          ? crypto.randomUUID()
          : `client-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`);

      const payload: OrderPayload = {
        client_uuid,
        customer_id: selectedCustomer.id,
        lines: calculatedLines.map((l) => ({
          product_id: l.product_id,
          quantity_packets: l.quantity_packets,
          unit_price_paise: l.unit_price_paise,
        })),
        notes: notes.trim() || undefined,
      };

      const outboxOrder: OutboxOrder = {
        client_uuid,
        payload,
        status: 'queued',
        attempts: 0,
        created_at: new Date().toISOString(),
        customer_id: selectedCustomer.id,
        customer_name: selectedCustomer.name,
        lines: calculatedLines,
        total_amount_paise: totalAmountPaise,
        notes: notes.trim() || undefined,
      };

      // 2. ALWAYS write the order to the Outbox first
      await saveToOutbox(outboxOrder);

      // 3. Try to send if currently online
      if (typeof navigator !== 'undefined' && navigator.onLine) {
        // Attempt direct send
        const sendResult = await sendOrderToServer(outboxOrder);

        if (sendResult.success) {
          const serverOrderNo = sendResult.data?.order_no || 'ORD-SENT';
          const updated = await updateOutboxOrder(client_uuid, {
            status: 'sent',
            server_order_no: serverOrderNo,
            server_order_id: sendResult.data?.id,
            sent_at: new Date().toISOString(),
            last_error: undefined,
          });
          setSubmittedOrder(updated || { ...outboxOrder, status: 'sent', server_order_no: serverOrderNo });
          return;
        }

        if (sendResult.status >= 400 && sendResult.status < 500 && sendResult.status !== 401) {
          // 4xx validation or permission error
          const updated = await updateOutboxOrder(client_uuid, {
            status: 'needs_attention',
            last_error: sendResult.errorMsg || `Client error (${sendResult.status})`,
            attempts: 1,
          });
          setSubmittedOrder(updated || { ...outboxOrder, status: 'needs_attention', last_error: sendResult.errorMsg });
          return;
        }

        // 5xx or network failure: keep queued, show "Saved on this phone"
        await updateOutboxOrder(client_uuid, {
          status: 'queued',
          attempts: 1,
          last_error: sendResult.errorMsg || 'Connection error. Retrying...',
        });
        setSubmittedOrder(outboxOrder);
      } else {
        // Offline: keep queued, show "Saved on this phone"
        setSubmittedOrder(outboxOrder);
      }
    } catch (err: any) {
      alert(`Could not save order: ${err.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Success view (or Saved on Phone view)
  if (submittedOrder) {
    const isQueued = submittedOrder.status === 'queued';
    const isNeedsAttention = submittedOrder.status === 'needs_attention';

    return (
      <div className="max-w-xl mx-auto py-8 px-4" data-testid="order-success-screen">
        <Card className="border border-border">
          <CardContent className="pt-8 pb-8 text-center space-y-4">
            <div
              className={`w-12 h-12 rounded-full mx-auto flex items-center justify-center ${
                isNeedsAttention
                  ? 'bg-status-breach-bg text-status-breach-text border border-status-breach-border'
                  : 'bg-status-ok-bg text-status-ok-text border border-status-ok-border'
              }`}
            >
              {isNeedsAttention ? <AlertTriangle className="w-6 h-6" /> : <CheckCircle2 className="w-6 h-6" />}
            </div>

            <h2 className="text-lg font-semibold text-text-primary tracking-tight" data-testid="success-title">
              {isQueued
                ? 'Saved on this phone'
                : isNeedsAttention
                ? 'Order Needs Attention'
                : 'Order submitted successfully'}
            </h2>

            <p className="text-xs text-text-secondary max-w-sm mx-auto">
              {isQueued
                ? 'Your order has been recorded securely in the local device outbox. It will sync automatically as soon as internet connectivity returns.'
                : isNeedsAttention
                ? submittedOrder.last_error || 'Please review this order before retrying.'
                : `Order confirmed #${submittedOrder.server_order_no || ''} for ${submittedOrder.customer_name}. Total: ${formatIndianCurrency(
                    submittedOrder.total_amount_paise / 100
                  )}`}
            </p>

            <div className="p-3 bg-surface-subtle border border-border rounded-[6px] text-left text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-text-muted">Customer:</span>
                <span className="font-semibold text-text-primary">{submittedOrder.customer_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Items:</span>
                <span className="tabular-nums font-semibold text-text-primary">
                  {submittedOrder.lines.reduce((acc, l) => acc + l.quantity_packets, 0)} packets
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Value:</span>
                <span className="tabular-nums font-semibold text-text-primary">
                  {formatIndianCurrency(submittedOrder.total_amount_paise / 100)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-muted">Status:</span>
                <span className="font-mono text-text-secondary uppercase">
                  {isQueued
                    ? 'QUEUED (WAITING TO SEND)'
                    : isNeedsAttention
                    ? 'NEEDS ATTENTION'
                    : `SENT (${submittedOrder.server_order_no || 'CONFIRMED'})`}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-center gap-3 pt-4">
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setSubmittedOrder(null);
                  setOrderLines([{ productId: products[0].id, quantity: 20 }]);
                  setNotes('');
                  navigate('/orders/new');
                }}
              >
                Take another order
              </Button>
              <Button variant="secondary" size="sm" onClick={() => navigate('/orders/my')}>
                View My Orders
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const isOffline = !status.isOnline;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">
            {editUuid ? 'Edit Order' : 'New Sales Order'}
          </h1>
          <p className="text-xs text-text-secondary mt-0.5">Take orders anytime — full offline capability</p>
        </div>

        {/* Offline indicator banner showing fetched_at timestamp */}
        {isOffline && (
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-[6px] bg-status-warning-bg border border-status-warning-border text-status-warning-text text-xs"
            data-testid="offline-prices-banner"
          >
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span className="font-medium">{formatPricesAsOf(pricesAsOf)}</span>
          </div>
        )}
      </div>

      {/* Order Entry Form */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>1. Select Retail Customer</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
                Customer Name
              </label>
              <select
                value={selectedCustomerId}
                onChange={(e) => setSelectedCustomerId(Number(e.target.value))}
                className="w-full h-9 px-3 rounded-[6px] border border-border bg-white text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
              >
                {customers.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.city})
                  </option>
                ))}
              </select>
            </div>
          </CardContent>
        </Card>

        {/* Product Selection */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>2. Order Items</CardTitle>
            <Button type="button" variant="secondary" size="sm" onClick={addLine} className="h-7 text-xs gap-1">
              <Plus className="w-3.5 h-3.5" />
              <span>Add item</span>
            </Button>
          </CardHeader>
          <CardContent className="space-y-3 p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-surface-subtle border-y border-border text-text-muted font-semibold">
                  <tr>
                    <th className="py-2 px-3">Product</th>
                    <th className="py-2 px-3 text-right">Price</th>
                    <th className="py-2 px-3 text-right w-24">Packets</th>
                    <th className="py-2 px-3 text-right">Line Total</th>
                    <th className="py-2 px-2 w-10"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {orderLines.map((line, idx) => {
                    const prod = products.find((p) => p.id === line.productId) || products[0];
                    const lineTotal = line.quantity * prod.standard_price_paise;
                    return (
                      <tr key={idx} className="hover:bg-surface-hover">
                        <td className="py-2 px-3">
                          <select
                            value={line.productId}
                            onChange={(e) => updateLine(idx, 'productId', Number(e.target.value))}
                            className="w-full h-8 px-2 rounded-[4px] border border-border bg-white text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                          >
                            {products.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.pack_name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-3 text-right tabular-nums text-text-secondary">
                          {formatIndianCurrency(prod.standard_price_paise / 100)}
                        </td>
                        <td className="py-2 px-3 text-right">
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={line.quantity}
                            onChange={(e) => updateLine(idx, 'quantity', Math.max(1, parseInt(e.target.value) || 1))}
                            className="w-20 h-8 px-2 rounded-[4px] border border-border text-right text-xs tabular-nums focus:outline-none focus:ring-1 focus:ring-accent"
                          />
                        </td>
                        <td className="py-2 px-3 text-right tabular-nums font-semibold text-text-primary">
                          {formatIndianCurrency(lineTotal / 100)}
                        </td>
                        <td className="py-2 px-2 text-center">
                          {orderLines.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeLine(idx)}
                              className="text-text-muted hover:text-status-breach-text p-1"
                              title="Remove item"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Total Row */}
            <div className="px-4 py-3 bg-surface-subtle flex justify-between items-center text-xs font-semibold border-t border-border">
              <span className="text-text-secondary">Total Order Value:</span>
              <span className="text-base text-accent tabular-nums">
                {formatIndianCurrency(totalAmountPaise / 100)}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Notes */}
        <Card>
          <CardHeader>
            <CardTitle>3. Delivery Instructions</CardTitle>
          </CardHeader>
          <CardContent>
            <textarea
              rows={2}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. Deliver before 11 AM via Madurai route"
              className="w-full p-2.5 rounded-[6px] border border-border text-xs text-text-primary focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </CardContent>
        </Card>

        {/* Offline Warning Strip on Review */}
        {isOffline && (
          <div
            className="p-3 rounded-[6px] bg-status-warning-bg border border-status-warning-border text-status-warning-text text-xs flex items-center gap-2"
            data-testid="offline-review-strip"
          >
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>
              You are currently offline. This order will be saved on this phone and sent automatically when connectivity returns.
            </span>
          </div>
        )}

        {/* Action Button: "Save order" when offline, "Submit order" when online */}
        <div className="flex items-center justify-end gap-3">
          <Button
            type="submit"
            variant="primary"
            size="md"
            disabled={isSubmitting}
            className="min-w-[140px] gap-2"
            data-testid="order-submit-button"
          >
            {isOffline ? (
              <>
                <Save className="w-4 h-4" />
                <span>Save order</span>
              </>
            ) : (
              <>
                <Send className="w-4 h-4" />
                <span>Submit order</span>
              </>
            )}
          </Button>
        </div>
      </form>
    </div>
  );
};
