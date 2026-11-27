import React from 'react';
import { Package, AlertTriangle, CheckCircle, ArrowRight } from 'lucide-react';
import { formatQuantity } from '../utils/formatters';

export default function StockOverview({ stock }) {
  if (!stock) return null;
  const { finished_goods = [], reorder_alerts = [] } = stock;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
      {/* Finished Goods Available-To-Promise (ATP) */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
              <Package className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Finished Goods & ATP</h3>
              <p className="text-xs text-slate-500">Available-To-Promise prevents over-committing warehouse stock</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
            {finished_goods.length} SKU{finished_goods.length !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-400 border-b border-slate-100 font-medium">
                <th className="pb-2.5">Product SKU</th>
                <th className="pb-2.5 text-right">On Hand</th>
                <th className="pb-2.5 text-right">Committed</th>
                <th className="pb-2.5 text-right font-bold text-slate-700">Available (ATP)</th>
                <th className="pb-2.5 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {finished_goods.map((fg) => {
                const isHealthy = fg.available_to_promise_packets > 20;
                return (
                  <tr key={fg.product_id} className="hover:bg-slate-50/75 transition-colors">
                    <td className="py-2.5">
                      <div className="font-semibold text-slate-900">{fg.product_name}</div>
                      <div className="text-[11px] text-slate-400">Pack: {fg.pack_size_desc}</div>
                    </td>
                    <td className="py-2.5 text-right font-medium text-slate-700">
                      {fg.on_hand_packets.toLocaleString('en-IN')} pkts
                    </td>
                    <td className="py-2.5 text-right text-slate-500">
                      {fg.committed_packets.toLocaleString('en-IN')} pkts
                    </td>
                    <td className="py-2.5 text-right font-bold text-slate-900">
                      <span className={`px-2 py-0.5 rounded ${isHealthy ? 'text-emerald-700 bg-emerald-50' : 'text-amber-700 bg-amber-50'}`}>
                        {fg.available_to_promise_packets.toLocaleString('en-IN')} pkts
                      </span>
                    </td>
                    <td className="py-2.5 text-center">
                      {isHealthy ? (
                        <span className="inline-flex items-center text-[11px] font-medium text-emerald-600">
                          <CheckCircle className="w-3.5 h-3.5 mr-1" />
                          Ready
                        </span>
                      ) : (
                        <span className="inline-flex items-center text-[11px] font-medium text-amber-600">
                          <AlertTriangle className="w-3.5 h-3.5 mr-1" />
                          Low
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Raw Materials & Packaging Reorder Alerts */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-amber-50 text-amber-600 rounded-lg">
              <AlertTriangle className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Inventory Reorder & Shortage Alerts</h3>
              <p className="text-xs text-slate-500">Critical ingredients and packaging below buffer levels</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-rose-50 text-rose-700 border border-rose-100">
            {reorder_alerts.length} Alert{reorder_alerts.length !== 1 ? 's' : ''}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="text-slate-400 border-b border-slate-100 font-medium">
                <th className="pb-2.5">Material / Supply</th>
                <th className="pb-2.5">Type</th>
                <th className="pb-2.5 text-right">Current Stock</th>
                <th className="pb-2.5 text-right">Reorder Level</th>
                <th className="pb-2.5 text-right font-bold text-rose-600">Deficit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {reorder_alerts.length === 0 ? (
                <tr>
                  <td colSpan={5} className="py-6 text-center text-slate-400 text-xs">
                    All inventory levels are above reorder thresholds.
                  </td>
                </tr>
              ) : (
                reorder_alerts.map((item) => (
                  <tr key={item.item_id} className="hover:bg-slate-50/75 transition-colors">
                    <td className="py-2.5 font-semibold text-slate-900">
                      {item.item_name}
                    </td>
                    <td className="py-2.5">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                        item.item_type === 'RAW_MATERIAL' ? 'bg-amber-100 text-amber-800' : 'bg-purple-100 text-purple-800'
                      }`}>
                        {item.item_type === 'RAW_MATERIAL' ? 'RAW' : 'PACK'}
                      </span>
                    </td>
                    <td className="py-2.5 text-right font-medium text-slate-700">
                      {formatQuantity(item.current_stock_base, item.base_unit)}
                    </td>
                    <td className="py-2.5 text-right text-slate-500">
                      {item.reorder_level_base !== null ? formatQuantity(item.reorder_level_base, item.base_unit) : 'N/A'}
                    </td>
                    <td className="py-2.5 text-right font-bold text-rose-600">
                      {item.deficit_base !== null && item.deficit_base > 0
                        ? `-${formatQuantity(item.deficit_base, item.base_unit)}`
                        : 'Buffer'}
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
