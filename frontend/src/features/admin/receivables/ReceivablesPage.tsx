import * as React from 'react';
import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/features/auth/AuthContext';
import { formatIndianCurrency, formatIndianDate } from '@/lib/format';
import { RotateCcw, Wallet } from 'lucide-react';

interface InvoiceOutstanding {
  invoice_id: number;
  invoice_no: string;
  invoice_date: string;
  customer_id: number;
  customer_name: string;
  grand_total_paise: number;
  credit_notes_total_paise: number;
  paid_allocations_paise: number;
  outstanding_paise: number;
  age_days: number;
  status: string;
}

interface CustomerOutstanding {
  customer_id: number;
  customer_name: string;
  total_invoiced_paise: number;
  total_credit_notes_paise: number;
  total_payments_paise: number;
  open_invoices_outstanding_paise: number;
  unallocated_advance_paise: number;
  total_outstanding_paise: number;
  invoices: InvoiceOutstanding[];
}

interface ReceivablesAgeing {
  as_of: string;
  total_bucket_0_30_paise: number;
  total_bucket_31_60_paise: number;
  total_bucket_61_90_paise: number;
  total_bucket_90_plus_paise: number;
  total_unallocated_advance_paise: number;
  grand_total_outstanding_paise: number;
}

interface PaymentResult {
  id: number;
  receipt_no: string;
  amount_paise: number;
  allocated_paise: number;
  unallocated_advance_paise: number;
}

const PAYMENT_MODES = ['CASH', 'UPI', 'BANK', 'CHEQUE'] as const;

const paise = (p: number) => formatIndianCurrency((p || 0) / 100);

export const ReceivablesPage: React.FC<{ isReadOnly?: boolean }> = ({ isReadOnly = false }) => {
  const { user } = useAuth();
  const canRecordPayment = !isReadOnly && user?.role === 'ADMIN';

  const [customers, setCustomers] = useState<CustomerOutstanding[]>([]);
  const [ageing, setAgeing] = useState<ReceivablesAgeing | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Payment form state
  const [showPaymentForm, setShowPaymentForm] = useState(false);
  const [payCustomerId, setPayCustomerId] = useState<number | ''>('');
  const [payAmountRupees, setPayAmountRupees] = useState('');
  const [payMode, setPayMode] = useState<(typeof PAYMENT_MODES)[number]>('BANK');
  const [payReference, setPayReference] = useState('');
  const [payInvoiceId, setPayInvoiceId] = useState<number | ''>('');
  const [isPostingPayment, setIsPostingPayment] = useState(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentSuccess, setPaymentSuccess] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [outstanding, ageingData] = await Promise.all([
        apiClient.get<CustomerOutstanding[]>('/receivables/outstanding'),
        apiClient.get<ReceivablesAgeing>('/receivables/ageing'),
      ]);
      setCustomers(outstanding);
      setAgeing(ageingData);
    } catch (err: any) {
      setError(err?.message || 'Failed to load receivables.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const openInvoicesForCustomer =
    customers.find((c) => c.customer_id === payCustomerId)?.invoices.filter(
      (i) => i.outstanding_paise > 0
    ) || [];

  const handleRecordPayment = async (e: React.FormEvent) => {
    e.preventDefault();
    setPaymentError(null);
    setPaymentSuccess(null);
    const amountRupees = parseFloat(payAmountRupees);
    if (payCustomerId === '') {
      setPaymentError('Select a customer.');
      return;
    }
    if (!Number.isFinite(amountRupees) || amountRupees <= 0) {
      setPaymentError('Enter a payment amount greater than zero.');
      return;
    }
    const amountPaise = Math.round(amountRupees * 100);
    setIsPostingPayment(true);
    try {
      const payment = await apiClient.post<PaymentResult>('/payments', {
        customer_id: payCustomerId,
        amount_paise: amountPaise,
        mode: payMode,
        reference_no: payReference.trim() || undefined,
        allocations:
          payInvoiceId !== ''
            ? [{ invoice_id: payInvoiceId, amount_paise: amountPaise }]
            : undefined,
      });
      setPaymentSuccess(
        `Payment ${payment.receipt_no} recorded — ${paise(payment.amount_paise)} received, ${paise(
          payment.allocated_paise
        )} allocated.`
      );
      setShowPaymentForm(false);
      setPayAmountRupees('');
      setPayReference('');
      setPayInvoiceId('');
      await fetchData();
    } catch (err: any) {
      setPaymentError(err?.message || 'Failed to record payment.');
    } finally {
      setIsPostingPayment(false);
    }
  };

  const totalOutstanding =
    ageing?.grand_total_outstanding_paise ??
    customers.reduce((sum, c) => sum + c.total_outstanding_paise, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-text-primary tracking-tight">Receivables</h1>
            {isReadOnly && <StatusChip label="READ-ONLY" status="neutral" size="sm" />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Customer dues, open invoices, statutory ageing, and payment collection.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start">
          <Button
            variant="secondary"
            size="sm"
            onClick={fetchData}
            className="h-8 text-xs gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
          {canRecordPayment && (
            <Button
              size="sm"
              onClick={() => {
                setShowPaymentForm((open) => !open);
                setPaymentError(null);
                setPaymentSuccess(null);
              }}
              className="h-8 text-xs gap-1.5"
            >
              <Wallet className="w-3.5 h-3.5" />
              <span>{showPaymentForm ? 'Close' : 'Record payment'}</span>
            </Button>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <SummaryCard label="Total outstanding" value={paise(totalOutstanding)} accent />
        <SummaryCard label="0–30 days" value={paise(ageing?.total_bucket_0_30_paise || 0)} />
        <SummaryCard label="31–60 days" value={paise(ageing?.total_bucket_31_60_paise || 0)} />
        <SummaryCard label="61–90 days" value={paise(ageing?.total_bucket_61_90_paise || 0)} />
        <SummaryCard label="90+ days" value={paise(ageing?.total_bucket_90_plus_paise || 0)} />
      </div>

      {paymentSuccess && (
        <div className="py-2.5 px-3 border border-status-ok-border bg-status-ok-bg text-status-ok-text text-xs rounded-[4px]">
          {paymentSuccess}
        </div>
      )}

      {/* Payment form */}
      {showPaymentForm && canRecordPayment && (
        <form
          onSubmit={handleRecordPayment}
          className="space-y-4 border border-border rounded-[6px] p-4 bg-surface"
          data-testid="payment-form"
        >
          <h2 className="text-sm font-semibold text-text-primary">Record payment</h2>
          {paymentError && <InlineError message={paymentError} />}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="pay-customer">
                Customer <span className="text-status-breach-text">*</span>
              </label>
              <select
                id="pay-customer"
                required
                value={payCustomerId}
                onChange={(e) => {
                  setPayCustomerId(e.target.value ? Number(e.target.value) : '');
                  setPayInvoiceId('');
                }}
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
              >
                <option value="">Select customer</option>
                {customers.map((c) => (
                  <option key={c.customer_id} value={c.customer_id}>
                    {c.customer_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="pay-amount">
                Amount (Rs) <span className="text-status-breach-text">*</span>
              </label>
              <input
                id="pay-amount"
                type="number"
                step="0.01"
                min="0.01"
                required
                value={payAmountRupees}
                onChange={(e) => setPayAmountRupees(e.target.value)}
                placeholder="0.00"
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] text-right tabular-nums"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="pay-mode">
                Mode
              </label>
              <select
                id="pay-mode"
                value={payMode}
                onChange={(e) => setPayMode(e.target.value as (typeof PAYMENT_MODES)[number])}
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
              >
                {PAYMENT_MODES.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="pay-reference">
                Reference no.
              </label>
              <input
                id="pay-reference"
                type="text"
                value={payReference}
                onChange={(e) => setPayReference(e.target.value)}
                placeholder="UTR / cheque no."
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
              />
            </div>
          </div>
          {payCustomerId !== '' && (
            <div>
              <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="pay-invoice">
                Allocate to invoice (optional)
              </label>
              <select
                id="pay-invoice"
                value={payInvoiceId}
                onChange={(e) => setPayInvoiceId(e.target.value ? Number(e.target.value) : '')}
                className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] max-w-md"
              >
                <option value="">Auto-allocate (FIFO across open invoices)</option>
                {openInvoicesForCustomer.map((i) => (
                  <option key={i.invoice_id} value={i.invoice_id}>
                    {i.invoice_no} — {paise(i.outstanding_paise)} outstanding
                  </option>
                ))}
              </select>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button type="submit" size="sm" disabled={isPostingPayment} className="text-xs h-8">
              {isPostingPayment ? 'Recording…' : 'Record payment'}
            </Button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="space-y-2 border-t border-border pt-3" aria-label="Loading receivables">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : error ? (
        <InlineError message={error} onRetry={fetchData} />
      ) : customers.length === 0 ? (
        <EmptyState
          message="No receivables"
          description="No posted invoices yet. Receivables appear once invoices are raised."
        />
      ) : (
        <div className="space-y-4">
          {customers.map((c) => (
            <section key={c.customer_id} className="border border-border rounded-[6px] bg-surface">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-4 py-3 border-b border-border">
                <div>
                  <h2 className="text-sm font-semibold text-text-primary">{c.customer_name}</h2>
                  <p className="text-xs text-text-muted mt-0.5">
                    Invoiced {paise(c.total_invoiced_paise)} · Paid {paise(c.total_payments_paise)}
                    {c.total_credit_notes_paise > 0 ? ` · Credits ${paise(c.total_credit_notes_paise)}` : ''}
                    {c.unallocated_advance_paise > 0 ? ` · Advance ${paise(c.unallocated_advance_paise)}` : ''}
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-[11px] text-text-muted block">Outstanding</span>
                  <span className="text-sm font-semibold text-text-primary tabular-nums">
                    {paise(c.total_outstanding_paise)}
                  </span>
                </div>
              </div>
              {c.invoices.length === 0 ? (
                <p className="px-4 py-3 text-xs text-text-muted">No open invoices.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-text-secondary text-left font-semibold">
                        <th className="py-2 px-4">Invoice</th>
                        <th className="py-2 px-3">Date</th>
                        <th className="py-2 px-3 text-right">Grand total</th>
                        <th className="py-2 px-3 text-right">Credits</th>
                        <th className="py-2 px-3 text-right">Paid</th>
                        <th className="py-2 px-3 text-right">Outstanding</th>
                        <th className="py-2 px-3 text-right">Age</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {c.invoices.map((inv) => (
                        <tr key={inv.invoice_id}>
                          <td className="py-2 px-4 font-semibold text-text-primary">{inv.invoice_no}</td>
                          <td className="py-2 px-3 text-text-secondary">{formatIndianDate(inv.invoice_date)}</td>
                          <td className="py-2 px-3 text-right tabular-nums">{paise(inv.grand_total_paise)}</td>
                          <td className="py-2 px-3 text-right tabular-nums">{paise(inv.credit_notes_total_paise)}</td>
                          <td className="py-2 px-3 text-right tabular-nums">{paise(inv.paid_allocations_paise)}</td>
                          <td className="py-2 px-3 text-right tabular-nums font-semibold">
                            {paise(inv.outstanding_paise)}
                          </td>
                          <td className="py-2 px-3 text-right text-text-muted">{inv.age_days}d</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
};

const SummaryCard: React.FC<{ label: string; value: string; accent?: boolean }> = ({
  label,
  value,
  accent,
}) => (
  <div className="border border-border rounded-[6px] bg-surface px-3 py-2.5">
    <span className="text-[11px] text-text-muted block">{label}</span>
    <span className={`text-sm font-semibold tabular-nums block mt-0.5 ${accent ? 'text-text-primary' : 'text-text-secondary'}`}>
      {value}
    </span>
  </div>
);
