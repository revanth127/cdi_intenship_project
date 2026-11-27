import * as React from 'react';
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import {
  formatIndianCurrency,
  formatIndianDate,
  formatIndianDateTime,
} from '@/lib/format';
import {
  CheckCircle2,
  XCircle,
  FileText,
  AlertTriangle,
  RotateCcw,
  ArrowLeft,
  Edit2,
  Check,
  Minimize2,
} from 'lucide-react';
import { cn } from '@/components/ui/button';

type OrderStatus =
  | 'SUBMITTED'
  | 'APPROVED'
  | 'INVOICED'
  | 'DISPATCHED'
  | 'REJECTED';
type OrderFilter = 'ALL' | OrderStatus;

interface StockAvailabilityLine {
  product_id: number;
  product_name: string;
  requested: number;
  on_hand: number;
  committed_elsewhere: number;
  available: number;
  shortage: number;
  ok: boolean;
}

interface EstimatedTax {
  is_intra_state: boolean;
  taxable_amount_paise: number;
  cgst_paise: number;
  sgst_paise: number;
  igst_paise: number;
  total_tax_paise: number;
  grand_total_paise: number;
}

interface OrderLine {
  id: number;
  order_id: number;
  product_id: number;
  product_name?: string;
  quantity_packets: number;
  unit_price_paise: number;
  line_total_paise: number;
  price_source: string;
  stock_availability?: StockAvailabilityLine;
}

interface Order {
  id: number;
  order_no: string;
  client_uuid: string;
  customer_id: number;
  customer_name?: string;
  salesman_id: number;
  salesman_name?: string;
  order_date: string;
  status: OrderStatus;
  total_amount_paise: number;
  notes?: string;
  rejection_reason?: string;
  lines: OrderLine[];
  estimated_tax?: EstimatedTax;
  stock_availability?: StockAvailabilityLine[];
}

interface EditLine {
  id: number;
  product_id: number;
  quantity: string;
  rate_rupees: string;
}

const FILTERS: OrderFilter[] = [
  'ALL',
  'SUBMITTED',
  'APPROVED',
  'INVOICED',
  'DISPATCHED',
  'REJECTED',
];

const statusChip = (status: string) => {
  switch (status) {
    case 'APPROVED':
    case 'INVOICED':
    case 'DISPATCHED':
      return <StatusChip label={status} status="ok" size="sm" />;
    case 'SUBMITTED':
      return <StatusChip label={status} status="warning" size="sm" />;
    case 'REJECTED':
      return <StatusChip label={status} status="breach" size="sm" />;
    default:
      return <StatusChip label={status} status="neutral" size="sm" />;
  }
};

export const AdminOrdersPage: React.FC<{ isReadOnly?: boolean }> = ({
  isReadOnly = false,
}) => {
  const [orders, setOrders] = useState<Order[]>([]);
  const [activeFilter, setActiveFilter] = useState<OrderFilter>('ALL');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedOrderId, setSelectedOrderId] = useState<number | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [isEditingLines, setIsEditingLines] = useState(false);
  const [editLines, setEditLines] = useState<EditLine[]>([]);
  const [isSavingEdit, setIsSavingEdit] = useState(false);

  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [isRejecting, setIsRejecting] = useState(false);

  const [overrideShortage, setOverrideShortage] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isInvoicing, setIsInvoicing] = useState(false);
  const [createdInvoice, setCreatedInvoice] = useState<{ id: number; invoice_no: string } | null>(
    null
  );
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchOrders = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<Order[]>('/orders');
      setOrders(data);
    } catch (err: any) {
      setError(err?.message || 'Failed to load orders.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchOrders();
  }, []);

  const hydrateLines = (order: Order) => {
    setEditLines(
      order.lines.map((l) => ({
        id: l.id,
        product_id: l.product_id,
        quantity: String(l.quantity_packets),
        rate_rupees: (l.unit_price_paise / 100).toFixed(2),
      }))
    );
  };

  const loadOrderDetail = async (orderId: number, keepMessage = false) => {
    setSelectedOrderId(orderId);
    setIsLoadingDetail(true);
    setDetailError(null);
    if (!keepMessage) {
      setActionSuccess(null);
      setCreatedInvoice(null);
    }
    setActionError(null);
    setIsEditingLines(false);
    setOverrideShortage(false);
    try {
      const order = await apiClient.get<Order>(`/orders/${orderId}`);
      setSelectedOrder(order);
      hydrateLines(order);
    } catch (err: any) {
      setDetailError(err?.message || `Failed to load order #${orderId}.`);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const filteredOrders = orders.filter(
    (o) => activeFilter === 'ALL' || o.status === activeFilter
  );

  const totalShortage =
    selectedOrder?.lines.reduce(
      (sum, line) => sum + (line.stock_availability?.shortage || 0),
      0
    ) || 0;
  const hasShortage = totalShortage > 0;
  const approveBlocked = hasShortage && !overrideShortage;

  const handleSaveLineEdits = async () => {
    if (!selectedOrder) return;
    setIsSavingEdit(true);
    setActionError(null);
    try {
      const payload = {
        lines: editLines.map((l) => {
          const quantity = parseInt(l.quantity, 10);
          const rate = Math.round(parseFloat(l.rate_rupees) * 100);
          if (!Number.isInteger(quantity) || quantity <= 0) {
            throw new Error('Every line needs a whole-packet quantity greater than zero.');
          }
          if (!Number.isFinite(rate) || rate < 0) {
            throw new Error('Every line needs a valid rate.');
          }
          return {
            id: l.id,
            product_id: l.product_id,
            quantity_packets: quantity,
            unit_price_paise: rate,
          };
        }),
      };
      await apiClient.patch<Order>(`/orders/${selectedOrder.id}`, payload);
      await loadOrderDetail(selectedOrder.id, true);
      setActionSuccess('Order quantities and rates updated. Stock and tax recalculated.');
      fetchOrders();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to update order lines.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleReduceToAvailable = async () => {
    if (!selectedOrder) return;
    setIsSavingEdit(true);
    setActionError(null);
    try {
      const reducedLines = selectedOrder.lines.map((l) => ({
        id: l.id,
        product_id: l.product_id,
        quantity_packets:
          l.stock_availability && l.stock_availability.available > 0
            ? l.stock_availability.available
            : l.quantity_packets,
        unit_price_paise: l.unit_price_paise,
      }));
      await apiClient.patch<Order>(`/orders/${selectedOrder.id}`, { lines: reducedLines });
      await loadOrderDetail(selectedOrder.id, true);
      setActionSuccess('Order quantities reduced to available stock.');
      fetchOrders();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to adjust quantities.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleApprove = async () => {
    if (!selectedOrder) return;
    setIsApproving(true);
    setActionError(null);
    try {
      const updated = await apiClient.post<Order>(`/orders/${selectedOrder.id}/approve`, {
        approve_with_shortage: overrideShortage,
      });
      setSelectedOrder(updated);
      hydrateLines(updated);
      setActionSuccess(`Order ${updated.order_no} approved.`);
      fetchOrders();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to approve order.');
    } finally {
      setIsApproving(false);
    }
  };

  const handleReject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrder) return;
    if (rejectReason.trim().length < 3) {
      setActionError('Rejection reason must be at least 3 characters.');
      return;
    }
    setIsRejecting(true);
    setActionError(null);
    try {
      const updated = await apiClient.post<Order>(`/orders/${selectedOrder.id}/reject`, {
        reason: rejectReason.trim(),
      });
      setSelectedOrder(updated);
      setShowRejectModal(false);
      setRejectReason('');
      setActionSuccess(`Order ${updated.order_no} rejected.`);
      fetchOrders();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to reject order.');
    } finally {
      setIsRejecting(false);
    }
  };

  const handleRaiseInvoice = async () => {
    if (!selectedOrder) return;
    setIsInvoicing(true);
    setActionError(null);
    try {
      const invoice = await apiClient.post<{ id: number; invoice_no: string }>(
        `/orders/${selectedOrder.id}/invoice`
      );
      setCreatedInvoice(invoice);
      setActionSuccess(`GST tax invoice ${invoice.invoice_no} generated.`);
      await loadOrderDetail(selectedOrder.id, true);
      fetchOrders();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to generate invoice.');
    } finally {
      setIsInvoicing(false);
    }
  };

  const renderEditButton = () => {
    if (selectedOrder?.status !== 'SUBMITTED' || isReadOnly) return null;
    return (
      <Button
        variant="secondary"
        size="sm"
        onClick={() => (isEditingLines ? handleSaveLineEdits() : setIsEditingLines(true))}
        disabled={isSavingEdit}
        className="text-xs h-7 gap-1"
      >
        {isEditingLines ? (
          <>
            <Check className="w-3 h-3 text-status-ok-text" />
            <span>{isSavingEdit ? 'Saving…' : 'Save quantities & rates'}</span>
          </>
        ) : (
          <>
            <Edit2 className="w-3 h-3" />
            <span>Edit quantities / rates</span>
          </>
        )}
      </Button>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-text-primary tracking-tight">
              {isReadOnly ? 'Orders (read-only)' : 'Orders inbox'}
            </h1>
            {isReadOnly && <StatusChip label="READ-ONLY" status="neutral" size="sm" />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Review sales orders, verify available-to-promise stock, approve or reject, and raise
            GST invoices.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start">
          {selectedOrderId && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setSelectedOrderId(null);
                setSelectedOrder(null);
                setActionSuccess(null);
                setActionError(null);
                setCreatedInvoice(null);
              }}
              className="h-8 text-xs gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to inbox</span>
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              selectedOrderId ? loadOrderDetail(selectedOrderId) : fetchOrders()
            }
            className="h-8 text-xs gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
        </div>
      </div>

      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-surface border border-border rounded-[6px] max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <XCircle className="w-4 h-4 text-status-breach-text" />
                <span>Reject {selectedOrder?.order_no}</span>
              </h2>
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="text-text-muted hover:text-text-primary text-xs"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleReject} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="reject-reason">
                  Reason for rejection <span className="text-status-breach-text">*</span>
                </label>
                <textarea
                  id="reject-reason"
                  rows={3}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Required audit reason (at least 3 characters)"
                  required
                  minLength={3}
                  className="w-full text-xs p-2.5 bg-surface border border-border rounded-[4px]"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowRejectModal(false)}
                  className="text-xs h-8"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={isRejecting || rejectReason.trim().length < 3}
                  className="text-xs h-8"
                  variant="danger"
                >
                  {isRejecting ? 'Rejecting…' : 'Confirm rejection'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {actionSuccess && (
        <div className="py-2.5 border-b border-status-ok-border flex items-center gap-2 text-xs" role="status">
          <CheckCircle2 className="w-4 h-4 text-status-ok-text shrink-0" />
          <span className="font-medium text-text-primary">{actionSuccess}</span>
          {createdInvoice && (
            <Link
              to={`/invoices?id=${createdInvoice.id}`}
              className="text-accent hover:underline font-semibold"
            >
              Open {createdInvoice.invoice_no}
            </Link>
          )}
        </div>
      )}

      {actionError && <InlineError message={actionError} />}

      {selectedOrderId && selectedOrder ? (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-text-primary tracking-tight">
                  {selectedOrder.order_no}
                </h2>
                {statusChip(selectedOrder.status)}
                {selectedOrder.status === 'SUBMITTED' && hasShortage && (
                  <StatusChip label={`SHORT ${totalShortage} PACKETS`} status="breach" size="sm" />
                )}
              </div>
              <p className="text-xs text-text-secondary mt-0.5">
                {selectedOrder.customer_name || `Customer #${selectedOrder.customer_id}`} ·{' '}
                {selectedOrder.salesman_name || 'Direct'} ·{' '}
                {formatIndianDateTime(selectedOrder.order_date)}
              </p>
            </div>

            {!isReadOnly && (
              <div className="flex flex-wrap items-center gap-2">
                {selectedOrder.status === 'SUBMITTED' && (
                  <>
                    {hasShortage && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleReduceToAvailable}
                        disabled={isSavingEdit}
                        className="text-xs h-8 gap-1"
                        title="Set each line to current available ATP stock"
                      >
                        <Minimize2 className="w-3.5 h-3.5" />
                        <span>Reduce to available</span>
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setShowRejectModal(true)}
                      className="text-xs h-8 gap-1 text-status-breach-text"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Reject</span>
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleApprove}
                      disabled={isApproving || approveBlocked}
                      className="text-xs h-8 gap-1.5"
                      title={
                        approveBlocked
                          ? `Cannot approve: ${totalShortage} packets short. Reduce the order or use the explicit shortage override.`
                          : 'Approve order'
                      }
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>{isApproving ? 'Approving…' : 'Approve order'}</span>
                    </Button>
                  </>
                )}

                {selectedOrder.status === 'APPROVED' && (
                  <Button
                    size="sm"
                    onClick={handleRaiseInvoice}
                    disabled={isInvoicing}
                    className="text-xs h-8 gap-1.5"
                  >
                    <FileText className="w-3.5 h-3.5" />
                    <span>{isInvoicing ? 'Generating invoice…' : 'Raise GST invoice'}</span>
                  </Button>
                )}
              </div>
            )}
          </div>

          {selectedOrder.status === 'SUBMITTED' && approveBlocked && (
            <div className="py-3 border-b border-status-warning-border" role="alert">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-status-warning-text shrink-0 mt-0.5" />
                <div className="text-xs">
                  <p className="font-semibold text-text-primary">
                    Approval blocked: {totalShortage} packets short across requested items.
                  </p>
                  <p className="text-text-secondary mt-0.5">
                    Reduce quantities to available stock, or explicitly override below. The
                    shortage is recorded in the order audit trail.
                  </p>
                  {!isReadOnly && (
                    <label className="mt-2 inline-flex items-center gap-2 cursor-pointer text-text-primary">
                      <input
                        type="checkbox"
                        checked={overrideShortage}
                        onChange={(e) => setOverrideShortage(e.target.checked)}
                        className="h-3.5 w-3.5"
                      />
                      <span className="font-semibold">
                        Authorize approval despite shortage
                      </span>
                    </label>
                  )}
                </div>
              </div>
            </div>
          )}

          {selectedOrder.status === 'REJECTED' && selectedOrder.rejection_reason && (
            <p className="text-xs text-status-breach-text border-b border-border pb-3">
              Rejected: {selectedOrder.rejection_reason}
            </p>
          )}

          <section className="space-y-3" aria-labelledby="order-lines-heading">
            <div className="flex items-center justify-between">
              <h3 id="order-lines-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Line items & stock availability
              </h3>
              {renderEditButton()}
            </div>

            {isLoadingDetail ? (
              <div className="space-y-2 border-t border-border pt-3">
                <Skeleton className="h-7 w-full" />
                <Skeleton className="h-7 w-full" />
              </div>
            ) : detailError ? (
              <InlineError message={detailError} onRetry={() => loadOrderDetail(selectedOrderId)} />
            ) : (
              <div className="overflow-x-auto border-t border-border">
                <table className="w-full text-xs" data-testid="order-lines-table">
                  <thead>
                    <tr className="border-b border-border text-text-secondary text-left font-semibold">
                      <th className="py-2.5 pr-3">Product</th>
                      <th className="py-2.5 px-3 text-right w-28">Requested</th>
                      <th className="py-2.5 px-3 text-right">On hand</th>
                      <th className="py-2.5 px-3 text-right">Committed</th>
                      <th className="py-2.5 px-3 text-right">Available</th>
                      <th className="py-2.5 px-3 text-right">Shortage</th>
                      <th className="py-2.5 px-3 text-right w-28">Rate</th>
                      <th className="py-2.5 px-3 text-right">Line total</th>
                      <th className="py-2.5 pl-3 text-right">ATP</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {selectedOrder.lines.map((line, idx) => {
                      const atp = line.stock_availability;
                      const editItem = editLines[idx] || {
                        id: line.id,
                        product_id: line.product_id,
                        quantity: String(line.quantity_packets),
                        rate_rupees: (line.unit_price_paise / 100).toFixed(2),
                      };
                      const short = (atp?.shortage || 0) > 0;
                      return (
                        <tr key={line.id} className="hover:bg-surface-subtle/50 transition-colors">
                          <td className="py-2.5 pr-3 font-semibold text-text-primary">
                            {line.product_name || `Product #${line.product_id}`}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {isEditingLines ? (
                              <input
                                aria-label={`Quantity for ${line.product_name || line.product_id}`}
                                type="number"
                                min="1"
                                value={editItem.quantity}
                                onChange={(e) =>
                                  setEditLines((prev) =>
                                    prev.map((l, i) =>
                                      i === idx ? { ...l, quantity: e.target.value } : l
                                    )
                                  )
                                }
                                className="w-full text-xs h-7 px-1.5 bg-surface border border-border rounded text-right tabular-nums font-semibold"
                              />
                            ) : (
                              <span className="font-semibold text-text-primary tabular-nums">
                                {line.quantity_packets.toLocaleString('en-IN')}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                            {atp ? atp.on_hand.toLocaleString('en-IN') : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                            {atp ? atp.committed_elsewhere.toLocaleString('en-IN') : '—'}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums font-medium text-status-ok-text">
                            {atp ? atp.available.toLocaleString('en-IN') : '—'}
                          </td>
                          <td
                            className={cn(
                              'py-2.5 px-3 text-right tabular-nums font-semibold',
                              short ? 'text-status-breach-text' : 'text-text-muted'
                            )}
                          >
                            {short ? atp!.shortage.toLocaleString('en-IN') : '0'}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {isEditingLines ? (
                              <input
                                aria-label={`Rate for ${line.product_name || line.product_id}`}
                                type="number"
                                step="0.01"
                                min="0"
                                value={editItem.rate_rupees}
                                onChange={(e) =>
                                  setEditLines((prev) =>
                                    prev.map((l, i) =>
                                      i === idx ? { ...l, rate_rupees: e.target.value } : l
                                    )
                                  )
                                }
                                className="w-full text-xs h-7 px-1.5 bg-surface border border-border rounded text-right tabular-nums font-semibold"
                              />
                            ) : (
                              <span className="text-text-secondary tabular-nums">
                                {formatIndianCurrency(line.unit_price_paise / 100)}
                              </span>
                            )}
                          </td>
                          <td className="py-2.5 px-3 text-right font-semibold text-text-primary tabular-nums">
                            {formatIndianCurrency(line.line_total_paise / 100)}
                          </td>
                          <td className="py-2.5 pl-3 text-right">
                            <StatusChip
                              label={short ? 'SHORT' : 'AVAILABLE'}
                              status={short ? 'breach' : 'ok'}
                              size="sm"
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="space-y-3" aria-labelledby="tax-heading">
            <h3 id="tax-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Estimated GST
            </h3>
            {selectedOrder.estimated_tax ? (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 border-t border-border pt-3">
                <div>
                  <span className="text-xs text-text-muted block">Taxable value</span>
                  <span className="text-sm font-semibold text-text-primary tabular-nums">
                    {formatIndianCurrency(
                      selectedOrder.estimated_tax.taxable_amount_paise / 100
                    )}
                  </span>
                </div>
                {selectedOrder.estimated_tax.is_intra_state ? (
                  <>
                    <div>
                      <span className="text-xs text-text-muted block">CGST</span>
                      <span className="text-sm font-medium text-text-secondary tabular-nums">
                        {formatIndianCurrency(selectedOrder.estimated_tax.cgst_paise / 100)}
                      </span>
                    </div>
                    <div>
                      <span className="text-xs text-text-muted block">SGST</span>
                      <span className="text-sm font-medium text-text-secondary tabular-nums">
                        {formatIndianCurrency(selectedOrder.estimated_tax.sgst_paise / 100)}
                      </span>
                    </div>
                  </>
                ) : (
                  <div>
                    <span className="text-xs text-text-muted block">IGST</span>
                    <span className="text-sm font-medium text-text-secondary tabular-nums">
                      {formatIndianCurrency(selectedOrder.estimated_tax.igst_paise / 100)}
                    </span>
                  </div>
                )}
                <div>
                  <span className="text-xs font-semibold text-text-secondary block">
                    Grand total
                  </span>
                  <span className="text-base font-semibold text-accent tabular-nums">
                    {formatIndianCurrency(
                      selectedOrder.estimated_tax.grand_total_paise / 100
                    )}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-xs text-text-muted border-t border-border pt-3">
                Tax estimate is not available for this order.
              </p>
            )}
          </section>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-1 border-b border-border overflow-x-auto pb-1">
            {FILTERS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveFilter(tab)}
                className={cn(
                  'px-3 py-1.5 text-xs font-semibold rounded-[4px] transition-colors whitespace-nowrap',
                  activeFilter === tab
                    ? 'bg-accent text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
                )}
              >
                {tab}
                <span className="ml-1.5 text-[11px] opacity-75">
                  ({tab === 'ALL' ? orders.length : orders.filter((o) => o.status === tab).length})
                </span>
              </button>
            ))}
          </div>

          {isLoading ? (
            <div className="space-y-2 border-t border-border pt-3" aria-label="Loading orders">
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
            </div>
          ) : error ? (
            <InlineError message={error} onRetry={fetchOrders} />
          ) : filteredOrders.length === 0 ? (
            <EmptyState
              message={`No ${activeFilter.toLowerCase()} orders`}
              description="Orders submitted by field salesmen appear here for review."
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="orders-inbox-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Order no.</th>
                    <th className="py-2.5 px-3">Customer</th>
                    <th className="py-2.5 px-3">Salesman</th>
                    <th className="py-2.5 px-3">Date</th>
                    <th className="py-2.5 px-3 text-right">Items</th>
                    <th className="py-2.5 px-3 text-right">Total incl. GST</th>
                    <th className="py-2.5 pl-3 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredOrders.map((o) => (
                    <tr
                      key={o.id}
                      onClick={() => loadOrderDetail(o.id)}
                      className="hover:bg-surface-subtle/60 cursor-pointer transition-colors"
                    >
                      <td className="py-2.5 pr-3 font-semibold text-accent">{o.order_no}</td>
                      <td className="py-2.5 px-3 font-medium text-text-primary">
                        {o.customer_name || `Customer #${o.customer_id}`}
                      </td>
                      <td className="py-2.5 px-3 text-text-secondary">
                        {o.salesman_name || 'Direct'}
                      </td>
                      <td className="py-2.5 px-3 text-text-secondary">
                        {formatIndianDate(o.order_date)}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {o.lines.length}
                      </td>
                      <td className="py-2.5 px-3 text-right font-semibold text-text-primary tabular-nums">
                        {formatIndianCurrency(
                          (o.estimated_tax?.grand_total_paise ?? o.total_amount_paise) / 100
                        )}
                      </td>
                      <td className="py-2.5 pl-3 text-right">{statusChip(o.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
