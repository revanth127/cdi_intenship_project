import React from 'react';
import { Activity, AlertOctagon, CheckCircle2 } from 'lucide-react';
import { formatDateTime, formatPercent, formatQuantity } from '../utils/formatters';

export default function VarianceAlerts({ alerts = [] }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-8">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-rose-50 text-rose-600 rounded-lg">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Production Variance & Yield Alerts (Last 30 Days)</h3>
            <p className="text-xs text-slate-500">
              Flagged consumption lines exceeding tolerance threshold (&gt; 3.00%) — newest first
            </p>
          </div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-rose-100 text-rose-800">
          {alerts.length} Flagged Incident{alerts.length !== 1 ? 's' : ''}
        </span>
      </div>

      {alerts.length === 0 ? (
        <div className="py-8 text-center">
          <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
          <p className="text-sm font-semibold text-slate-800">Zero Variance Excursions</p>
          <p className="text-xs text-slate-500">All recent production batches ran strictly within recipe tolerances.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-400 border-b border-slate-100 font-medium">
                <th className="pb-2.5">Date & Run No</th>
                <th className="pb-2.5">Product Recipe</th>
                <th className="pb-2.5">Material Component</th>
                <th className="pb-2.5 text-right">Planned Qty</th>
                <th className="pb-2.5 text-right">Actual Qty</th>
                <th className="pb-2.5 text-right font-bold">Variance %</th>
                <th className="pb-2.5 text-right">Tolerance</th>
                <th className="pb-2.5 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {alerts.map((item, idx) => {
                const isOver = item.difference_qty_base > 0;
                return (
                  <tr key={idx} className="hover:bg-slate-50/75 transition-colors">
                    <td className="py-2.5">
                      <div className="font-semibold text-slate-900">{item.run_no}</div>
                      <div className="text-[11px] text-slate-400">{formatDateTime(item.run_date)}</div>
                    </td>
                    <td className="py-2.5 font-medium text-slate-700">
                      {item.product_name}
                    </td>
                    <td className="py-2.5">
                      <span className="font-semibold text-slate-900">{item.item_name}</span>
                    </td>
                    <td className="py-2.5 text-right text-slate-500">
                      {formatQuantity(item.planned_qty_base, item.display_unit)}
                    </td>
                    <td className="py-2.5 text-right font-medium text-slate-700">
                      {formatQuantity(item.actual_qty_base, item.display_unit)}
                    </td>
                    <td className="py-2.5 text-right font-bold">
                      <span className={`px-2 py-0.5 rounded ${isOver ? 'text-rose-700 bg-rose-50' : 'text-blue-700 bg-blue-50'}`}>
                        {formatPercent(item.variance_pct)}
                      </span>
                    </td>
                    <td className="py-2.5 text-right text-slate-500">
                      ±{Number(item.tolerance_pct).toFixed(2)}%
                    </td>
                    <td className="py-2.5 text-center">
                      <span className="inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800">
                        <AlertOctagon className="w-3 h-3 mr-1" />
                        FLAGGED
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
