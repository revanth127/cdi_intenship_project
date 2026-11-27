import React from 'react';
import { RefreshCw, ShieldCheck, Factory, Calendar } from 'lucide-react';
import { formatDate } from '../utils/formatters';

export default function Navbar({ asOf, onAsOfChange, onRefresh, isLoading }) {
  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand info */}
          <div className="flex items-center space-x-3">
            <div className="h-10 w-10 rounded-lg bg-amber-600 flex items-center justify-center text-white shadow-sm font-bold text-lg">
              SM
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-900 tracking-tight text-lg">
                  Sri Murugan Traditional Foods
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-emerald-100 text-emerald-800">
                  <ShieldCheck className="w-3 h-3 mr-1" />
                  Audit-Ready
                </span>
              </div>
              <p className="text-xs text-slate-500">Order-to-Audit Factory Executive Suite • Owner Command Center</p>
            </div>
          </div>

          {/* Controls: as_of date picker & refresh */}
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-200 text-sm">
              <Calendar className="w-4 h-4 text-slate-500" />
              <label htmlFor="asOfInput" className="text-xs font-medium text-slate-600">As Of:</label>
              <input
                id="asOfInput"
                type="date"
                value={asOf ? asOf.split('T')[0] : ''}
                onChange={(e) => onAsOfChange(e.target.value ? `${e.target.value}T23:59:59Z` : null)}
                className="bg-transparent border-none text-xs font-medium text-slate-800 focus:outline-none"
              />
              {asOf && (
                <button
                  onClick={() => onAsOfChange(null)}
                  className="text-xs text-slate-400 hover:text-slate-600 font-semibold"
                  title="Reset to current live time"
                >
                  Live
                </button>
              )}
            </div>

            <button
              onClick={onRefresh}
              disabled={isLoading}
              className="inline-flex items-center px-3 py-1.5 border border-slate-300 shadow-sm text-xs font-medium rounded-lg text-slate-700 bg-white hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-500 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 text-slate-500 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>

            <div className="hidden md:flex items-center pl-2 border-l border-slate-200">
              <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-slate-900 text-white">
                OWNER
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
