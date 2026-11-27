import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OwnerDashboardPage } from '../OwnerDashboardPage';
import { LoginPage } from '@/features/auth/LoginPage';
import { AuthProvider } from '@/features/auth/AuthContext';
import { setAccessToken, getAccessToken, apiClient, ApiError, setRefreshToken } from '@/lib/api/client';

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
          json: async () => ({
            today: {
              orders_received_count: 5,
              orders_received_value_paise: 500000,
              orders_pending_approval_count: 1,
              invoices_raised_count: 2,
              invoices_raised_value_paise: 200000,
              dispatches_made_count: 1,
              payments_collected_paise: 150000,
              payments_collected_count: 1,
            },
          }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({}),
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

    globalThis.fetch = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = input.toString();
      if (url.includes('/dashboard/summary')) {
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

    // Render LoginPage when navigated with ?returnUrl=%2Foverview&expired=true
    render(
      <AuthProvider>
        <MemoryRouter initialEntries={['/login?returnUrl=%2Foverview&expired=true']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>
    );

    // The message "Your session expired. Sign in again." must be displayed
    expect(screen.getByText(/Your session expired\. Sign in again\./i)).toBeInTheDocument();
  });
});
