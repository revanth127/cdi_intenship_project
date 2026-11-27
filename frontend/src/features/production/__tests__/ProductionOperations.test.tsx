import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ProductionOperationsPage } from '../ProductionOperationsPage';
import { apiClient } from '@/lib/api/client';

describe('ProductionOperationsPage', () => {
  const mockRuns = [
    {
      id: 1,
      run_no: 'PR-2026-0001',
      product_id: 1,
      bom_id: 1,
      bom_version: 1,
      run_date: '2026-11-26T10:00:00Z',
      batches: 1.0,
      expected_output_packets: 200,
      actual_good_packets: 196,
      wastage_packets: 4,
      yield_variance_pct: -2.0,
      is_yield_flagged: false,
      status: 'POSTED',
      product: { id: 1, name: 'Murukku 200 g', pack_size: '200 g' },
      lines: [
        {
          id: 101,
          run_id: 1,
          item_id: 1,
          planned_qty_base: 40000,
          actual_qty_base: 40000,
          damaged_qty_base: 0,
          variance_qty_base: 0,
          variance_pct: 0.0,
          is_flagged: false,
          unit_for_display: 'kg',
          item: { id: 1, name: 'Rice Flour', item_type: 'RAW_MATERIAL', display_unit: 'kg', base_unit: 'g' },
        },
      ],
    },
  ];

  const mockProducts = [
    { id: 1, name: 'Murukku 200 g', pack_size: '200 g', item_id: 10 },
  ];

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders production run list and opens run detail', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
      if (url === '/production') return mockRuns as any;
      if (url === '/products') return mockProducts as any;
      if (url === '/production/1') return mockRuns[0] as any;
      if (url.includes('/costing/runs/1')) {
        return {
          run_id: 1,
          run_no: 'PR-2026-0001',
          product_name: 'Murukku 200 g',
          good_packets: 196,
          total_material_cost_paise: 500000,
          direct_overheads_paise: 100000,
          allocated_overheads_paise: 0,
          total_overheads_paise: 100000,
          total_cost_paise: 600000,
          cost_per_packet: '30.61',
          planned_cost_per_packet: '29.50',
          cost_of_loss_paise: 12245,
        } as any;
      }
      if (url.includes('/costing/products')) {
        return [
          {
            product_id: 1,
            product_name: 'Murukku 200 g',
            cost_per_packet: '30.61',
            selling_price: '50.00',
            margin_per_packet: '19.39',
            margin_pct: '38.8',
          },
        ] as any;
      }
      return [] as any;
    });

    render(<ProductionOperationsPage />);

    // Table should render the run
    await waitFor(() => {
      expect(screen.getByText('PR-2026-0001')).toBeInTheDocument();
    });
    expect(screen.getByText('Murukku 200 g')).toBeInTheDocument();
    expect(screen.getByText('POSTED')).toBeInTheDocument();

    // Click on row to open detail
    fireEvent.click(screen.getByText('PR-2026-0001'));

    await waitFor(() => {
      expect(screen.getByTestId('production-lines-table')).toBeInTheDocument();
    });

    expect(screen.getByText('Rice Flour')).toBeInTheDocument();
    expect(screen.getByText('Batch Cost Sheet & Packet Margins')).toBeInTheDocument();
    expect(screen.getByText('₹30.61')).toBeInTheDocument();
    expect(screen.getByText('38.8%')).toBeInTheDocument();
  });
});
