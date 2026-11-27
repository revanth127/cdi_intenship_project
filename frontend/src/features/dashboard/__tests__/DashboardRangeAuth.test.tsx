import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OwnerDashboardPage } from '../OwnerDashboardPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { AuthProvider } from '@/features/auth/AuthContext';
import {
  setAccessToken,
  getAccessToken,
  apiClient,
  ApiError,
  setRefreshToken,
  setOnUnauthorized,
} from '@/lib/api/client';

const benchmarkSummary = {
  as_of: '2026-11-27T09:00:00Z',
  today: {
    date: '2026-11-27',
    orders_received_count: 4,
    orders_received_value_paise: 4800000,
    orders_pending_approval_count: 1,
    invoices_raised_count: 1,
    invoices_raised_value_paise: 750000,
    dispatches_made_count: 1,
    payments_collected_paise: 400000,
    payments_collected_count: 1,
  },
  stock: {
    finished_goods: [{
      product_id: 1,
      product_name: 'Murukku 200 g',
      pack_size_desc: '200 g',
      on_hand_packets: 88,
      committed_packets: 0,
      available_to_promise_packets: 88,
    }],
    reorder_alerts: [],
  },
  variance_alerts: [
    { run_id: 1, run_no: 'PR-2026-0001', run_date: '2026-11-27T09:00:00Z', product_name: 'Murukku 200 g', item_name: 'Cooking oil', planned_qty_base: 10000, actual_qty_base: 10500, difference_qty_base: 500, variance_pct: 5, display_unit: 'L', tolerance_pct: 3 },
    { run_id: 1, run_no: 'PR-2026-0001', run_date: '2026-11-27T09:00:00Z', product_name: 'Murukku 200 g', item_name: 'finished packets', planned_qty_base: 200, actual_qty_base: 188, difference_qty_base: -12, variance_pct: -6, display_unit: 'packet', tolerance_pct: 3 },
    { run_id: 1, run_no: 'PR-2026-0001', run_date: '2026-11-27T09:00:00Z', product_name: 'Murukku 200 g', item_name: 'Carton', planned_qty_base: 10, actual_qty_base: 9, difference_qty_base: -1, variance_pct: -10, display_unit: 'piece', tolerance_pct: 3 },
  ],
  receivables: {
    total_outstanding_paise: 387500,
    bucket_0_30_paise: 387500,
    bucket_31_60_paise: 0,
    bucket_61_90_paise: 0,
    bucket_90_plus_paise: 0,
    unallocated_advance_paise: 0,
    top_debtors: [{
      customer_id: 1,
      customer_name: 'Retailer A (Meenakshi Stores)',
      total_outstanding_paise: 387500,
      oldest_invoice_date: '2026-11-27T09:00:00Z',
    }],
  },
  costing: [{
    product_id: 1,
    product_name: 'Murukku 200 g',
    cost_per_packet: '31.14',
    selling_price: '50.00',
    margin_per_packet: '18.86',
    margin_pct: '37.70',
  }],
  sales_trend: [{
    date: '2026-11-26',
    taxable_sales_paise: 750000,
    taxable_sales_rupees: '7500.00',
    invoice_count: 1,
  }],
};

const benchmarkOrders = [{
  id: 2,
  order_no: 'ORD-2026-0002',
  customer_name: 'Distributor B (Karnataka Snack Distributors)',
  salesman_name: 'Salesman B (Bengaluru)',
  total_amount_paise: 600000,
  created_at: '2026-11-27T09:00:00Z',
  stock_availability: [{ shortage: 32 }],
}];

describe('Part 1: Dashboard Range Selection & Session Robustness', () => {
  let queryClient: QueryClient;
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: 0,
        },
      },
    });
    sessionStorage.clear();
    localStorage.clear();
    setAccessToken(null);
    setRefreshToken(null);
    setOnUnauthorized(() => {});
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('changing the range keeps the session and sends the Authorization header', async () => {
    const validToken = 'valid-owner-jwt-access-token';
    setAccessToken(validToken);

    const capturedRequests: { url: string; headers: HeadersInit }[] = [];

    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      const headers = (init?.headers || {}) as Record<string, string>;
      capturedRequests.push({ url, headers });

      if (url.includes('/dashboard/summary')) {
        return {
          ok: true,
          status: 200,
          json: async () => benchmarkSummary,
        };
      }
      if (url.includes('/orders?status=SUBMITTED')) {
        return { ok: true, status: 200, json: async () => benchmarkOrders };
      }
      return {
        ok: true,
        status: 200,
        json: async () => [],
      };
    }) as any;

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <OwnerDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Initial query is for 'today'
    await waitFor(() => {
      const todayCall = capturedRequests.find((r) => r.url.includes('/dashboard/summary?range=today'));
      expect(todayCall).toBeDefined();
      expect((todayCall?.headers as any)['Authorization']).toBe(`Bearer ${validToken}`);
    });

    // Click "7 days" range button
    const btn7Days = screen.getByRole('button', { name: /7 days/i });
    fireEvent.click(btn7Days);

    await waitFor(() => {
      const call7d = capturedRequests.find((r) => r.url.includes('/dashboard/summary?range=7d'));
      expect(call7d).toBeDefined();
      expect((call7d?.headers as any)['Authorization']).toBe(`Bearer ${validToken}`);
    });

    // Click "30 days" range button
    const btn30Days = screen.getByRole('button', { name: /30 days/i });
    fireEvent.click(btn30Days);

    await waitFor(() => {
      const call30d = capturedRequests.find((r) => r.url.includes('/dashboard/summary?range=30d'));
      expect(call30d).toBeDefined();
      expect((call30d?.headers as any)['Authorization']).toBe(`Bearer ${validToken}`);
    });

    // Session token must still be intact
    expect(getAccessToken()).toBe(validToken);
  });

  it('an expired token returns 401 and the user lands on login with a return path and expired message', async () => {
    setAccessToken('expired-jwt-token');
    window.history.replaceState({}, '', '/overview?range=7d');
    const capturedUnauthorized: Array<{ expired?: boolean; returnUrl?: string }> = [];
    setOnUnauthorized((info) => capturedUnauthorized.push(info || {}));
    let failingRequests = 0;

    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.includes('/dashboard/summary')) {
        failingRequests += 1;
        return {
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Could not validate credentials' }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    }) as any;

    // Direct apiClient call with expired token throws ApiError 401
    await expect(apiClient.get('/dashboard/summary')).rejects.toThrow(ApiError);

    // After 401 on expired token without refresh, token is cleared
    expect(getAccessToken()).toBeNull();
    expect(failingRequests).toBe(1);
    expect(capturedUnauthorized).toEqual([{ expired: true, returnUrl: '/overview?range=7d' }]);

    // Render the login destination produced from the expired request's return path.
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={[
          `/login?returnUrl=${encodeURIComponent(capturedUnauthorized[0].returnUrl || '/')}&expired=true`,
        ]}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/overview" element={<div>Returned to overview</div>} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );

    // The message "Your session expired. Sign in again." must be displayed
    expect(screen.getByText(/Your session expired\. Sign in again\./i)).toBeInTheDocument();
  });

  it('renders Overview figures, daily sales rows, and order numbers from backend data', async () => {
    setAccessToken('owner-token');
    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.includes('/dashboard/summary')) {
        return { ok: true, status: 200, json: async () => benchmarkSummary };
      }
      if (url.includes('/orders?status=SUBMITTED')) {
        return { ok: true, status: 200, json: async () => benchmarkOrders };
      }
      return { ok: false, status: 404, json: async () => ({ detail: 'Not found' }) };
    }) as any;

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/']}>
          <OwnerDashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

    await screen.findByText('ORD-2026-0002');
    expect(screen.getAllByText('88 packets')).toHaveLength(2);
    expect(within(screen.getByTestId('summary-strip')).getByText('₹31.14')).toBeInTheDocument();
    expect(screen.getByText('Short by 32')).toBeInTheDocument();
    expect(screen.getByText('3 flagged alerts')).toBeInTheDocument();
    expect(screen.getByText('10.0 L')).toBeInTheDocument();
    expect(screen.getByText('10.5 L')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /toggle accessible data table/i }));
    expect(await screen.findByText('2026-11-26')).toBeInTheDocument();
    expect(screen.getByText('₹7,500.00')).toBeInTheDocument();
  });
});
