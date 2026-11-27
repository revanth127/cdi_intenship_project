import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
      batches: '1.0000',
      batch_size_packets: 200,
      expected_output_packets: 200,
      actual_good_packets: 196,
      wastage_packets: 4,
      yield_variance_pct: '-2.00',
      is_yield_flagged: false,
      status: 'POSTED',
      total_material_cost_paise: 500000,
      unit_material_cost_paise: '2551.020408',
      lines: [
        {
          id: 101,
          run_id: 1,
          item_id: 1,
          planned_qty_base: 40000,
          actual_qty_base: 40000,
          damaged_qty_base: 0,
          variance_qty_base: 0,
          variance_pct: '0.00',
          is_flagged: false,
          unit_cost: '4.312500',
          value_paise: 172500,
          unit_for_display: 'kg',
          item: {
            id: 1,
            name: 'Rice Flour',
            item_type: 'RAW_MATERIAL',
            display_unit: 'kg',
            base_unit: 'g',
          },
        },
      ],
    },
  ];

  const mockProducts = [
    {
      id: 1,
      item_id: 10,
      pack_name: 'Murukku 200 g',
      pack_size_desc: '200 g',
      item: {
        id: 10,
        name: 'Murukku 200 g',
        item_type: 'FINISHED_GOOD',
        base_unit: 'packet',
        display_unit: 'packet',
      },
    },
  ];

  const mockBoms = [
    {
      id: 1,
      product_id: 1,
      version: 1,
      expected_output_g: 40000,
      batch_output_packets: 200,
      is_active: true,
      items: [],
    },
  ];

  const mockCostDetail = {
    run_id: 1,
    run_no: 'PR-2026-0001',
    product_id: 1,
    product_name: 'Murukku 200 g',
    run_date: '2026-11-26T10:00:00Z',
    status: 'POSTED',
    expected_output_packets: 200,
    good_packets: 196,
    wastage_packets: 4,
    yield_variance_pct: '-2.00',
    material_cost_paise: 500000,
    material_cost_per_packet: '25.51',
    material_breakdown: [
      {
        item_id: 1,
        item_name: 'Rice Flour',
        base_unit: 'g',
        display_unit: 'kg',
        quantity_base: 40000,
        unit_cost_paise: '4.312500',
        value_paise: 172500,
      },
    ],
    labour_paise: 100000,
    gas_power_paise: 0,
    other_paise: 0,
    total_overheads_paise: 100000,
    overhead_cost_per_packet: '5.10',
    overheads_breakdown: [],
    total_cost_paise: 600000,
    cost_per_packet: '30.61',
    cost_per_packet_4dp: '30.6122',
    planned_cost_per_packet: '29.50',
    cost_of_loss_paise: 12245,
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the run list and the posted result cost sheet', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
      if (url === '/production') return mockRuns as any;
      if (url === '/products') return mockProducts as any;
      if (url === '/boms') return mockBoms as any;
      if (url === '/company-settings') {
        return { variance_tolerance_pct: '3.00' } as any;
      }
      if (url === '/production/1') return mockRuns[0] as any;
      if (url === '/costing/runs/1') return mockCostDetail as any;
      if (url.includes('/costing/products')) {
        return [
          {
            product_id: 1,
            product_name: 'Murukku 200 g',
            cost_per_packet: '30.61',
            selling_price: '50.00',
            margin_per_packet: '19.39',
            margin_pct: '38.80',
            selling_price_paise: 5000,
            gst_rate_bp: 500,
          },
        ] as any;
      }
      return [] as any;
    });

    render(
      <MemoryRouter>
        <ProductionOperationsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('PR-2026-0001')).toBeInTheDocument();
    });
    expect(screen.getByText(/Murukku 200 g/)).toBeInTheDocument();
    expect(screen.getByText('POSTED')).toBeInTheDocument();

    fireEvent.click(screen.getByText('PR-2026-0001'));

    await waitFor(() => {
      expect(screen.getByTestId('production-lines-table')).toBeInTheDocument();
    });

    expect(screen.getAllByText('Rice Flour').length).toBeGreaterThan(0);
    expect(screen.getByText('Batch cost sheet & margin')).toBeInTheDocument();
    expect(screen.getByText('₹30.61')).toBeInTheDocument();
    expect(screen.getByText(/\+38.8%/)).toBeInTheDocument();
    expect(screen.getByText('Stock effect')).toBeInTheDocument();
  });
});
