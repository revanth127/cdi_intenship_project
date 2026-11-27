import React from 'react';
import { Percent, TrendingUp, DollarSign } from 'lucide-react';
import { formatRupees } from '../utils/formatters';

export default function CostingMargins({ costing = [] }) {
  if (!costing || costing.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-8">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
        <div className="flex items-center space-x-2">
          <div className="p-2 bg-emerald-50 text-emerald-600 rounded-lg">
            <Percent className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">Product Costing & Commercial Margins</h3>
            <p className="text-xs text-slate-500">
              Weighted cost per packet (materials from stock ledger + absorbed overheads) vs selling price
            </p>
          </div>
        </div>
        <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800">
          Gross Profit Analysis
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {costing.map((prod) => {
          const marginPct = Number(prod.margin_pct);
          const isHealthy = marginPct >= 30;

          return (
            <div
              key={prod.product_id}
              className="p-4 rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 hover:border-slate-300 transition-all shadow-sm"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="font-bold text-slate-900 text-sm">{prod.product_name}</span>
                <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                  isHealthy ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                }`}>
                  {marginPct.toFixed(1)}% Margin
                </span>
              </div>

              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between text-slate-500">
                  <span>Selling Price (Excl. Tax):</span>
                  <span className="font-semibold text-slate-800">{formatRupees(prod.selling_price)} / pkt</span>
                </div>
                <div className="flex items-center justify-between text-slate-500">
                  <span>Weighted Cost Per Packet:</span>
                  <span className="font-semibold text-slate-800">{formatRupees(prod.cost_per_packet)} / pkt</span>
                </div>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between font-bold">
                  <span className="text-slate-700">Gross Margin Per Packet:</span>
                  <span className="text-emerald-600 text-sm">{formatRupees(prod.margin_per_packet)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
