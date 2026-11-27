import * as React from 'react';
import { useState, useEffect } from 'react';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import {
  formatIndianCurrency,
  formatIndianNumber,
  formatQuantityWithUnit,
  formatPercentage,
} from '@/lib/format';
import {
  Plus,
  ArrowLeft,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  Factory,
  Save,
  Send,
  Layers,
  Flame,
  Zap,
  Users,
} from 'lucide-react';
import { cn } from '@/components/ui/button';

interface Product {
  id: number;
  name: string;
  pack_size: string;
  item_id: number;
}

interface LineVarianceReport {
  item_id: number;
  item_name: string;
  display_unit: string;
  planned_qty_base: number;
  actual_qty_base?: number;
  difference_qty_base?: number;
  variance_pct?: number;
  tolerance_pct: number;
  is_flagged: boolean;
  damaged_qty_base: number;
  unit_cost_paise?: number;
  value_paise?: number;
}

interface YieldVarianceReport {
  expected_output_packets: number;
  actual_good_packets?: number;
  wastage_packets?: number;
  yield_variance_pct?: number;
  tolerance_pct: number;
  is_flagged: boolean;
}

interface ProductionRunLine {
  id: number;
  run_id: number;
  item_id: number;
  planned_qty_base: number;
  actual_qty_base?: number;
  damaged_qty_base: number;
  variance_qty_base?: number;
  variance_pct?: number;
  is_flagged: boolean;
  unit_cost?: number;
  value_paise?: number;
  unit_for_display: string;
  item?: {
    id: number;
    name: string;
    item_type: string;
    display_unit: string;
    base_unit: string;
  };
}

interface ProductionRun {
  id: number;
  run_no: string;
  product_id: number;
  bom_id: number;
  bom_version: number;
  run_date: string;
  batches: number;
  batch_size_packets?: number;
  expected_output_packets: number;
  actual_good_packets?: number;
  wastage_packets?: number;
  yield_variance_pct?: number;
  is_yield_flagged: boolean;
  status: 'DRAFT' | 'POSTED' | 'CANCELLED';
  notes?: string;
  product?: {
    id: number;
    name: string;
    pack_size: string;
  };
  lines: ProductionRunLine[];
  variance_report?: {
    yield_report: YieldVarianceReport;
    lines: LineVarianceReport[];
  };
}

interface RunCostDetail {
  run_id: number;
  run_no: string;
  product_name: string;
  good_packets: number;
  total_material_cost_paise: number;
  direct_overheads_paise: number;
  allocated_overheads_paise: number;
  total_overheads_paise: number;
  total_cost_paise: number;
  cost_per_packet: string;
  planned_cost_per_packet: string;
  cost_of_loss_paise: number;
}

interface ProductCostSummary {
  product_id: number;
  product_name: string;
  cost_per_packet: string;
  selling_price: string;
  margin_per_packet: string;
  margin_pct: string;
}

export const ProductionOperationsPage: React.FC = () => {
  const [runs, setRuns] = useState<ProductionRun[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selected run for detail / edit / results
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedRun, setSelectedRun] = useState<ProductionRun | null>(null);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  // New run dialog state
  const [showNewModal, setShowNewModal] = useState(false);
  const [newProductId, setNewProductId] = useState<number | ''>('');
  const [newBatches, setNewBatches] = useState('1.0');
  const [newNotes, setNewNotes] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Draft inputs
  const [editableActualGood, setEditableActualGood] = useState<string>('');
  const [editableLines, setEditableLines] = useState<
    { item_id: number; actual_qty: string; damaged_qty: string }[]
  >([]);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isPostingRun, setIsPostingRun] = useState(false);
  const [actionMessage, setActionMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Overheads form state
  const [overheadCategory, setOverheadCategory] = useState<'LABOUR' | 'GAS' | 'POWER' | 'OTHER'>('LABOUR');
  const [overheadAmount, setOverheadAmount] = useState('');
  const [overheadDescription, setOverheadDescription] = useState('');
  const [isRecordingOverhead, setIsRecordingOverhead] = useState(false);
  const [overheadError, setOverheadError] = useState<string | null>(null);

  // Cost sheet data
  const [costDetail, setCostDetail] = useState<RunCostDetail | null>(null);
  const [productCostSummary, setProductCostSummary] = useState<ProductCostSummary | null>(null);

  const fetchRunsAndProducts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [runsData, productsData] = await Promise.all([
        apiClient.get<ProductionRun[]>('/production'),
        apiClient.get<Product[]>('/products'),
      ]);
      setRuns(runsData);
      setProducts(productsData);
    } catch (err: any) {
      setError(err?.message || 'Failed to load production runs.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRunsAndProducts();
  }, []);

  const loadRunDetail = async (runId: number) => {
    setSelectedRunId(runId);
    setIsLoadingRun(true);
    setRunError(null);
    setActionMessage(null);
    try {
      const run = await apiClient.get<ProductionRun>(`/production/${runId}`);
      setSelectedRun(run);
      setEditableActualGood(
        run.actual_good_packets !== null && run.actual_good_packets !== undefined
          ? String(run.actual_good_packets)
          : String(run.expected_output_packets || '')
      );
      setEditableLines(
        run.lines.map((l) => ({
          item_id: l.item_id,
          actual_qty:
            l.actual_qty_base !== null && l.actual_qty_base !== undefined
              ? String(l.actual_qty_base)
              : String(l.planned_qty_base),
          damaged_qty: String(l.damaged_qty_base || 0),
        }))
      );

      // If posted, load costing
      if (run.status === 'POSTED') {
        loadCosting(run.id, run.product_id);
      } else {
        setCostDetail(null);
        setProductCostSummary(null);
      }
    } catch (err: any) {
      setRunError(err?.message || `Failed to load details for run #${runId}.`);
    } finally {
      setIsLoadingRun(false);
    }
  };

  const loadCosting = async (runId: number, productId: number) => {
    try {
      const [costData, productData] = await Promise.all([
        apiClient.get<RunCostDetail>(`/costing/runs/${runId}`),
        apiClient.get<ProductCostSummary[]>(`/costing/products?product_id=${productId}`),
      ]);
      setCostDetail(costData);
      if (productData && productData.length > 0) {
        setProductCostSummary(productData[0]);
      }
    } catch {
      // Costing read may fail or be empty
    }
  };

  const handleCreateRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProductId) {
      setCreateError('Please select a product.');
      return;
    }
    const batchesNum = parseFloat(newBatches);
    if (isNaN(batchesNum) || batchesNum <= 0) {
      setCreateError('Batches must be a positive number.');
      return;
    }

    setIsCreating(true);
    setCreateError(null);
    try {
      const newRun = await apiClient.post<ProductionRun>('/production', {
        product_id: Number(newProductId),
        batches: batchesNum,
        notes: newNotes.trim() || undefined,
      });

      setShowNewModal(false);
      setNewProductId('');
      setNewBatches('1.0');
      setNewNotes('');

      // Refresh list and open new run in edit mode
      await fetchRunsAndProducts();
      await loadRunDetail(newRun.id);
    } catch (err: any) {
      setCreateError(err?.message || 'Failed to initialize production run from BOM.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!selectedRun) return;
    setIsSavingDraft(true);
    setActionMessage(null);
    try {
      const payload = {
        actual_good_packets: editableActualGood ? parseInt(editableActualGood, 10) : undefined,
        lines: editableLines.map((l) => ({
          item_id: l.item_id,
          actual_qty_base: l.actual_qty ? parseInt(l.actual_qty, 10) : undefined,
          damaged_qty_base: l.damaged_qty ? parseInt(l.damaged_qty, 10) : 0,
        })),
      };
      const updated = await apiClient.patch<ProductionRun>(`/production/${selectedRun.id}`, payload);
      setSelectedRun(updated);
      setActionMessage({ text: 'Draft updated and variances recalculated.', type: 'success' });
      fetchRunsAndProducts();
    } catch (err: any) {
      setActionMessage({ text: err?.message || 'Failed to save draft.', type: 'error' });
    } finally {
      setIsSavingDraft(false);
    }
  };

  const handlePostRun = async () => {
    if (!selectedRun) return;
    if (
      !window.confirm(
        'Post this production run? This will atomically issue materials from stock and post finished goods to inventory.'
      )
    ) {
      return;
    }

    setIsPostingRun(true);
    setActionMessage(null);
    try {
      // First save current inputs
      const payload = {
        actual_good_packets: editableActualGood ? parseInt(editableActualGood, 10) : undefined,
        lines: editableLines.map((l) => ({
          item_id: l.item_id,
          actual_qty_base: l.actual_qty ? parseInt(l.actual_qty, 10) : undefined,
          damaged_qty_base: l.damaged_qty ? parseInt(l.damaged_qty, 10) : 0,
        })),
      };
      await apiClient.patch<ProductionRun>(`/production/${selectedRun.id}`, payload);

      // Now post atomically
      const posted = await apiClient.post<ProductionRun>(`/production/${selectedRun.id}/post`);
      setSelectedRun(posted);
      setActionMessage({
        text: 'Production run posted successfully! Stock movements recorded atomically.',
        type: 'success',
      });
      fetchRunsAndProducts();
      loadCosting(posted.id, posted.product_id);
    } catch (err: any) {
      setActionMessage({ text: err?.message || 'Failed to post production run.', type: 'error' });
    } finally {
      setIsPostingRun(false);
    }
  };

  const handleRecordOverhead = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRun) return;
    const amountNum = parseFloat(overheadAmount);
    if (isNaN(amountNum) || amountNum <= 0) {
      setOverheadError('Please enter a valid amount.');
      return;
    }

    setIsRecordingOverhead(true);
    setOverheadError(null);
    try {
      await apiClient.post('/overheads', {
        category: overheadCategory,
        amount_paise: Math.round(amountNum * 100),
        production_run_id: selectedRun.id,
        description: overheadDescription.trim() || undefined,
      });

      setOverheadAmount('');
      setOverheadDescription('');
      loadCosting(selectedRun.id, selectedRun.product_id);
      setActionMessage({ text: `Recorded ${overheadCategory} overhead expenditure.`, type: 'success' });
    } catch (err: any) {
      setOverheadError(err?.message || 'Failed to record overhead expenditure.');
    } finally {
      setIsRecordingOverhead(false);
    }
  };

  // Helper for live line variance calculation
  const getLineLiveVariance = (planned: number, actualStr: string, tolerance: number = 3.0) => {
    const actual = parseFloat(actualStr);
    if (isNaN(actual) || planned <= 0) return { pct: 0, isFlagged: false };
    const diff = actual - planned;
    const pct = (diff / planned) * 100;
    const isFlagged = Math.abs(pct) > tolerance;
    return { pct, isFlagged };
  };

  const getYieldLiveVariance = (expected: number, actualGoodStr: string, tolerance: number = 3.0) => {
    const actual = parseFloat(actualGoodStr);
    if (isNaN(actual) || expected <= 0) return { pct: 0, isFlagged: false, wastage: 0 };
    const diff = actual - expected;
    const pct = (diff / expected) * 100;
    const isFlagged = Math.abs(pct) > tolerance;
    const wastage = expected - actual;
    return { pct, isFlagged, wastage };
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Production Operations</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            BOM batch scaling, actual vs planned consumption tracking, live tolerance alerts, and batch costing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {selectedRunId && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setSelectedRunId(null);
                setSelectedRun(null);
              }}
              className="h-8 text-xs gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>All Runs</span>
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => setShowNewModal(true)}
            className="h-8 text-xs gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Production Run</span>
          </Button>
        </div>
      </div>

      {/* New Run Modal */}
      {showNewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-surface border border-border rounded-[6px] max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Factory className="w-4 h-4 text-accent" />
                <span>Initialize Production Run</span>
              </h2>
              <button
                type="button"
                onClick={() => setShowNewModal(false)}
                className="text-text-muted hover:text-text-primary text-xs"
              >
                ✕
              </button>
            </div>

            {createError && <InlineError message={createError} />}

            <form onSubmit={handleCreateRun} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Product / Pack Size <span className="text-red-500">*</span>
                </label>
                <select
                  value={newProductId}
                  onChange={(e) => setNewProductId(e.target.value ? Number(e.target.value) : '')}
                  required
                  className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
                >
                  <option value="">Select Finished Good Product</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.pack_size})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">
                  Batches to Produce <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="0.0001"
                  min="0.1"
                  value={newBatches}
                  onChange={(e) => setNewBatches(e.target.value)}
                  required
                  className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
                />
                <span className="text-[11px] text-text-muted">
                  Scales BOM standard quantities proportionally (e.g. 1.0 = standard batch).
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1">Notes / Batch Tag</label>
                <input
                  type="text"
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  placeholder="e.g. Morning Shift Batch 1"
                  className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-border">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => setShowNewModal(false)}
                  className="text-xs h-8"
                >
                  Cancel
                </Button>
                <Button type="submit" size="sm" disabled={isCreating} className="text-xs h-8">
                  {isCreating ? 'Creating Run...' : 'Create Run'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Action Notification */}
      {actionMessage && (
        <div
          className={cn(
            'p-3 rounded-[6px] text-xs flex items-center gap-2 border',
            actionMessage.type === 'success'
              ? 'bg-emerald-50 text-emerald-900 border-emerald-200'
              : 'bg-status-breach-bg text-status-breach-text border-status-breach-border'
          )}
        >
          {actionMessage.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-status-breach-text shrink-0" />
          )}
          <span className="font-medium">{actionMessage.text}</span>
        </div>
      )}

      {selectedRunId && selectedRun ? (
        /* Run Detail / Draft Edit & Results View */
        <div className="space-y-6">
          {/* Top Run Header Status Strip */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-border pb-4">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-text-primary tracking-tight">
                  {selectedRun.run_no}
                </h2>
                <StatusChip
                  label={selectedRun.status}
                  status={
                    selectedRun.status === 'POSTED'
                      ? 'ok'
                      : selectedRun.status === 'DRAFT'
                      ? 'neutral'
                      : 'breach'
                  }
                  size="sm"
                />
              </div>
              <p className="text-xs text-text-secondary mt-0.5">
                Product: <span className="font-semibold text-text-primary">{selectedRun.product?.name || `Product #${selectedRun.product_id}`}</span>{' '}
                • BOM v{selectedRun.bom_version} • Batches: {selectedRun.batches} • Run Date:{' '}
                {new Date(selectedRun.run_date).toLocaleDateString('en-IN')}
              </p>
            </div>

            {selectedRun.status === 'DRAFT' && (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleSaveDraft}
                  disabled={isSavingDraft}
                  className="text-xs h-8 gap-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>{isSavingDraft ? 'Saving...' : 'Save Draft'}</span>
                </Button>
                <Button
                  size="sm"
                  onClick={handlePostRun}
                  disabled={isPostingRun}
                  className="text-xs h-8 gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{isPostingRun ? 'Posting...' : 'Post Run'}</span>
                </Button>
              </div>
            )}
          </div>

          {/* Yield & Output Card */}
          <div className="bg-surface border border-border rounded-[6px] p-4 space-y-3">
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
              Finished Goods Output & Yield
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div>
                <span className="text-xs text-text-muted block">Expected Output</span>
                <span className="text-sm font-semibold text-text-primary tabular-nums">
                  {formatIndianNumber(selectedRun.expected_output_packets)} packets
                </span>
              </div>

              <div>
                <label className="text-xs text-text-muted block font-medium">Actual Good Packets</label>
                {selectedRun.status === 'DRAFT' ? (
                  <input
                    type="number"
                    min="0"
                    value={editableActualGood}
                    onChange={(e) => setEditableActualGood(e.target.value)}
                    className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] mt-1 tabular-nums font-semibold"
                  />
                ) : (
                  <span className="text-sm font-semibold text-accent tabular-nums block mt-1">
                    {formatIndianNumber(selectedRun.actual_good_packets)} packets
                  </span>
                )}
              </div>

              <div>
                <span className="text-xs text-text-muted block">Packaging Wastage</span>
                <span className="text-sm font-medium text-amber-700 tabular-nums block mt-1">
                  {selectedRun.status === 'DRAFT'
                    ? `${getYieldLiveVariance(selectedRun.expected_output_packets, editableActualGood).wastage} packets`
                    : `${selectedRun.wastage_packets ?? 0} packets`}
                </span>
              </div>

              <div>
                <span className="text-xs text-text-muted block">Yield Variance</span>
                <div className="mt-1 flex items-center gap-2">
                  {(() => {
                    const yv =
                      selectedRun.status === 'DRAFT'
                        ? getYieldLiveVariance(selectedRun.expected_output_packets, editableActualGood)
                        : {
                            pct: selectedRun.yield_variance_pct ?? 0,
                            isFlagged: selectedRun.is_yield_flagged,
                          };
                    return (
                      <>
                        <span className="text-sm font-semibold tabular-nums">
                          {formatPercentage(yv.pct, true)}
                        </span>
                        <StatusChip
                          label={yv.isFlagged ? 'EXCEEDED TOLERANCE' : 'WITHIN TOLERANCE'}
                          status={yv.isFlagged ? 'breach' : 'ok'}
                          size="sm"
                        />
                      </>
                    );
                  })()}
                </div>
              </div>
            </div>
          </div>

          {/* BOM Material Lines Table */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                Material & Packaging Consumption
              </h3>
              <span className="text-xs text-text-muted">Tolerance threshold: ±3.0%</span>
            </div>

            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="production-lines-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Material Item</th>
                    <th className="py-2.5 px-3">Unit</th>
                    <th className="py-2.5 px-3 text-right">Planned Qty</th>
                    <th className="py-2.5 px-3 text-right w-36">Actual Consumed</th>
                    <th className="py-2.5 px-3 text-right w-28">Damaged Qty</th>
                    <th className="py-2.5 px-3 text-right">Live Variance</th>
                    <th className="py-2.5 pl-3 text-center">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {selectedRun.lines.map((line, idx) => {
                    const lineState = editableLines.find((l) => l.item_id === line.item_id) || {
                      item_id: line.item_id,
                      actual_qty: String(line.actual_qty_base || line.planned_qty_base),
                      damaged_qty: String(line.damaged_qty_base || 0),
                    };

                    const liveVar = getLineLiveVariance(line.planned_qty_base, lineState.actual_qty);

                    return (
                      <tr key={line.id} className="hover:bg-surface-subtle/50 transition-colors">
                        <td className="py-2.5 pr-3 font-semibold text-text-primary">
                          {line.item?.name || `Item #${line.item_id}`}
                        </td>
                        <td className="py-2.5 px-3 text-text-muted font-mono">{line.unit_for_display}</td>
                        <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                          {formatIndianNumber(line.planned_qty_base)}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          {selectedRun.status === 'DRAFT' ? (
                            <input
                              type="number"
                              min="0"
                              value={lineState.actual_qty}
                              onChange={(e) => {
                                const val = e.target.value;
                                setEditableLines((prev) =>
                                  prev.map((l) => (l.item_id === line.item_id ? { ...l, actual_qty: val } : l))
                                );
                              }}
                              className="w-full text-xs h-7 px-2 bg-surface border border-border rounded-[4px] text-right font-semibold tabular-nums"
                            />
                          ) : (
                            <span className="font-semibold text-text-primary tabular-nums">
                              {formatIndianNumber(line.actual_qty_base)}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          {selectedRun.status === 'DRAFT' ? (
                            <input
                              type="number"
                              min="0"
                              value={lineState.damaged_qty}
                              onChange={(e) => {
                                const val = e.target.value;
                                setEditableLines((prev) =>
                                  prev.map((l) => (l.item_id === line.item_id ? { ...l, damaged_qty: val } : l))
                                );
                              }}
                              className="w-full text-xs h-7 px-2 bg-surface border border-border rounded-[4px] text-right text-amber-700 tabular-nums"
                            />
                          ) : (
                            <span className="text-amber-700 tabular-nums">
                              {formatIndianNumber(line.damaged_qty_base)}
                            </span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-right font-semibold tabular-nums">
                          {selectedRun.status === 'DRAFT'
                            ? formatPercentage(liveVar.pct, true)
                            : formatPercentage(line.variance_pct, true)}
                        </td>
                        <td className="py-2.5 pl-3 text-center">
                          <StatusChip
                            label={
                              selectedRun.status === 'DRAFT'
                                ? liveVar.isFlagged
                                  ? 'FLAGGED'
                                  : 'OK'
                                : line.is_flagged
                                ? 'FLAGGED'
                                : 'OK'
                            }
                            status={
                              selectedRun.status === 'DRAFT'
                                ? liveVar.isFlagged
                                  ? 'breach'
                                  : 'ok'
                                : line.is_flagged
                                ? 'breach'
                                : 'ok'
                            }
                            size="sm"
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* After Posting Result View & Overheads & Cost Sheet */}
          {selectedRun.status === 'POSTED' && (
            <div className="space-y-6 pt-4 border-t border-border">
              {/* Overheads Section */}
              <div className="bg-surface border border-border rounded-[6px] p-4 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-2">
                      <Flame className="w-3.5 h-3.5 text-accent" />
                      <span>Direct Batch Overheads</span>
                    </h3>
                    <p className="text-xs text-text-muted mt-0.5">
                      Log labour, gas, power and consumables specifically incurred for this production batch.
                    </p>
                  </div>
                </div>

                {overheadError && <InlineError message={overheadError} />}

                <form onSubmit={handleRecordOverhead} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Category</label>
                    <select
                      value={overheadCategory}
                      onChange={(e) => setOverheadCategory(e.target.value as any)}
                      className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                    >
                      <option value="LABOUR">Labour (Contract & Direct)</option>
                      <option value="GAS">Gas / Fuel (Frying)</option>
                      <option value="POWER">Power / Electricity</option>
                      <option value="OTHER">Other Consumables</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Amount (₹)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="1"
                      value={overheadAmount}
                      onChange={(e) => setOverheadAmount(e.target.value)}
                      placeholder="e.g. 500.00"
                      required
                      className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-text-secondary mb-1">Description</label>
                    <input
                      type="text"
                      value={overheadDescription}
                      onChange={(e) => setOverheadDescription(e.target.value)}
                      placeholder="e.g. Extra frying cylinder"
                      className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                    />
                  </div>

                  <Button type="submit" size="sm" disabled={isRecordingOverhead} className="h-8 text-xs gap-1">
                    <Plus className="w-3 h-3" />
                    <span>{isRecordingOverhead ? 'Recording...' : 'Add Overhead'}</span>
                  </Button>
                </form>
              </div>

              {/* Cost Sheet & Margin Analysis */}
              {costDetail && (
                <div className="bg-surface border border-border rounded-[6px] p-5 space-y-4">
                  <div className="flex items-center justify-between border-b border-border pb-3">
                    <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                      <Layers className="w-4 h-4 text-accent" />
                      <span>Batch Cost Sheet & Packet Margins</span>
                    </h3>
                    <span className="text-xs text-text-muted">
                      {formatIndianNumber(costDetail.good_packets)} Good Packets Produced
                    </span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div>
                      <span className="text-xs text-text-muted block">Total Material Cost</span>
                      <span className="text-sm font-semibold text-text-primary tabular-nums">
                        {formatIndianCurrency(costDetail.total_material_cost_paise / 100)}
                      </span>
                    </div>

                    <div>
                      <span className="text-xs text-text-muted block">Direct & Allocated Overheads</span>
                      <span className="text-sm font-semibold text-text-primary tabular-nums">
                        {formatIndianCurrency(costDetail.total_overheads_paise / 100)}
                      </span>
                    </div>

                    <div>
                      <span className="text-xs text-text-muted block">Total Batch Cost</span>
                      <span className="text-sm font-semibold text-text-primary tabular-nums">
                        {formatIndianCurrency(costDetail.total_cost_paise / 100)}
                      </span>
                    </div>

                    <div>
                      <span className="text-xs text-text-muted block">Cost of Loss (Wastage)</span>
                      <span className="text-sm font-semibold text-amber-700 tabular-nums">
                        {formatIndianCurrency(costDetail.cost_of_loss_paise / 100)}
                      </span>
                    </div>
                  </div>

                  <div className="p-3 bg-surface-subtle border border-border rounded-[4px] grid grid-cols-2 sm:grid-cols-4 gap-4 items-center">
                    <div>
                      <span className="text-xs font-semibold text-text-secondary block">Cost Per Packet</span>
                      <span className="text-base font-semibold text-accent tabular-nums">
                        ₹{costDetail.cost_per_packet}
                      </span>
                    </div>

                    <div>
                      <span className="text-xs text-text-muted block">BOM Standard Cost</span>
                      <span className="text-xs font-medium text-text-secondary tabular-nums">
                        ₹{costDetail.planned_cost_per_packet}
                      </span>
                    </div>

                    {productCostSummary && (
                      <>
                        <div>
                          <span className="text-xs text-text-muted block">Wholesale Selling Price</span>
                          <span className="text-xs font-medium text-text-primary tabular-nums">
                            ₹{productCostSummary.selling_price}
                          </span>
                        </div>

                        <div>
                          <span className="text-xs font-semibold text-text-secondary block">Gross Margin %</span>
                          <span className="text-base font-semibold text-emerald-700 tabular-nums">
                            {productCostSummary.margin_pct}%
                          </span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ) : (
        /* Runs List */
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-text-primary">Production Batches</h2>
            <span className="text-xs text-text-muted">{runs.length} runs</span>
          </div>

          {isLoading ? (
            <div className="divide-y divide-border border-y border-border py-4">
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
              <div className="h-6 bg-surface-subtle animate-pulse rounded my-2"></div>
            </div>
          ) : error ? (
            <InlineError message={error} onRetry={fetchRunsAndProducts} />
          ) : runs.length === 0 ? (
            <EmptyState
              message="No production runs recorded yet"
              description="Click 'New Production Run' to scale a BOM recipe and log batch production."
              action={
                <Button size="sm" onClick={() => setShowNewModal(true)} className="text-xs">
                  Create First Run
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="production-runs-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Run No</th>
                    <th className="py-2.5 px-3">Product</th>
                    <th className="py-2.5 px-3">Run Date</th>
                    <th className="py-2.5 px-3 text-right">Batches</th>
                    <th className="py-2.5 px-3 text-right">Expected</th>
                    <th className="py-2.5 px-3 text-right">Good Output</th>
                    <th className="py-2.5 px-3 text-center">Yield Variance</th>
                    <th className="py-2.5 pl-3 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {runs.map((r) => (
                    <tr
                      key={r.id}
                      onClick={() => loadRunDetail(r.id)}
                      className="hover:bg-surface-subtle/60 cursor-pointer transition-colors"
                    >
                      <td className="py-2.5 pr-3 font-semibold text-accent">{r.run_no}</td>
                      <td className="py-2.5 px-3 font-medium text-text-primary">
                        {r.product?.name || `Product #${r.product_id}`}
                      </td>
                      <td className="py-2.5 px-3 text-text-secondary">
                        {new Date(r.run_date).toLocaleDateString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">{r.batches}</td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {formatIndianNumber(r.expected_output_packets)}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                        {r.actual_good_packets !== null && r.actual_good_packets !== undefined
                          ? formatIndianNumber(r.actual_good_packets)
                          : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-center">
                        {r.yield_variance_pct !== null && r.yield_variance_pct !== undefined ? (
                          <StatusChip
                            label={formatPercentage(r.yield_variance_pct, true)}
                            status={r.is_yield_flagged ? 'breach' : 'ok'}
                            size="sm"
                          />
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                      <td className="py-2.5 pl-3 text-right">
                        <StatusChip
                          label={r.status}
                          status={r.status === 'POSTED' ? 'ok' : r.status === 'DRAFT' ? 'neutral' : 'breach'}
                          size="sm"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
