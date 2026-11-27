import * as React from 'react';
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient, getAccessToken } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import {
  formatIndianCurrency,
  formatIndianDate,
  formatGstRate,
} from '@/lib/format';
import {
  ArrowLeft,
  Download,
  MessageCircle,
  Truck,
  RotateCcw,
  FileMinus,
  CheckCircle2,
} from 'lucide-react';

interface InvoiceLine {
  id: number;
  product_id: number;
  description: string;
  hsn_code: string;
  quantity_packets: number;
  unit_price_paise: number;
  taxable_paise: number;
  gst_rate_bp: number;
  cgst_paise: number;
  sgst_paise: number;
  igst_paise: number;
  line_total_paise: number;
}

interface Invoice {
  id: number;
  invoice_no: string;
  financial_year: string;
  invoice_date: string;
  order_id?: number | null;
  customer_id: number;
  status: 'POSTED' | 'CANCELLED';
  seller_name: string;
  seller_gstin: string;
  seller_address: string;
  seller_state_code: string;
  buyer_name: string;
  buyer_gstin?: string | null;
  buyer_address: string;
  buyer_state_code: string;
  place_of_supply_state_code: string;
  is_igst: boolean;
  taxable_total_paise: number;
  cgst_total_paise: number;
  sgst_total_paise: number;
  igst_total_paise: number;
  round_off_paise: number;
  grand_total_paise: number;
  grand_total_in_words?: string | null;
  cancelled_at?: string | null;
  cancel_reason?: string | null;
  lines: InvoiceLine[];
  is_dispatched: boolean;
}

interface ShareLink {
  share_token: string;
  public_url: string;
  whatsapp_url?: string | null;
  email_url?: string | null;
  expires_at: string;
}

interface CreditNote {
  id: number;
  credit_note_no: string;
  grand_total_paise: number;
  status: string;
  reason: string;
}

export const InvoicesPage: React.FC<{ isReadOnly?: boolean }> = ({ isReadOnly = false }) => {
  const [searchParams] = useSearchParams();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedInvoiceId, setSelectedInvoiceId] = useState<number | null>(null);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [isDownloading, setIsDownloading] = useState(false);
  const [shareLink, setShareLink] = useState<ShareLink | null>(null);
  const [isLoadingShare, setIsLoadingShare] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const [showDispatchForm, setShowDispatchForm] = useState(false);
  const [vehicleNo, setVehicleNo] = useState('');
  const [dispatchDate, setDispatchDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [isDispatching, setIsDispatching] = useState(false);

  const [showCreditForm, setShowCreditForm] = useState(false);
  const [creditReason, setCreditReason] = useState('');
  const [returnStock, setReturnStock] = useState(true);
  const [isIssuingCredit, setIsIssuingCredit] = useState(false);
  const [creditNote, setCreditNote] = useState<CreditNote | null>(null);

  const fetchInvoices = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.get<Invoice[]>('/invoices');
      setInvoices(data);
      const deepLink = searchParams.get('id');
      if (deepLink) {
        const id = Number(deepLink);
        if (data.some((inv) => inv.id === id)) {
          loadInvoice(id);
        }
      }
    } catch (err: any) {
      setError(err?.message || 'Failed to load invoices.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInvoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadInvoice = async (id: number) => {
    setSelectedInvoiceId(id);
    setIsLoadingDetail(true);
    setDetailError(null);
    setActionError(null);
    setActionSuccess(null);
    setShareLink(null);
    setShowDispatchForm(false);
    setShowCreditForm(false);
    setCreditNote(null);
    try {
      const invoice = await apiClient.get<Invoice>(`/invoices/${id}`);
      setSelectedInvoice(invoice);
    } catch (err: any) {
      setDetailError(err?.message || `Failed to load invoice #${id}.`);
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const downloadPdf = async () => {
    if (!selectedInvoice) return;
    setIsDownloading(true);
    setActionError(null);
    try {
      const token = getAccessToken();
      const res = await fetch(`/api/v1/invoices/${selectedInvoice.id}/pdf`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) {
        throw new Error(`PDF download failed (${res.status}).`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${selectedInvoice.invoice_no.replace(/\//g, '-')}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setActionError(err?.message || 'Could not download the invoice PDF.');
    } finally {
      setIsDownloading(false);
    }
  };

  const fetchShareLink = async () => {
    if (!selectedInvoice) return;
    setIsLoadingShare(true);
    setActionError(null);
    try {
      const link = await apiClient.get<ShareLink>(
        `/invoices/${selectedInvoice.id}/share-link`
      );
      setShareLink(link);
      if (link.whatsapp_url) {
        window.open(link.whatsapp_url, '_blank', 'noopener,noreferrer');
      }
    } catch (err: any) {
      setActionError(err?.message || 'Could not create a WhatsApp share link.');
    } finally {
      setIsLoadingShare(false);
    }
  };

  const handleDispatch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInvoice) return;
    setIsDispatching(true);
    setActionError(null);
    try {
      await apiClient.post(`/invoices/${selectedInvoice.id}/dispatch`, {
        vehicle_no: vehicleNo.trim() || undefined,
        dispatch_date: dispatchDate
          ? new Date(`${dispatchDate}T00:00:00`).toISOString()
          : undefined,
      });
      setShowDispatchForm(false);
      setVehicleNo('');
      await loadInvoice(selectedInvoice.id);
      setActionSuccess('Dispatch recorded. Finished-goods stock has been issued.');
      fetchInvoices();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to record dispatch.');
    } finally {
      setIsDispatching(false);
    }
  };

  const handleCreditNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInvoice) return;
    if (creditReason.trim().length < 3) {
      setActionError('A credit-note reason of at least 3 characters is required.');
      return;
    }
    setIsIssuingCredit(true);
    setActionError(null);
    try {
      const note = await apiClient.post<CreditNote>(
        `/invoices/${selectedInvoice.id}/credit-note`,
        { reason: creditReason.trim(), return_stock: returnStock }
      );
      setCreditNote(note);
      setShowCreditForm(false);
      setCreditReason('');
      await loadInvoice(selectedInvoice.id);
      setActionSuccess(`Credit note ${note.credit_note_no} issued.`);
      fetchInvoices();
    } catch (err: any) {
      setActionError(err?.message || 'Failed to issue credit note.');
    } finally {
      setIsIssuingCredit(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold text-text-primary tracking-tight">
              {isReadOnly ? 'Invoices (read-only)' : 'Invoices'}
            </h1>
            {isReadOnly && <StatusChip label="READ-ONLY" status="neutral" size="sm" />}
          </div>
          <p className="text-xs text-text-secondary mt-0.5">
            Immutable GST tax invoices, PDF downloads, WhatsApp sharing, dispatch, and credit
            notes.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start">
          {selectedInvoiceId && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setSelectedInvoiceId(null);
                setSelectedInvoice(null);
                setActionSuccess(null);
                setActionError(null);
              }}
              className="h-8 text-xs gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>All invoices</span>
            </Button>
          )}
          <Button
            variant="secondary"
            size="sm"
            onClick={() =>
              selectedInvoiceId ? loadInvoice(selectedInvoiceId) : fetchInvoices()
            }
            className="h-8 text-xs gap-1.5"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </Button>
        </div>
      </div>

      {actionSuccess && (
        <div className="py-2.5 border-b border-status-ok-border flex items-center gap-2 text-xs" role="status">
          <CheckCircle2 className="w-4 h-4 text-status-ok-text shrink-0" />
          <span className="font-medium text-text-primary">{actionSuccess}</span>
          {creditNote && (
            <span className="text-text-secondary">
              Credit note total {formatIndianCurrency(creditNote.grand_total_paise / 100)}
            </span>
          )}
        </div>
      )}
      {actionError && <InlineError message={actionError} />}

      {selectedInvoiceId && selectedInvoice ? (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-text-primary">
                  {selectedInvoice.invoice_no}
                </h2>
                <StatusChip
                  label={selectedInvoice.status}
                  status={selectedInvoice.status === 'POSTED' ? 'ok' : 'breach'}
                  size="sm"
                />
                <StatusChip
                  label={selectedInvoice.is_dispatched ? 'DISPATCHED' : 'NOT DISPATCHED'}
                  status={selectedInvoice.is_dispatched ? 'ok' : 'warning'}
                  size="sm"
                />
              </div>
              <p className="text-xs text-text-secondary mt-0.5">
                {formatIndianDate(selectedInvoice.invoice_date)} · FY{' '}
                {selectedInvoice.financial_year} · Buyer state{' '}
                {selectedInvoice.buyer_state_code}
              </p>
            </div>

            {!isReadOnly && (
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={downloadPdf}
                  disabled={isDownloading}
                  className="text-xs h-8 gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>{isDownloading ? 'Preparing…' : 'Download PDF'}</span>
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={fetchShareLink}
                  disabled={isLoadingShare}
                  className="text-xs h-8 gap-1.5"
                >
                  <MessageCircle className="w-3.5 h-3.5" />
                  <span>{isLoadingShare ? 'Creating link…' : 'Share on WhatsApp'}</span>
                </Button>
                {!selectedInvoice.is_dispatched && selectedInvoice.status === 'POSTED' && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowDispatchForm((v) => !v)}
                    className="text-xs h-8 gap-1.5"
                  >
                    <Truck className="w-3.5 h-3.5" />
                    <span>Record dispatch</span>
                  </Button>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowCreditForm((v) => !v)}
                  className="text-xs h-8 gap-1.5 text-status-breach-text"
                >
                  <FileMinus className="w-3.5 h-3.5" />
                  <span>Issue credit note</span>
                </Button>
              </div>
            )}
          </div>

          {shareLink && (
            <div className="py-2.5 border-b border-border text-xs text-text-secondary">
              WhatsApp share link created.{' '}
              <a
                href={shareLink.public_url}
                target="_blank"
                rel="noreferrer"
                className="text-accent hover:underline"
              >
                Open public invoice
              </a>{' '}
              · expires {formatIndianDate(shareLink.expires_at)}
            </div>
          )}

          {showDispatchForm && !isReadOnly && (
            <form onSubmit={handleDispatch} className="py-4 border-b border-border space-y-3">
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Record dispatch
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                <div>
                  <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="dispatch-vehicle">
                    Vehicle number
                  </label>
                  <input
                    id="dispatch-vehicle"
                    type="text"
                    value={vehicleNo}
                    onChange={(e) => setVehicleNo(e.target.value)}
                    placeholder="e.g. TN-59-AB-1234"
                    className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="dispatch-date">
                    Dispatch date
                  </label>
                  <input
                    id="dispatch-date"
                    type="date"
                    value={dispatchDate}
                    onChange={(e) => setDispatchDate(e.target.value)}
                    className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                  />
                </div>
                <div className="flex gap-2">
                  <Button type="submit" size="sm" disabled={isDispatching} className="text-xs h-8">
                    {isDispatching ? 'Recording…' : 'Confirm dispatch'}
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowDispatchForm(false)}
                    className="text-xs h-8"
                  >
                    Cancel
                  </Button>
                </div>
              </div>
              <p className="text-[11px] text-text-muted">
                Dispatch issues finished-goods stock for the invoice quantity and is audited.
              </p>
            </form>
          )}

          {showCreditForm && !isReadOnly && (
            <form onSubmit={handleCreditNote} className="py-4 border-b border-border space-y-3">
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Issue credit note
              </h3>
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="credit-reason">
                  Reason <span className="text-status-breach-text">*</span>
                </label>
                <textarea
                  id="credit-reason"
                  rows={2}
                  value={creditReason}
                  onChange={(e) => setCreditReason(e.target.value)}
                  placeholder="Required audit reason for the credit note"
                  required
                  minLength={3}
                  className="w-full text-xs p-2 bg-surface border border-border rounded-[4px]"
                />
              </div>
              <label className="inline-flex items-center gap-2 text-xs text-text-primary">
                <input
                  type="checkbox"
                  checked={returnStock}
                  onChange={(e) => setReturnStock(e.target.checked)}
                  className="h-3.5 w-3.5"
                />
                <span>Return dispatched goods to finished-goods stock</span>
              </label>
              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={isIssuingCredit} className="text-xs h-8">
                  {isIssuingCredit ? 'Issuing…' : 'Issue credit note'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowCreditForm(false)}
                  className="text-xs h-8"
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}

          {isLoadingDetail ? (
            <div className="space-y-2 border-t border-border pt-3">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : detailError ? (
            <InlineError message={detailError} onRetry={() => loadInvoice(selectedInvoiceId)} />
          ) : (
            <>
              <section className="grid grid-cols-1 sm:grid-cols-2 gap-6 border-b border-border pb-4">
                <div>
                  <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
                    Seller
                  </span>
                  <p className="text-sm font-semibold text-text-primary mt-1">
                    {selectedInvoice.seller_name}
                  </p>
                  <p className="text-xs text-text-secondary whitespace-pre-line">
                    {selectedInvoice.seller_address}
                  </p>
                  <p className="text-xs text-text-secondary mt-1">
                    GSTIN {selectedInvoice.seller_gstin} · State {selectedInvoice.seller_state_code}
                  </p>
                </div>
                <div>
                  <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
                    Buyer
                  </span>
                  <p className="text-sm font-semibold text-text-primary mt-1">
                    {selectedInvoice.buyer_name}
                  </p>
                  <p className="text-xs text-text-secondary whitespace-pre-line">
                    {selectedInvoice.buyer_address}
                  </p>
                  <p className="text-xs text-text-secondary mt-1">
                    GSTIN {selectedInvoice.buyer_gstin || '—'} · State{' '}
                    {selectedInvoice.buyer_state_code}
                  </p>
                </div>
              </section>

              <section className="space-y-3">
                <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                  Invoice lines
                </h3>
                <div className="overflow-x-auto border-t border-border">
                  <table className="w-full text-xs" data-testid="invoice-lines-table">
                    <thead>
                      <tr className="border-b border-border text-text-secondary text-left font-semibold">
                        <th className="py-2.5 pr-3">Description</th>
                        <th className="py-2.5 px-3">HSN</th>
                        <th className="py-2.5 px-3 text-right">Qty</th>
                        <th className="py-2.5 px-3 text-right">Rate</th>
                        <th className="py-2.5 px-3 text-right">Taxable</th>
                        <th className="py-2.5 px-3 text-right">GST</th>
                        <th className="py-2.5 pl-3 text-right">Line total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {selectedInvoice.lines.map((line) => (
                        <tr key={line.id}>
                          <td className="py-2.5 pr-3 font-medium text-text-primary">
                            {line.description}
                          </td>
                          <td className="py-2.5 px-3 text-text-secondary">{line.hsn_code}</td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                            {line.quantity_packets.toLocaleString('en-IN')}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                            {formatIndianCurrency(line.unit_price_paise / 100)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                            {formatIndianCurrency(line.taxable_paise / 100)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                            {formatGstRate(line.gst_rate_bp)}
                          </td>
                          <td className="py-2.5 pl-3 text-right tabular-nums font-semibold text-text-primary">
                            {formatIndianCurrency(line.line_total_paise / 100)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div className="text-xs text-text-secondary space-y-1">
                  {selectedInvoice.is_igst ? (
                    <p>
                      IGST:{' '}
                      <span className="font-semibold text-text-primary tabular-nums">
                        {formatIndianCurrency(selectedInvoice.igst_total_paise / 100)}
                      </span>
                    </p>
                  ) : (
                    <>
                      <p>
                        CGST:{' '}
                        <span className="font-semibold text-text-primary tabular-nums">
                          {formatIndianCurrency(selectedInvoice.cgst_total_paise / 100)}
                        </span>
                      </p>
                      <p>
                        SGST:{' '}
                        <span className="font-semibold text-text-primary tabular-nums">
                          {formatIndianCurrency(selectedInvoice.sgst_total_paise / 100)}
                        </span>
                      </p>
                    </>
                  )}
                  {selectedInvoice.round_off_paise !== 0 && (
                    <p>
                      Round off:{' '}
                      <span className="tabular-nums">
                        {formatIndianCurrency(selectedInvoice.round_off_paise / 100)}
                      </span>
                    </p>
                  )}
                </div>
                <div className="sm:text-right">
                  <p className="text-xs text-text-muted">Taxable value</p>
                  <p className="text-sm font-semibold text-text-primary tabular-nums">
                    {formatIndianCurrency(selectedInvoice.taxable_total_paise / 100)}
                  </p>
                  <p className="text-xs text-text-muted mt-1">Invoice total</p>
                  <p className="text-xl font-semibold text-accent tabular-nums">
                    {formatIndianCurrency(selectedInvoice.grand_total_paise / 100)}
                  </p>
                  {selectedInvoice.grand_total_in_words && (
                    <p className="text-[11px] text-text-secondary mt-1">
                      {selectedInvoice.grand_total_in_words}
                    </p>
                  )}
                </div>
              </section>
            </>
          )}
        </div>
      ) : (
        <section className="space-y-3" aria-labelledby="invoice-list-heading">
          <div className="flex items-baseline justify-between">
            <h2 id="invoice-list-heading" className="text-sm font-semibold text-text-primary">
              Issued invoices
            </h2>
            <span className="text-xs text-text-muted">{invoices.length} invoices</span>
          </div>

          {isLoading ? (
            <div className="space-y-2 border-t border-border pt-3" aria-label="Loading invoices">
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
            </div>
          ) : error ? (
            <InlineError message={error} onRetry={fetchInvoices} />
          ) : invoices.length === 0 ? (
            <EmptyState
              message="No invoices issued yet"
              description="Approve an order in the Orders inbox and raise a GST invoice."
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="invoices-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Invoice no.</th>
                    <th className="py-2.5 px-3">Date</th>
                    <th className="py-2.5 px-3">Buyer</th>
                    <th className="py-2.5 px-3 text-right">Taxable</th>
                    <th className="py-2.5 px-3 text-right">Tax</th>
                    <th className="py-2.5 px-3 text-right">Total</th>
                    <th className="py-2.5 px-3 text-right">Dispatch</th>
                    <th className="py-2.5 pl-3 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {invoices.map((inv) => {
                    const tax =
                      inv.cgst_total_paise +
                      inv.sgst_total_paise +
                      inv.igst_total_paise;
                    return (
                      <tr
                        key={inv.id}
                        onClick={() => loadInvoice(inv.id)}
                        className="hover:bg-surface-subtle/60 cursor-pointer transition-colors"
                      >
                        <td className="py-2.5 pr-3 font-semibold text-accent">
                          {inv.invoice_no}
                        </td>
                        <td className="py-2.5 px-3 text-text-secondary">
                          {formatIndianDate(inv.invoice_date)}
                        </td>
                        <td className="py-2.5 px-3 font-medium text-text-primary">
                          {inv.buyer_name}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                          {formatIndianCurrency(inv.taxable_total_paise / 100)}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                          {formatIndianCurrency(tax / 100)}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                          {formatIndianCurrency(inv.grand_total_paise / 100)}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <StatusChip
                            label={inv.is_dispatched ? 'DISPATCHED' : 'PENDING'}
                            status={inv.is_dispatched ? 'ok' : 'warning'}
                            size="sm"
                          />
                        </td>
                        <td className="py-2.5 pl-3 text-right">
                          <StatusChip
                            label={inv.status}
                            status={inv.status === 'POSTED' ? 'ok' : 'breach'}
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
      )}
    </div>
  );
};
