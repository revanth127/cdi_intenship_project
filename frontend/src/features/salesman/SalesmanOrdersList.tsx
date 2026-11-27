import * as React from 'react';
import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { RotateCcw, Plus, Trash2, Edit3, Clock, CheckCircle2, AlertCircle, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { formatIndianCurrency } from '@/lib/format';
import { getOutboxOrders, deleteFromOutbox } from '@/lib/offline/db';
import { useSyncStatus } from '@/lib/offline/useSyncStatus';
import type { OutboxOrder } from '@/lib/offline/types';

export const SalesmanOrdersList: React.FC = () => {
  const navigate = useNavigate();
  const [orders, setOrders] = useState<OutboxOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const { status, triggerSync } = useSyncStatus();

  const loadOrders = async () => {
    setIsLoading(true);
    try {
      const list = await getOutboxOrders();
      setOrders(list);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
    const handleSyncStatusChanged = () => {
      loadOrders();
    };
    window.addEventListener('sync:status-changed', handleSyncStatusChanged);
    return () => window.removeEventListener('sync:status-changed', handleSyncStatusChanged);
  }, []);

  const handleDiscard = async (client_uuid: string) => {
    if (confirm('Discard this order from your phone?')) {
      await deleteFromOutbox(client_uuid);
      loadOrders();
    }
  };

  const handleEdit = (client_uuid: string) => {
    navigate(`/orders/new?edit=${client_uuid}`);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Top Banner & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">My Orders</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Local outbox and confirmed orders on this device
          </p>
        </div>

        <div className="flex items-center gap-2">
          {status.isOnline && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => triggerSync()}
              disabled={status.isSyncing}
              className="text-xs gap-1.5 h-8"
              data-testid="sync-now-button"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${status.isSyncing ? 'animate-spin' : ''}`} />
              <span>{status.isSyncing ? 'Syncing...' : 'Sync Now'}</span>
            </Button>
          )}

          <Link to="/orders/new">
            <Button variant="primary" size="sm" className="text-xs gap-1.5 h-8">
              <Plus className="w-3.5 h-3.5" />
              <span>New Order</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Orders Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle>Orders ({orders.length})</CardTitle>
          <div className="text-xs text-text-muted">
            {orders.filter((o) => o.status !== 'sent').length} pending sync
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {orders.length === 0 ? (
            <div className="py-12 text-center text-xs text-text-muted">
              No orders found in local device outbox. Tap &quot;New Order&quot; to book an order.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead className="bg-surface-subtle border-y border-border text-text-muted font-semibold">
                  <tr>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Customer</th>
                    <th className="py-2.5 px-3">Created</th>
                    <th className="py-2.5 px-3 text-right">Packets</th>
                    <th className="py-2.5 px-3 text-right">Value</th>
                    <th className="py-2.5 px-3">Server Ref / Error</th>
                    <th className="py-2.5 px-2 w-20 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {orders.map((o) => {
                    const totalPackets = o.lines
                      ? o.lines.reduce((acc, l) => acc + l.quantity_packets, 0)
                      : 0;

                    return (
                      <tr
                        key={o.client_uuid}
                        className={`hover:bg-surface-hover ${
                          o.status === 'needs_attention' ? 'bg-status-breach-bg/30' : ''
                        }`}
                        data-testid={`order-row-${o.client_uuid}`}
                      >
                        <td className="py-2.5 px-3 whitespace-nowrap">
                          {o.status === 'queued' && (
                            <span
                              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] bg-slate-100 text-slate-700 border border-slate-200 text-[11px] font-medium"
                              data-testid="chip-waiting-to-send"
                            >
                              <Clock className="w-3 h-3 text-slate-500" />
                              <span>Waiting to send</span>
                            </span>
                          )}

                          {o.status === 'sending' && (
                            <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] bg-blue-50 text-blue-800 border border-blue-200 text-[11px] font-medium">
                              <RotateCcw className="w-3 h-3 animate-spin text-blue-600" />
                              <span>Sending...</span>
                            </span>
                          )}

                          {o.status === 'needs_attention' && (
                            <span
                              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] bg-status-breach-bg text-status-breach-text border border-status-breach-border text-[11px] font-semibold"
                              data-testid="chip-needs-attention"
                            >
                              <AlertCircle className="w-3 h-3 text-status-breach-text" />
                              <span>Needs attention</span>
                            </span>
                          )}

                          {o.status === 'sent' && (
                            <span
                              className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-[4px] bg-status-ok-bg text-status-ok-text border border-status-ok-border text-[11px] font-semibold"
                              data-testid="chip-sent"
                            >
                              <CheckCircle2 className="w-3 h-3 text-status-ok-text" />
                              <span>Sent</span>
                            </span>
                          )}
                        </td>

                        <td className="py-2.5 px-3 font-medium text-text-primary">
                          {o.customer_name}
                        </td>

                        <td className="py-2.5 px-3 text-text-secondary tabular-nums whitespace-nowrap">
                          {new Date(o.created_at).toLocaleTimeString('en-IN', {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </td>

                        <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                          {totalPackets} pkts
                        </td>

                        <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                          {formatIndianCurrency(o.total_amount_paise / 100)}
                        </td>

                        <td className="py-2.5 px-3 text-xs max-w-xs truncate">
                          {o.server_order_no ? (
                            <span className="font-mono text-accent font-semibold">{o.server_order_no}</span>
                          ) : o.last_error ? (
                            <span
                              className="text-status-breach-text truncate block font-medium"
                              title={o.last_error}
                              data-testid="order-error-message"
                            >
                              {o.last_error}
                            </span>
                          ) : (
                            <span className="text-text-muted">Queued on phone</span>
                          )}
                        </td>

                        <td className="py-2.5 px-2 text-center whitespace-nowrap">
                          {o.status === 'needs_attention' && (
                            <div className="flex items-center justify-center gap-1">
                              <button
                                type="button"
                                onClick={() => handleEdit(o.client_uuid)}
                                className="text-text-muted hover:text-accent p-1"
                                title="Edit order"
                                data-testid="edit-button"
                              >
                                <Edit3 className="w-3.5 h-3.5" />
                              </button>
                              <button
                                type="button"
                                onClick={() => handleDiscard(o.client_uuid)}
                                className="text-text-muted hover:text-status-breach-text p-1"
                                title="Discard order"
                                data-testid="discard-button"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};
