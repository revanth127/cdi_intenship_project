import React, { useState } from 'react';
import { BarChart3, TrendingUp, Calendar } from 'lucide-react';
import { formatRupees, formatPaise } from '../utils/formatters';

export default function SalesTrend({ trend = [] }) {
  if (!trend || trend.length === 0) return null;

  const [hoveredDay, setHoveredDay] = useState(null);

  // Compute max taxable sales for scaling
  const maxSales = Math.max(1, ...trend.map(t => Number(t.taxable_sales_rupees || 0)));
  const totalPeriodSales = trend.reduce((acc, t) => acc + (t.taxable_sales_paise || 0), 0);
  const totalInvoices = trend.reduce((acc, t) => acc + (t.invoice_count || 0), 0);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-8">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 pb-4 border-b border-slate-100 gap-3">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-blue-50 text-blue-600 rounded-lg">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">30-Day Sales Trend (Taxable Turnover)</h3>
            <p className="text-xs text-slate-500">Daily taxable revenue from posted GST invoices</p>
          </div>
        </div>

        <div className="flex items-center space-x-4 text-xs">
          <div className="bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200">
            <span className="text-slate-500 mr-1.5">30-Day Taxable:</span>
            <span className="font-bold text-slate-900">{formatPaise(totalPeriodSales)}</span>
          </div>
          <div className="bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200">
            <span className="text-slate-500 mr-1.5">Invoices Raised:</span>
            <span className="font-bold text-slate-900">{totalInvoices}</span>
          </div>
        </div>
      </div>

      {/* Visual Bar Chart */}
      <div className="h-44 w-full flex items-end space-x-1.5 pt-6 pb-2 px-1">
        {trend.map((day, idx) => {
          const val = Number(day.taxable_sales_rupees || 0);
          const heightPct = Math.max(4, Math.round((val / maxSales) * 100));
          const isToday = idx === trend.length - 1;
          const isHovered = hoveredDay && hoveredDay.date === day.date;

          return (
            <div
              key={day.date}
              onMouseEnter={() => setHoveredDay(day)}
              onMouseLeave={() => setHoveredDay(null)}
              className="flex-1 flex flex-col items-center h-full justify-end group cursor-pointer relative"
            >
              {/* Tooltip */}
              {isHovered && (
                <div className="absolute bottom-full mb-2 z-20 bg-slate-900 text-white rounded-lg px-2.5 py-1.5 text-[11px] whitespace-nowrap shadow-xl pointer-events-none">
                  <div className="font-semibold">{day.date}</div>
                  <div>Sales: {formatRupees(day.taxable_sales_rupees)}</div>
                  <div className="text-slate-400">{day.invoice_count} invoice(s)</div>
                </div>
              )}

              {/* Bar */}
              <div
                style={{ height: `${heightPct}%` }}
                className={`w-full rounded-t transition-all ${
                  isToday
                    ? 'bg-amber-500 hover:bg-amber-600'
                    : val > 0
                    ? 'bg-blue-500 hover:bg-blue-600'
                    : 'bg-slate-100 hover:bg-slate-200'
                }`}
              />
            </div>
          );
        })}
      </div>

      {/* Date labels */}
      <div className="flex justify-between text-[10px] text-slate-400 pt-2 border-t border-slate-100 px-1 font-mono">
        <span>{trend[0]?.date}</span>
        <span>15 Days Ago</span>
        <span className="font-bold text-amber-600">Today ({trend[trend.length - 1]?.date})</span>
      </div>
    </div>
  );
}
