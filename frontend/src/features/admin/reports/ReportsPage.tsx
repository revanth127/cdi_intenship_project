import * as React from 'react';
import { useState, useEffect, useCallback, useMemo } from 'react';
import { apiClient, getAccessToken } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/features/auth/AuthContext';
import { formatIndianCurrency, formatIndianNumber, formatPercentage } from '@/lib/format';
import { FileSpreadsheet, FileText, Table2, RotateCcw, FileDown } from 'lucide-react';

interface ReportMeta {
  name: string;
  title: string;
  scope: string;
  description: string;
}

interface ReportColumn {
  key: string;
  label: string;
  type: string; // string | money_paise | number | percent | bool | date
}

interface ReportResult {
  name: string;
  title: string;
  filters: Record<string, string | null>;
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, unknown>;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function firstOfMonthIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
}
function lastOfMonthIso(): string {
  const d = new Date();
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`;
}

function renderCell(col: ReportColumn, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  switch (col.type) {
    case 'money_paise':
      return formatIndianCurrency(Number(value) / 100);
    case 'number':
      return formatIndianNumber(Number(value));
    case 'percent':
      return formatPercentage(Number(value));
    case 'bool':
      return value ? 'YES' : 'no';
    default:
      return String(value);
  }
}

const EXPORT_FORMATS: { key: string; label: string; icon: React.ElementType }[] = [
  { key: 'xlsx', label: 'Excel', icon: FileSpreadsheet },
  { key: 'csv', label: 'CSV', icon: Table2 },
  { key: 'pdf', label: 'PDF', icon: FileText },
];

export const ReportsPage: React.FC<{ isReadOnly?: boolean }> = () => {
  const { user } = useAuth();
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [from, setFrom] = useState(firstOfMonthIso());
  const [to, setTo] = useState(lastOfMonthIso());
  const [asOf, setAsOf] = useState(todayIso());

  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [preview, setPreview] = useState<ReportResult | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState<string | null>(null);

  // Load report list
  useEffect(() => {
    (async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await apiClient.get<ReportMeta[]>('/reports');
        setReports(data);
        if (data.length && !selectedName) setSelectedName(data[0].name);
      } catch (err: any) {
        setError(err?.message || 'Failed to load reports.');
      } finally {
        setIsLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const queryParams = useMemo(() => {
    const p = new URLSearchParams();
    if (from) p.set('from', from);
    if (to) p.set('to', to);
    if (asOf) p.set('as_of', asOf);
    return p;
  }, [from, to, asOf]);

  const loadPreview = useCallback(async (name: string) => {
    setIsLoadingPreview(true);
    setPreviewError(null);
    try {
      const token = getAccessToken();
      const res = await fetch(`/api/v1/reports/${name}?format=json&${queryParams.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(`Preview failed (${res.status}).`);
      setPreview(await res.json());
    } catch (err: any) {
      setPreviewError(err?.message || 'Failed to load preview.');
      setPreview(null);
    } finally {
      setIsLoadingPreview(false);
    }
  }, [queryParams]);

  useEffect(() => {
    if (selectedName) loadPreview(selectedName);
  }, [selectedName, loadPreview]);

  const download = async (name: string, format: string) => {
    setIsExporting(`${name}:${format}`);
    try {
      const token = getAccessToken();
      const res = await fetch(`/api/v1/reports/${name}?format=${format}&${queryParams.toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (!res.ok) throw new Error(`Export failed (${res.status}).`);
      const blob = await res.blob();
      const ext = format === 'xlsx' ? 'xlsx' : format;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${name}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      setPreviewError(err?.message || 'Export failed.');
    } finally {
      setIsExporting(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Reports &amp; Exports</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            Period-selectable business reports. The same result is exported as CSV, Excel (XLSX) and PDF.
          </p>
        </div>
        <StatusChip label={user?.role === 'PRODUCTION' ? 'STOCK & PRODUCTION' : 'READ-ONLY'} status="neutral" size="sm" />
      </div>

      {/* Period selector */}
      <div className="flex flex-wrap items-end gap-3 border border-border rounded-[6px] bg-surface p-3">
        <div>
          <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="report-from">From (IST)</label>
          <input id="report-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)}
            className="text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="report-to">To (IST)</label>
          <input id="report-to" type="date" value={to} onChange={(e) => setTo(e.target.value)}
            className="text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]" />
        </div>
        <div>
          <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="report-asof">As of (IST)</label>
          <input id="report-asof" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)}
            className="text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]" />
        </div>
        <Button variant="secondary" size="sm" className="h-8 text-xs gap-1.5"
          onClick={() => { setFrom(firstOfMonthIso()); setTo(lastOfMonthIso()); setAsOf(todayIso()); }}>
          <RotateCcw className="w-3.5 h-3.5" /> This month
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2"><Skeleton className="h-8 w-full" /><Skeleton className="h-8 w-full" /></div>
      ) : error ? (
        <InlineError message={error} />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Report list */}
          <div className="space-y-2">
            {reports.map((r) => (
              <div
                key={r.name}
                className={`border rounded-[6px] p-3 bg-surface cursor-pointer transition-colors ${
                  selectedName === r.name ? 'border-accent' : 'border-border hover:bg-surface-subtle'
                }`}
                onClick={() => setSelectedName(r.name)}
                data-testid={`report-${r.name}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold text-text-primary">{r.title}</h2>
                    <p className="text-xs text-text-muted mt-0.5">{r.description}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 mt-2.5">
                  {EXPORT_FORMATS.map((f) => {
                    const Icon = f.icon;
                    const key = `${r.name}:${f.key}`;
                    return (
                      <a
                        key={f.key}
                        href={`/api/v1/reports/${r.name}?format=${f.key}&${queryParams.toString()}`}
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); download(r.name, f.key); }}
                        className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded-[4px] border border-border text-text-secondary hover:text-accent hover:border-accent"
                        data-testid={`export-${r.name}-${f.key}`}
                      >
                        <Icon className="w-3 h-3" />
                        {isExporting === key ? 'Exporting…' : f.label}
                      </a>
                    );
                  })}
                  <span className="inline-flex items-center gap-1 text-[11px] px-2 py-1 text-text-muted">
                    <FileDown className="w-3 h-3" /> CSV · XLSX · PDF
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* On-screen preview */}
          <div className="border border-border rounded-[6px] bg-surface min-w-0">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <h2 className="text-sm font-semibold text-text-primary">
                {preview?.title || 'Preview'}
              </h2>
              {preview && (
                <span className="text-[11px] text-text-muted">
                  {preview.rows.length} rows
                  {typeof preview.totals?.row_count === 'number' ? ` · total rows ${preview.totals.row_count}` : ''}
                </span>
              )}
            </div>
            {isLoadingPreview ? (
              <div className="p-4 space-y-2"><Skeleton className="h-6 w-full" /><Skeleton className="h-6 w-full" /></div>
            ) : previewError ? (
              <div className="p-4"><InlineError message={previewError} /></div>
            ) : preview ? (
              <div className="overflow-auto max-h-[60vh]">
                <table className="w-full text-xs" data-testid="report-preview-table">
                  <thead className="sticky top-0 bg-surface">
                    <tr className="border-b border-border text-text-secondary text-left font-semibold">
                      {preview.columns.map((c) => (
                        <th key={c.key} className={`py-2 px-3 whitespace-nowrap ${c.type === 'money_paise' || c.type === 'number' || c.type === 'percent' ? 'text-right' : ''}`}>
                          {c.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {preview.rows.slice(0, 200).map((row, i) => (
                      <tr key={i}>
                        {preview.columns.map((c) => (
                          <td key={c.key} className={`py-1.5 px-3 whitespace-nowrap ${c.type === 'money_paise' || c.type === 'number' || c.type === 'percent' ? 'text-right tabular-nums' : ''}`}>
                            {renderCell(c, row[c.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                    {preview.rows.length === 0 && (
                      <tr><td colSpan={preview.columns.length} className="py-4 px-3 text-center text-text-muted">No rows in this period.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="p-4 text-xs text-text-muted">Select a report to preview.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
