import * as React from 'react';
import { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '@/lib/api/client';
import { Button } from '@/components/ui/button';
import { StatusChip } from '@/components/ui/status-chip';
import { EmptyState } from '@/components/ui/empty-state';
import { InlineError } from '@/components/ui/inline-error';
import { Skeleton } from '@/components/ui/skeleton';
import {
  formatIndianCurrency,
  formatIndianDate,
  formatIndianDecimal,
  formatPercentage,
  convertBaseQuantity,
  formatBaseQuantity,
  formatUnitCost,
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
} from 'lucide-react';
import { cn } from '@/components/ui/button';

interface ItemMeta {
  id: number;
  name: string;
  item_type: string;
  base_unit: string;
  display_unit: string;
}

interface Product {
  id: number;
  item_id: number;
  pack_name: string;
  pack_size_desc: string;
  packets_per_carton?: number;
  item: ItemMeta;
}

interface BomItem {
  item_id: number;
  quantity_per_batch: number;
  unit_for_display: string;
  item: ItemMeta;
}

interface Bom {
  id: number;
  product_id: number;
  version: number;
  expected_output_g: number;
  batch_output_packets: number;
  is_active: boolean;
  items: BomItem[];
}

interface ProductionRunLine {
  id: number;
  run_id: number;
  item_id: number;
  planned_qty_base: number;
  actual_qty_base?: number | null;
  damaged_qty_base: number;
  variance_qty_base?: number | null;
  variance_pct?: number | string | null;
  is_flagged: boolean;
  unit_cost?: number | string | null;
  value_paise?: number | null;
  unit_for_display: string;
  item?: ItemMeta;
}

interface ProductionRun {
  id: number;
  run_no: string;
  product_id: number;
  bom_id: number;
  bom_version: number;
  run_date: string;
  batches: number | string;
  batch_size_packets?: number;
  expected_output_packets: number;
  actual_good_packets?: number | null;
  wastage_packets?: number | null;
  yield_variance_pct?: number | string | null;
  is_yield_flagged: boolean;
  status: 'DRAFT' | 'POSTED' | 'CANCELLED';
  notes?: string;
  total_material_cost_paise?: number | null;
  lines: ProductionRunLine[];
  variance_report?: {
    yield_report: { tolerance_pct: number | string };
    lines: { item_id: number; tolerance_pct: number | string }[];
  } | null;
}

interface MaterialConsumptionItem {
  item_id: number;
  item_name: string;
  base_unit: string;
  display_unit: string;
  quantity_base: number;
  unit_cost_paise: number | string;
  value_paise: number;
}

interface AllocatedOverheadLine {
  overhead_id: number;
  category: string;
  description?: string | null;
  is_direct: boolean;
  total_entry_amount_paise: number;
  allocated_amount_paise: number;
}

interface RunCostDetail {
  run_id: number;
  run_no: string;
  product_id: number;
  product_name: string;
  status: string;
  expected_output_packets: number;
  good_packets: number;
  wastage_packets?: number | null;
  yield_variance_pct?: number | string | null;
  material_cost_paise: number;
  material_cost_per_packet: number | string;
  material_breakdown: MaterialConsumptionItem[];
  labour_paise: number;
  gas_power_paise: number;
  other_paise: number;
  total_overheads_paise: number;
  overhead_cost_per_packet: number | string;
  overheads_breakdown: AllocatedOverheadLine[];
  total_cost_paise: number;
  cost_per_packet: number | string;
  cost_per_packet_4dp: number | string;
  planned_cost_per_packet: number | string;
  cost_of_loss_paise: number;
}

interface ProductCostSummary {
  product_id: number;
  product_name: string;
  cost_per_packet: number | string;
  selling_price: number | string;
  margin_per_packet: number | string;
  margin_pct: number | string;
  selling_price_paise: number;
  gst_rate_bp: number;
}

interface EditableLine {
  item_id: number;
  actual_qty: string;
  damaged_qty: string;
}

type OverheadCategory = 'LABOUR' | 'GAS' | 'POWER' | 'OTHER';

const DEFAULT_TOLERANCE = 3;

const productLabel = (product?: Product | null) => {
  if (!product) return null;
  const name = product.pack_name || product.item?.name || `Product #${product.id}`;
  return product.pack_size_desc ? `${name} · ${product.pack_size_desc}` : name;
};

export const ProductionOperationsPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const deepLinkHandled = useRef(false);

  const [runs, setRuns] = useState<ProductionRun[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [boms, setBoms] = useState<Bom[]>([]);
  const [tolerance, setTolerance] = useState(DEFAULT_TOLERANCE);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedRun, setSelectedRun] = useState<ProductionRun | null>(null);
  const [isLoadingRun, setIsLoadingRun] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const [showNewModal, setShowNewModal] = useState(false);
  const [newProductId, setNewProductId] = useState<number | ''>('');
  const [newBatches, setNewBatches] = useState('1');
  const [newNotes, setNewNotes] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editableActualGood, setEditableActualGood] = useState('');
  const [editableLines, setEditableLines] = useState<EditableLine[]>([]);
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isPostingRun, setIsPostingRun] = useState(false);
  const [actionMessage, setActionMessage] = useState<{
    text: string;
    type: 'success' | 'error';
  } | null>(null);

  const [overheadCategory, setOverheadCategory] = useState<OverheadCategory>('LABOUR');
  const [overheadAmount, setOverheadAmount] = useState('');
  const [overheadDescription, setOverheadDescription] = useState('');
  const [isRecordingOverhead, setIsRecordingOverhead] = useState(false);
  const [overheadError, setOverheadError] = useState<string | null>(null);

  const [costDetail, setCostDetail] = useState<RunCostDetail | null>(null);
  const [isLoadingCost, setIsLoadingCost] = useState(false);
  const [costError, setCostError] = useState<string | null>(null);
  const [productCostSummary, setProductCostSummary] = useState<ProductCostSummary | null>(null);

  const getProduct = (productId: number) => products.find((p) => p.id === productId);

  const fetchRunsAndProducts = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [runsData, productsData, bomsData] = await Promise.all([
        apiClient.get<ProductionRun[]>('/production'),
        apiClient.get<Product[]>('/products'),
        apiClient.get<Bom[]>('/boms'),
      ]);
      setRuns(runsData);
      setProducts(productsData);
      setBoms(bomsData.filter((b) => b.is_active));

      // The variance report carries the configured tolerance and is readable by
      // the production role; company settings are admin-only.
      const runTolerance = runsData[0]?.variance_report?.yield_report?.tolerance_pct;
      const configuredTolerance = Number(runTolerance);
      if (Number.isFinite(configuredTolerance)) setTolerance(configuredTolerance);
    } catch (err: any) {
      setError(err?.message || 'Failed to load production runs.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRunsAndProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hydrateEditor = (run: ProductionRun) => {
    setEditableActualGood(
      run.actual_good_packets !== null && run.actual_good_packets !== undefined
        ? String(run.actual_good_packets)
        : String(run.expected_output_packets || '')
    );
    setEditableLines(
      run.lines.map((line) => {
        const baseUnit = line.item?.base_unit || '';
        const displayUnit = line.item?.display_unit || line.unit_for_display;
        const actualBase =
          line.actual_qty_base !== null && line.actual_qty_base !== undefined
            ? line.actual_qty_base
            : line.planned_qty_base;
        return {
          item_id: line.item_id,
          actual_qty: formatIndianDecimal(
            convertBaseQuantity(actualBase, baseUnit, displayUnit),
            3
          ).replace(/,/g, ''),
          damaged_qty: formatIndianDecimal(
            convertBaseQuantity(line.damaged_qty_base || 0, baseUnit, displayUnit),
            3
          ).replace(/,/g, ''),
        };
      })
    );
  };

  const loadCosting = async (runId: number, productId: number) => {
    setIsLoadingCost(true);
    setCostError(null);
    try {
      const [costData, productData] = await Promise.all([
        apiClient.get<RunCostDetail>(`/costing/runs/${runId}`),
        apiClient.get<ProductCostSummary[]>(`/costing/products?product_id=${productId}`),
      ]);
      setCostDetail(costData);
      setProductCostSummary(productData && productData.length > 0 ? productData[0] : null);
    } catch (err: any) {
      setCostDetail(null);
      setCostError(err?.message || 'Failed to load the batch cost sheet.');
    } finally {
      setIsLoadingCost(false);
    }
  };

  const loadRunDetail = async (runId: number) => {
    setSelectedRunId(runId);
    setIsLoadingRun(true);
    setRunError(null);
    setActionMessage(null);
    setCostDetail(null);
    setProductCostSummary(null);
    try {
      const run = await apiClient.get<ProductionRun>(`/production/${runId}`);
      setSelectedRun(run);
      hydrateEditor(run);
      const runTolerance = Number(run.variance_report?.yield_report?.tolerance_pct);
      if (Number.isFinite(runTolerance)) setTolerance(runTolerance);
      if (run.status === 'POSTED') {
        await loadCosting(run.id, run.product_id);
      }
    } catch (err: any) {
      setRunError(err?.message || `Failed to load details for run #${runId}.`);
    } finally {
      setIsLoadingRun(false);
    }
  };

  useEffect(() => {
    if (isLoading || deepLinkHandled.current) return;
    const runParam = searchParams.get('run');
    if (!runParam) {
      deepLinkHandled.current = true;
      return;
    }
    const parsed = Number(runParam);
    if (Number.isInteger(parsed) && runs.some((r) => r.id === parsed)) {
      deepLinkHandled.current = true;
      loadRunDetail(parsed);
    } else {
      deepLinkHandled.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, runs]);

  const selectedBom = boms.find((b) => b.product_id === Number(newProductId));
  const expectedNewOutput = selectedBom
    ? Math.round(selectedBom.batch_output_packets * (parseFloat(newBatches) || 0))
    : null;

  const handleCreateRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProductId) {
      setCreateError('Select a finished-goods product.');
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
      setNewBatches('1');
      setNewNotes('');
      await fetchRunsAndProducts();
      await loadRunDetail(newRun.id);
    } catch (err: any) {
      setCreateError(err?.message || 'Failed to initialize the production run from its BOM.');
    } finally {
      setIsCreating(false);
    }
  };

  const buildSavePayload = () => {
    if (!selectedRun) return { lines: [] as any[] };
    const good = parseInt(editableActualGood, 10);
    return {
      actual_good_packets:
        editableActualGood !== '' && !isNaN(good) ? good : undefined,
      lines: selectedRun.lines.map((line) => {
        const state = editableLines.find((l) => l.item_id === line.item_id);
        const baseUnit = line.item?.base_unit || '';
        const displayUnit = line.item?.display_unit || line.unit_for_display;
        const damaged = parseFloat(state?.damaged_qty || '0') || 0;
        let actual = parseFloat(state?.actual_qty || '0') || 0;

        // Primary packaging is consumed at one piece per good packet plus damage.
        const isPrimaryPackaging =
          line.planned_qty_base === selectedRun.expected_output_packets;
        if (isPrimaryPackaging && !isNaN(good)) {
          actual = good + damaged;
        }

        return {
          item_id: line.item_id,
          // The API accepts display-unit quantities; it converts them to base units.
          actual_qty: actual,
          damaged_qty: damaged,
          unit: displayUnit || line.unit_for_display,
        };
      }),
    };
  };

  const handleSaveDraft = async () => {
    if (!selectedRun) return;
    setIsSavingDraft(true);
    setActionMessage(null);
    try {
      const updated = await apiClient.patch<ProductionRun>(
        `/production/${selectedRun.id}`,
        buildSavePayload()
      );
      setSelectedRun(updated);
      hydrateEditor(updated);
      setActionMessage({ text: 'Draft saved. Variances recalculated.', type: 'success' });
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
        'Post this production run? Materials will be issued from stock and finished goods received atomically.'
      )
    ) {
      return;
    }

    setIsPostingRun(true);
    setActionMessage(null);
    try {
      await apiClient.patch<ProductionRun>(`/production/${selectedRun.id}`, buildSavePayload());
      const posted = await apiClient.post<ProductionRun>(`/production/${selectedRun.id}/post`);
      setSelectedRun(posted);
      hydrateEditor(posted);
      setActionMessage({
        text: 'Production run posted. Stock movements recorded atomically.',
        type: 'success',
      });
      fetchRunsAndProducts();
      await loadCosting(posted.id, posted.product_id);
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
      setOverheadError('Enter a positive overhead amount.');
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
      await loadCosting(selectedRun.id, selectedRun.product_id);
      setActionMessage({
        text: `${overheadCategory.toLowerCase()} overhead recorded against ${selectedRun.run_no}.`,
        type: 'success',
      });
    } catch (err: any) {
      setOverheadError(err?.message || 'Failed to record overhead expenditure.');
    } finally {
      setIsRecordingOverhead(false);
    }
  };

  const getLineDisplay = (line: ProductionRunLine) => {
    const baseUnit = line.item?.base_unit || '';
    const displayUnit = line.item?.display_unit || line.unit_for_display;
    return { baseUnit, displayUnit };
  };

  const getLineLiveVariance = (plannedBase: number, actualStr: string, line: ProductionRunLine) => {
    const { baseUnit, displayUnit } = getLineDisplay(line);
    const planned = convertBaseQuantity(plannedBase, baseUnit, displayUnit);
    const actual = parseFloat(actualStr);
    if (isNaN(actual) || planned <= 0) return { pct: 0, isFlagged: false };
    const pct = ((actual - planned) / planned) * 100;
    return { pct, isFlagged: Math.abs(pct) > tolerance };
  };

  const getYieldLiveVariance = (expected: number, actualGoodStr: string) => {
    const actual = parseFloat(actualGoodStr);
    if (isNaN(actual) || expected <= 0) return { pct: 0, isFlagged: false, wastage: 0 };
    const pct = ((actual - expected) / expected) * 100;
    return {
      pct,
      isFlagged: Math.abs(pct) > tolerance,
      wastage: expected - actual,
    };
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
        <div>
          <h1 className="text-xl font-semibold text-text-primary tracking-tight">Production</h1>
          <p className="text-xs text-text-secondary mt-0.5">
            BOM batch scaling, actual-versus-planned consumption, tolerance alerts, and batch
            costing.
          </p>
        </div>
        <div className="flex items-center gap-2 self-start">
          {selectedRunId && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setSelectedRunId(null);
                setSelectedRun(null);
                setCostDetail(null);
                setActionMessage(null);
              }}
              className="h-8 text-xs gap-1"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>All runs</span>
            </Button>
          )}
          <Button size="sm" onClick={() => setShowNewModal(true)} className="h-8 text-xs gap-1.5">
            <Plus className="w-3.5 h-3.5" />
            <span>New production run</span>
          </Button>
        </div>
      </div>

      {showNewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="bg-surface border border-border rounded-[6px] max-w-md w-full p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <Factory className="w-4 h-4 text-accent" />
                <span>Initialize production run</span>
              </h2>
              <button
                type="button"
                onClick={() => setShowNewModal(false)}
                className="text-text-muted hover:text-text-primary text-xs"
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            {createError && <InlineError message={createError} />}

            <form onSubmit={handleCreateRun} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="new-run-product">
                  Pack size <span className="text-status-breach-text">*</span>
                </label>
                <select
                  id="new-run-product"
                  value={newProductId}
                  onChange={(e) => setNewProductId(e.target.value ? Number(e.target.value) : '')}
                  required
                  className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px]"
                >
                  <option value="">Select finished-goods product</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {productLabel(p)}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="new-run-batches">
                  Batches <span className="text-status-breach-text">*</span>
                </label>
                <input
                  id="new-run-batches"
                  type="number"
                  step="0.0001"
                  min="0.1"
                  value={newBatches}
                  onChange={(e) => setNewBatches(e.target.value)}
                  required
                  className="w-full text-xs h-8 px-2.5 bg-surface border border-border rounded-[4px] tabular-nums"
                />
                <span className="text-[11px] text-text-muted">
                  Quantities scale proportionally from the active BOM.
                </span>
              </div>

              <div className="flex items-baseline justify-between border-t border-border pt-3">
                <span className="text-xs text-text-secondary">Expected output</span>
                <span className="text-sm font-semibold text-text-primary tabular-nums">
                  {expectedNewOutput !== null
                    ? `${expectedNewOutput.toLocaleString('en-IN')} packets`
                    : '—'}
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="new-run-notes">
                  Notes / batch tag
                </label>
                <input
                  id="new-run-notes"
                  type="text"
                  value={newNotes}
                  onChange={(e) => setNewNotes(e.target.value)}
                  placeholder="e.g. Morning shift batch 1"
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
                  {isCreating ? 'Creating run…' : 'Create run'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {actionMessage && (
        <div
          className={cn(
            'py-2.5 px-3 border-b text-xs flex items-center gap-2',
            actionMessage.type === 'success'
              ? 'border-status-ok-border text-status-ok-text'
              : 'border-status-breach-border text-status-breach-text'
          )}
          role={actionMessage.type === 'error' ? 'alert' : 'status'}
        >
          {actionMessage.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 shrink-0" />
          ) : (
            <AlertTriangle className="w-4 h-4 shrink-0" />
          )}
          <span className="font-medium">{actionMessage.text}</span>
        </div>
      )}

      {selectedRunId && selectedRun ? (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-border pb-4">
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
                {productLabel(getProduct(selectedRun.product_id)) || `Product #${selectedRun.product_id}`}{' '}
                · BOM v{selectedRun.bom_version} · {Number(selectedRun.batches)} batch
                {Number(selectedRun.batches) === 1 ? '' : 'es'} · {formatIndianDate(selectedRun.run_date)}
              </p>
            </div>

            {selectedRun.status === 'DRAFT' && (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleSaveDraft}
                  disabled={isSavingDraft || isPostingRun}
                  className="text-xs h-8 gap-1.5"
                >
                  <Save className="w-3.5 h-3.5" />
                  <span>{isSavingDraft ? 'Saving…' : 'Save draft'}</span>
                </Button>
                <Button
                  size="sm"
                  onClick={handlePostRun}
                  disabled={isPostingRun || isSavingDraft}
                  className="text-xs h-8 gap-1.5"
                >
                  <Send className="w-3.5 h-3.5" />
                  <span>{isPostingRun ? 'Posting…' : 'Post run'}</span>
                </Button>
              </div>
            )}
          </div>

          {isLoadingRun ? (
            <div className="space-y-2 border-t border-border pt-3" aria-label="Loading production run">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : runError ? (
            <InlineError message={runError} onRetry={() => loadRunDetail(selectedRunId)} />
          ) : (
            <>
              <section className="space-y-3" aria-labelledby="output-heading">
                <h3 id="output-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                  Finished-goods output & yield
                </h3>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 border-t border-border pt-3">
                  <div>
                    <span className="text-xs text-text-muted block">Expected output</span>
                    <span className="text-sm font-semibold text-text-primary tabular-nums">
                      {selectedRun.expected_output_packets.toLocaleString('en-IN')} packets
                    </span>
                  </div>

                  <div>
                    <label className="text-xs text-text-muted block" htmlFor="actual-good-packets">
                      Good packets
                    </label>
                    {selectedRun.status === 'DRAFT' ? (
                      <input
                        id="actual-good-packets"
                        type="number"
                        min="0"
                        value={editableActualGood}
                        onChange={(e) => setEditableActualGood(e.target.value)}
                        className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] mt-1 tabular-nums font-semibold"
                      />
                    ) : (
                      <span className="text-sm font-semibold text-accent tabular-nums block mt-1">
                        {(selectedRun.actual_good_packets ?? 0).toLocaleString('en-IN')} packets
                      </span>
                    )}
                  </div>

                  <div>
                    <span className="text-xs text-text-muted block">Wastage</span>
                    <span className="text-sm font-medium text-status-warning-text tabular-nums block mt-1">
                      {selectedRun.status === 'DRAFT'
                        ? `${getYieldLiveVariance(
                            selectedRun.expected_output_packets,
                            editableActualGood
                          ).wastage.toLocaleString('en-IN')} packets`
                        : `${(selectedRun.wastage_packets ?? 0).toLocaleString('en-IN')} packets`}
                    </span>
                  </div>

                  <div>
                    <span className="text-xs text-text-muted block">
                      Yield variance · ±{tolerance}% tolerance
                    </span>
                    <div className="mt-1 flex items-center gap-2">
                      {(() => {
                        const yv =
                          selectedRun.status === 'DRAFT'
                            ? getYieldLiveVariance(
                                selectedRun.expected_output_packets,
                                editableActualGood
                              )
                            : {
                                pct: Number(selectedRun.yield_variance_pct ?? 0),
                                isFlagged: selectedRun.is_yield_flagged,
                              };
                        return (
                          <>
                            <span className="text-sm font-semibold tabular-nums">
                              {formatPercentage(yv.pct, true)}
                            </span>
                            <StatusChip
                              label={yv.isFlagged ? 'FLAGGED' : 'WITHIN TOLERANCE'}
                              status={yv.isFlagged ? 'breach' : 'ok'}
                              size="sm"
                            />
                          </>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              </section>

              <section className="space-y-3" aria-labelledby="materials-heading">
                <div className="flex items-baseline justify-between">
                  <h3 id="materials-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Material & packaging consumption
                  </h3>
                  <span className="text-xs text-text-muted">
                    {selectedRun.lines.length} BOM lines
                  </span>
                </div>

                <div className="overflow-x-auto border-t border-border">
                  <table className="w-full text-xs" data-testid="production-lines-table">
                    <thead>
                      <tr className="border-b border-border text-text-secondary text-left font-semibold">
                        <th className="py-2.5 pr-3">Material</th>
                        <th className="py-2.5 px-3">Unit</th>
                        <th className="py-2.5 px-3 text-right">Planned</th>
                        <th className="py-2.5 px-3 text-right w-36">Actual</th>
                        <th className="py-2.5 px-3 text-right w-28">Damaged</th>
                        <th className="py-2.5 px-3 text-right">Variance</th>
                        <th className="py-2.5 pl-3 text-right">Tolerance</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {selectedRun.lines.map((line) => {
                        const { baseUnit, displayUnit } = getLineDisplay(line);
                        const state =
                          editableLines.find((l) => l.item_id === line.item_id) || {
                            item_id: line.item_id,
                            actual_qty: String(
                              convertBaseQuantity(
                                line.actual_qty_base ?? line.planned_qty_base,
                                baseUnit,
                                displayUnit
                              )
                            ),
                            damaged_qty: String(
                              convertBaseQuantity(
                                line.damaged_qty_base || 0,
                                baseUnit,
                                displayUnit
                              )
                            ),
                          };
                        const liveVar = getLineLiveVariance(
                          line.planned_qty_base,
                          state.actual_qty,
                          line
                        );

                        return (
                          <tr key={line.id} className="hover:bg-surface-subtle/50 transition-colors">
                            <td className="py-2.5 pr-3 font-semibold text-text-primary">
                              {line.item?.name || `Item #${line.item_id}`}
                            </td>
                            <td className="py-2.5 px-3 text-text-muted">{displayUnit}</td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                              {formatBaseQuantity(line.planned_qty_base, baseUnit, displayUnit)}
                            </td>
                            <td className="py-2.5 px-3 text-right">
                              {selectedRun.status === 'DRAFT' ? (
                                <input
                                  aria-label={`Actual quantity for ${line.item?.name || line.item_id}`}
                                  type="number"
                                  step="any"
                                  min="0"
                                  value={state.actual_qty}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    setEditableLines((prev) =>
                                      prev.map((l) =>
                                        l.item_id === line.item_id ? { ...l, actual_qty: val } : l
                                      )
                                    );
                                  }}
                                  className="w-full text-xs h-7 px-2 bg-surface border border-border rounded-[4px] text-right font-semibold tabular-nums"
                                />
                              ) : (
                                <span className="font-semibold text-text-primary tabular-nums">
                                  {formatBaseQuantity(
                                    line.actual_qty_base ?? 0,
                                    baseUnit,
                                    displayUnit
                                  )}
                                </span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 text-right">
                              {selectedRun.status === 'DRAFT' ? (
                                <input
                                  aria-label={`Damaged quantity for ${line.item?.name || line.item_id}`}
                                  type="number"
                                  step="any"
                                  min="0"
                                  value={state.damaged_qty}
                                  onChange={(e) => {
                                    const val = e.target.value;
                                    setEditableLines((prev) =>
                                      prev.map((l) =>
                                        l.item_id === line.item_id ? { ...l, damaged_qty: val } : l
                                      )
                                    );
                                  }}
                                  className="w-full text-xs h-7 px-2 bg-surface border border-border rounded-[4px] text-right text-status-warning-text tabular-nums"
                                />
                              ) : (
                                <span className="text-status-warning-text tabular-nums">
                                  {formatBaseQuantity(
                                    line.damaged_qty_base || 0,
                                    baseUnit,
                                    displayUnit
                                  )}
                                </span>
                              )}
                            </td>
                            <td className="py-2.5 px-3 text-right font-semibold tabular-nums">
                              {selectedRun.status === 'DRAFT'
                                ? formatPercentage(liveVar.pct, true)
                                : formatPercentage(line.variance_pct, true)}
                            </td>
                            <td className="py-2.5 pl-3 text-right">
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
              </section>

              {selectedRun.status === 'POSTED' && (
                <div className="space-y-6 border-t border-border pt-5">
                  <section className="space-y-3" aria-labelledby="result-heading">
                    <h3 id="result-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                      Posted result · planned vs actual
                    </h3>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                      <div>
                        <span className="text-xs text-text-muted block">Expected</span>
                        <span className="text-sm font-semibold text-text-secondary tabular-nums">
                          {selectedRun.expected_output_packets.toLocaleString('en-IN')} packets
                        </span>
                      </div>
                      <div>
                        <span className="text-xs text-text-muted block">Good output</span>
                        <span className="text-sm font-semibold text-text-primary tabular-nums">
                          {(selectedRun.actual_good_packets ?? 0).toLocaleString('en-IN')} packets
                        </span>
                      </div>
                      <div>
                        <span className="text-xs text-text-muted block">Yield variance</span>
                        <span className="text-sm font-semibold tabular-nums">
                          {formatPercentage(selectedRun.yield_variance_pct, true)}
                        </span>
                      </div>
                      <div>
                        <span className="text-xs text-text-muted block">Flagged BOM lines</span>
                        <span className="text-sm font-semibold tabular-nums">
                          {selectedRun.lines.filter((l) => l.is_flagged).length} of{' '}
                          {selectedRun.lines.length}
                        </span>
                      </div>
                    </div>

                    {selectedRun.lines.some((l) => l.is_flagged) && (
                      <ul className="space-y-1 text-xs text-status-breach-text border-t border-border pt-2">
                        {selectedRun.lines
                          .filter((l) => l.is_flagged)
                          .map((l) => (
                            <li key={l.id}>
                              <span className="font-semibold">
                                {l.item?.name || `Item #${l.item_id}`}
                              </span>{' '}
                              consumed{' '}
                              {formatBaseQuantity(
                                l.planned_qty_base,
                                l.item?.base_unit || '',
                                l.item?.display_unit || l.unit_for_display
                              )}{' '}
                              planned versus{' '}
                              {formatBaseQuantity(
                                l.actual_qty_base ?? 0,
                                l.item?.base_unit || '',
                                l.item?.display_unit || l.unit_for_display
                              )}{' '}
                              actual ({formatPercentage(l.variance_pct, true)}).
                            </li>
                          ))}
                      </ul>
                    )}
                  </section>

                  <section className="space-y-3" aria-labelledby="stock-effect-heading">
                    <h3 id="stock-effect-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                      Stock effect
                    </h3>
                    {isLoadingCost ? (
                      <div className="space-y-2 border-t border-border pt-3">
                        <Skeleton className="h-7 w-full" />
                        <Skeleton className="h-7 w-full" />
                      </div>
                    ) : costError ? (
                      <InlineError
                        message={costError}
                        onRetry={() => loadCosting(selectedRun.id, selectedRun.product_id)}
                      />
                    ) : costDetail ? (
                      <>
                        <div className="overflow-x-auto border-t border-border">
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="border-b border-border text-text-secondary text-left font-semibold">
                                <th className="py-2 pr-3">Issued material</th>
                                <th className="py-2 px-3 text-right">Quantity</th>
                                <th className="py-2 px-3 text-right">Unit cost</th>
                                <th className="py-2 pl-3 text-right">Value</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                              {costDetail.material_breakdown.map((m) => (
                                <tr key={m.item_id}>
                                  <td className="py-2 pr-3 text-text-primary">{m.item_name}</td>
                                  <td className="py-2 px-3 text-right tabular-nums text-text-secondary">
                                    {formatBaseQuantity(
                                      m.quantity_base,
                                      m.base_unit,
                                      m.display_unit
                                    )}{' '}
                                    {m.display_unit}
                                  </td>
                                  <td className="py-2 px-3 text-right tabular-nums text-text-secondary">
                                    {formatUnitCost(
                                      m.unit_cost_paise,
                                      m.base_unit,
                                      m.display_unit
                                    )}
                                  </td>
                                  <td className="py-2 pl-3 text-right tabular-nums font-medium text-text-primary">
                                    {formatIndianCurrency(m.value_paise / 100)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        <p className="text-xs text-text-secondary">
                          Finished goods received:{' '}
                          <span className="font-semibold text-text-primary tabular-nums">
                            {(costDetail.good_packets || 0).toLocaleString('en-IN')} packets
                          </span>{' '}
                          at the batch cost below.
                        </p>
                      </>
                    ) : null}
                  </section>

                  <section className="space-y-3" aria-labelledby="overheads-heading">
                    <div>
                      <h3 id="overheads-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                        Direct batch overheads
                      </h3>
                      <p className="text-xs text-text-muted mt-0.5">
                        Record labour, gas, power or other costs incurred for this batch.
                      </p>
                    </div>

                    {overheadError && <InlineError message={overheadError} />}

                    <form onSubmit={handleRecordOverhead} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
                      <div>
                        <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="overhead-category">
                          Category
                        </label>
                        <select
                          id="overhead-category"
                          value={overheadCategory}
                          onChange={(e) => setOverheadCategory(e.target.value as OverheadCategory)}
                          className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                        >
                          <option value="LABOUR">Labour</option>
                          <option value="GAS">Gas / fuel</option>
                          <option value="POWER">Power / electricity</option>
                          <option value="OTHER">Other</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="overhead-amount">
                          Amount
                        </label>
                        <input
                          id="overhead-amount"
                          type="number"
                          step="0.01"
                          min="0.01"
                          value={overheadAmount}
                          onChange={(e) => setOverheadAmount(e.target.value)}
                          placeholder="0.00"
                          required
                          className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px] tabular-nums"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-text-secondary mb-1" htmlFor="overhead-description">
                          Description
                        </label>
                        <input
                          id="overhead-description"
                          type="text"
                          value={overheadDescription}
                          onChange={(e) => setOverheadDescription(e.target.value)}
                          placeholder="e.g. Extra frying cylinder"
                          className="w-full text-xs h-8 px-2 bg-surface border border-border rounded-[4px]"
                        />
                      </div>
                      <Button type="submit" size="sm" disabled={isRecordingOverhead} className="h-8 text-xs gap-1">
                        <Plus className="w-3 h-3" />
                        <span>{isRecordingOverhead ? 'Recording…' : 'Add overhead'}</span>
                      </Button>
                    </form>

                    {costDetail && costDetail.overheads_breakdown.length > 0 && (
                      <div className="overflow-x-auto border-t border-border">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="border-b border-border text-text-secondary text-left font-semibold">
                              <th className="py-2 pr-3">Category</th>
                              <th className="py-2 px-3">Description</th>
                              <th className="py-2 px-3 text-right">Allocated</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border">
                            {costDetail.overheads_breakdown.map((o) => (
                              <tr key={o.overhead_id}>
                                <td className="py-2 pr-3 font-medium text-text-primary">
                                  {o.category}
                                  {!o.is_direct && (
                                    <span className="ml-1 text-text-muted">(allocated)</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-text-secondary">
                                  {o.description || '—'}
                                </td>
                                <td className="py-2 px-3 text-right tabular-nums text-text-primary">
                                  {formatIndianCurrency(o.allocated_amount_paise / 100)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>

                  <section className="space-y-3" aria-labelledby="cost-sheet-heading">
                    <h3 id="cost-sheet-heading" className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
                      Batch cost sheet & margin
                    </h3>

                    {isLoadingCost ? (
                      <div className="space-y-2 border-t border-border pt-3">
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-8 w-full" />
                      </div>
                    ) : costError ? (
                      <InlineError
                        message={costError}
                        onRetry={() => loadCosting(selectedRun.id, selectedRun.product_id)}
                      />
                    ) : costDetail ? (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 border-t border-border pt-3">
                          <div>
                            <span className="text-xs text-text-muted block">Material cost</span>
                            <span className="text-sm font-semibold text-text-primary tabular-nums">
                              {formatIndianCurrency(costDetail.material_cost_paise / 100)}
                            </span>
                          </div>
                          <div>
                            <span className="text-xs text-text-muted block">Overheads</span>
                            <span className="text-sm font-semibold text-text-primary tabular-nums">
                              {formatIndianCurrency(costDetail.total_overheads_paise / 100)}
                            </span>
                            <span className="block text-[11px] text-text-muted">
                              Labour {formatIndianCurrency(costDetail.labour_paise / 100)} · Gas/power{' '}
                              {formatIndianCurrency(costDetail.gas_power_paise / 100)}
                            </span>
                          </div>
                          <div>
                            <span className="text-xs text-text-muted block">Total batch cost</span>
                            <span className="text-sm font-semibold text-text-primary tabular-nums">
                              {formatIndianCurrency(costDetail.total_cost_paise / 100)}
                            </span>
                          </div>
                          <div>
                            <span className="text-xs text-text-muted block">Cost of wastage</span>
                            <span className="text-sm font-semibold text-status-warning-text tabular-nums">
                              {formatIndianCurrency(costDetail.cost_of_loss_paise / 100)}
                            </span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 bg-surface-subtle px-3 py-3">
                          <div>
                            <span className="text-xs font-semibold text-text-secondary block">
                              Cost per packet
                            </span>
                            <span className="text-base font-semibold text-accent tabular-nums">
                              {formatIndianCurrency(Number(costDetail.cost_per_packet))}
                            </span>
                          </div>
                          <div>
                            <span className="text-xs text-text-muted block">BOM standard cost</span>
                            <span className="text-xs font-medium text-text-secondary tabular-nums">
                              {formatIndianCurrency(Number(costDetail.planned_cost_per_packet))}
                            </span>
                          </div>
                          {productCostSummary && (
                            <>
                              <div>
                                <span className="text-xs text-text-muted block">Selling price</span>
                                <span className="text-xs font-medium text-text-primary tabular-nums">
                                  {formatIndianCurrency(Number(productCostSummary.selling_price))}
                                </span>
                              </div>
                              <div>
                                <span className="text-xs font-semibold text-text-secondary block">
                                  Gross margin
                                </span>
                                <span className="text-base font-semibold text-status-ok-text tabular-nums">
                                  {formatPercentage(productCostSummary.margin_pct, true)} ·{' '}
                                  {formatIndianCurrency(
                                    Number(productCostSummary.margin_per_packet)
                                  )}{' '}
                                  / packet
                                </span>
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    ) : null}
                  </section>
                </div>
              )}
            </>
          )}
        </div>
      ) : (
        <section className="space-y-3" aria-labelledby="runs-heading">
          <div className="flex items-baseline justify-between">
            <h2 id="runs-heading" className="text-sm font-semibold text-text-primary">
              Production batches
            </h2>
            <span className="text-xs text-text-muted">{runs.length} runs</span>
          </div>

          {isLoading ? (
            <div className="space-y-2 border-t border-border pt-3" aria-label="Loading production runs">
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
              <Skeleton className="h-7 w-full" />
            </div>
          ) : error ? (
            <InlineError message={error} onRetry={fetchRunsAndProducts} />
          ) : runs.length === 0 ? (
            <EmptyState
              message="No production runs recorded yet"
              description="Create a run to scale a BOM recipe and log batch production."
              action={
                <Button size="sm" onClick={() => setShowNewModal(true)} className="text-xs">
                  Create first run
                </Button>
              }
            />
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs" data-testid="production-runs-table">
                <thead>
                  <tr className="border-b border-border text-text-secondary text-left font-semibold">
                    <th className="py-2.5 pr-3">Run no.</th>
                    <th className="py-2.5 px-3">Product</th>
                    <th className="py-2.5 px-3">Date</th>
                    <th className="py-2.5 px-3 text-right">Batches</th>
                    <th className="py-2.5 px-3 text-right">Expected</th>
                    <th className="py-2.5 px-3 text-right">Good output</th>
                    <th className="py-2.5 px-3 text-right">Yield variance</th>
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
                        {productLabel(getProduct(r.product_id)) || `Product #${r.product_id}`}
                      </td>
                      <td className="py-2.5 px-3 text-text-secondary">
                        {formatIndianDate(r.run_date)}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {Number(r.batches)}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums text-text-secondary">
                        {r.expected_output_packets.toLocaleString('en-IN')}
                      </td>
                      <td className="py-2.5 px-3 text-right tabular-nums font-semibold text-text-primary">
                        {r.actual_good_packets !== null && r.actual_good_packets !== undefined
                          ? r.actual_good_packets.toLocaleString('en-IN')
                          : '—'}
                      </td>
                      <td className="py-2.5 px-3 text-right">
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
        </section>
      )}
    </div>
  );
};
