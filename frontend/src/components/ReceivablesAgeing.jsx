import React from 'react';
import { IndianRupee, Users, Clock, ArrowUpRight } from 'lucide-react';
import { formatPaise, formatDate } from '../utils/formatters';

export default function ReceivablesAgeing({ receivables }) {
  if (!receivables) return null;

  const {
    total_outstanding_paise = 0,
    bucket_0_30_paise = 0,
    bucket_31_60_paise = 0,
    bucket_61_90_paise = 0,
    bucket_90_plus_paise = 0,
    unallocated_advance_paise = 0,
    top_debtors = [],
  } = receivables;

  const buckets = [
    { label: '0–30 Days', paise: bucket_0_30_paise, color: 'bg-emerald-500', textColor: 'text-emerald-700', bgLight: 'bg-emerald-50' },
    { label: '31–60 Days', paise: bucket_31_60_paise, color: 'bg-blue-500', textColor: 'text-blue-700', bgLight: 'bg-blue-50' },
    { label: '61–90 Days', paise: bucket_61_90_paise, color: 'bg-amber-500', textColor: 'text-amber-700', bgLight: 'bg-amber-50' },
    { label: '90+ Days', paise: bucket_90_plus_paise, color: 'bg-rose-500', textColor: 'text-rose-700', bgLight: 'bg-rose-50' },
  ];

  const grossDues = Math.max(1, bucket_0_30_paise + bucket_31_60_paise + bucket_61_90_paise + bucket_90_plus_paise);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      {/* Receivables & Ageing Breakdown */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
              <IndianRupee className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Receivables & Statutory Ageing</h3>
              <p className="text-xs text-slate-500">Invoice date to as_of date boundary buckets</p>
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs text-slate-400 font-medium">Net Outstanding</div>
            <div className="text-base font-bold text-slate-900">{formatPaise(total_outstanding_paise)}</div>
          </div>
        </div>

        {/* Visual progress bar */}
        <div className="h-3 w-full bg-slate-100 rounded-full overflow-hidden flex mb-4">
          {buckets.map((b, idx) => {
            const pct = (b.paise / grossDues) * 100;
            if (pct <= 0) return null;
            return (
              <div
                key={idx}
                style={{ width: `${pct}%` }}
                className={`${b.color} h-full transition-all`}
                title={`${b.label}: ${formatPaise(b.paise)} (${pct.toFixed(1)}%)`}
              />
            );
          })}
        </div>

        {/* Buckets grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
          {buckets.map((b, idx) => {
            const pct = (b.paise / grossDues) * 100;
            return (
              <div key={idx} className={`p-3 rounded-lg border border-slate-100 ${b.bgLight}`}>
                <div className="text-[11px] font-semibold text-slate-500 mb-1">{b.label}</div>
                <div className={`text-sm font-bold ${b.textColor}`}>{formatPaise(b.paise)}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">{pct.toFixed(1)}% of gross</div>
              </div>
            );
          })}
        </div>

        {unallocated_advance_paise > 0 && (
          <div className="flex items-center justify-between p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs text-slate-600">
            <span className="font-medium">Unallocated Customer Advance (Credit Balance):</span>
            <span className="font-bold text-slate-900">{formatPaise(unallocated_advance_paise)}</span>
          </div>
        )}
      </div>

      {/* Top 5 Customers by Dues */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
              <Users className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Top Debtors (Collection Priority)</h3>
              <p className="text-xs text-slate-500">Customers with highest outstanding balances</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600">
            Top 5
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-400 border-b border-slate-100 font-medium">
                <th className="pb-2.5">Customer Name</th>
                <th className="pb-2.5 text-right font-bold text-slate-700">Total Dues</th>
                <th className="pb-2.5 text-right">Oldest Invoice</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {top_debtors.length === 0 ? (
                <tr>
                  <td colSpan={3} className="py-6 text-center text-slate-400 text-xs">
                    No outstanding customer dues recorded.
                  </td>
                </tr>
              ) : (
                top_debtors.map((c) => (
                  <tr key={c.customer_id} className="hover:bg-slate-50/75 transition-colors">
                    <td className="py-2.5 font-semibold text-slate-900">
                      {c.customer_name}
                    </td>
                    <td className="py-2.5 text-right font-bold text-rose-600">
                      {formatPaise(c.total_outstanding_paise)}
                    </td>
                    <td className="py-2.5 text-right text-slate-500">
                      {formatDate(c.oldest_invoice_date)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
