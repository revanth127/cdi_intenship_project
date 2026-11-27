import React from 'react';
import { ShoppingBag, Clock, FileText, Truck, CreditCard, ArrowUpRight } from 'lucide-react';
import { formatPaise } from '../utils/formatters';

export default function TodaySnapshot({ today }) {
  if (!today) return null;

  const metrics = [
    {
      title: "Today's Orders Received",
      value: today.orders_received_count,
      subtext: formatPaise(today.orders_received_value_paise),
      icon: ShoppingBag,
      color: "text-blue-600",
      bgColor: "bg-blue-50",
      borderColor: "border-blue-100",
    },
    {
      title: "Pending Approval",
      value: today.orders_pending_approval_count,
      subtext: today.orders_pending_approval_count > 0 ? "Requires Admin Action" : "All Approved",
      icon: Clock,
      color: today.orders_pending_approval_count > 0 ? "text-amber-600" : "text-emerald-600",
      bgColor: today.orders_pending_approval_count > 0 ? "bg-amber-50" : "bg-emerald-50",
      borderColor: today.orders_pending_approval_count > 0 ? "border-amber-200" : "border-emerald-100",
      highlight: today.orders_pending_approval_count > 0,
    },
    {
      title: "GST Invoices Raised",
      value: today.invoices_raised_count,
      subtext: formatPaise(today.invoices_raised_value_paise),
      icon: FileText,
      color: "text-indigo-600",
      bgColor: "bg-indigo-50",
      borderColor: "border-indigo-100",
    },
    {
      title: "Dispatches Made",
      value: today.dispatches_made_count,
      subtext: `${today.dispatches_made_count} delivery orders out`,
      icon: Truck,
      color: "text-cyan-600",
      bgColor: "bg-cyan-50",
      borderColor: "border-cyan-100",
    },
    {
      title: "Payments Collected",
      value: formatPaise(today.payments_collected_paise),
      subtext: `${today.payments_collected_count} receipts recorded`,
      icon: CreditCard,
      color: "text-emerald-600",
      bgColor: "bg-emerald-50",
      borderColor: "border-emerald-100",
    },
  ];

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold text-slate-900 tracking-tight">Today's Pulse ({today.date})</h2>
          <p className="text-xs text-slate-500">Real-time factory receipts, order inflows, tax dispatches & collection cash flow</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        {metrics.map((m, idx) => {
          const Icon = m.icon;
          return (
            <div
              key={idx}
              className={`bg-white rounded-xl p-4 border shadow-sm transition-all hover:shadow-md ${
                m.highlight ? 'border-amber-300 ring-2 ring-amber-100' : 'border-slate-200'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs font-medium text-slate-500">{m.title}</span>
                <div className={`p-2 rounded-lg ${m.bgColor} ${m.color}`}>
                  <Icon className="w-4 h-4" />
                </div>
              </div>
              <div className="text-2xl font-bold text-slate-900 tracking-tight mb-1">
                {m.value}
              </div>
              <div className="text-xs font-medium text-slate-500 flex items-center">
                <span>{m.subtext}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
