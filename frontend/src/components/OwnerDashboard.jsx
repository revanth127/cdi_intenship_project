import React, { useState, useEffect } from 'react';
import Navbar from './Navbar';
import TodaySnapshot from './TodaySnapshot';
import StockOverview from './StockOverview';
import VarianceAlerts from './VarianceAlerts';
import ReceivablesAgeing from './ReceivablesAgeing';
import CostingMargins from './CostingMargins';
import SalesTrend from './SalesTrend';
import { fetchDashboardSummary } from '../api/client';
import { AlertCircle, RefreshCw } from 'lucide-react';

export default function OwnerDashboard() {
  const [data, setData] = useState(null);
  const [asOf, setAsOf] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadDashboard = async (targetAsOf = asOf) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await fetchDashboardSummary(targetAsOf);
      setData(result);
    } catch (err) {
      console.error('Error fetching dashboard summary:', err);
      setError(err.message || 'Failed to load executive dashboard');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard(asOf);
  }, [asOf]);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 flex flex-col font-sans">
      <Navbar
        asOf={asOf}
        onAsOfChange={(newAsOf) => setAsOf(newAsOf)}
        onRefresh={() => loadDashboard(asOf)}
        isLoading={isLoading}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {error && (
          <div className="mb-6 p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{error}</span>
            </div>
            <button
              onClick={() => loadDashboard(asOf)}
              className="text-xs font-semibold text-rose-700 underline hover:text-rose-900"
            >
              Retry
            </button>
          </div>
        )}

        {isLoading && !data ? (
          <div className="py-24 text-center">
            <RefreshCw className="w-8 h-8 text-amber-500 animate-spin mx-auto mb-3" />
            <h3 className="text-sm font-semibold text-slate-700">Synthesizing Factory Financials...</h3>
            <p className="text-xs text-slate-400">Loading stock ATP, receivables ageing, BOM costs and sales trend</p>
          </div>
        ) : (
          data && (
            <>
              {/* Today's Operational Pulse */}
              <TodaySnapshot today={data.today} />

              {/* Sales Turnover Trend */}
              <SalesTrend trend={data.sales_trend} />

              {/* Finished Goods ATP & Material Reorder */}
              <StockOverview stock={data.stock} />

              {/* Receivables & Statutory Ageing */}
              <ReceivablesAgeing receivables={data.receivables} />

              {/* Product Costing & Commercial Margins */}
              <CostingMargins costing={data.costing} />

              {/* Production Variance Alerts */}
              <VarianceAlerts alerts={data.variance_alerts} />
            </>
          )
        )}
      </main>

      <footer className="bg-white border-t border-slate-200 py-4 text-center text-xs text-slate-400">
        Sri Murugan Traditional Foods Pvt Ltd • Order-to-Audit Enterprise Manufacturing System • Confidential
      </footer>
    </div>
  );
}
