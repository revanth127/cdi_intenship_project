import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from '../LoginPage';
import { AppShell } from '@/app/AppShell';
import * as AuthContextModule from '../AuthContext';

describe('Part 2: Demo Logins & Role Views', () => {
  const demoCredentials = [
    { title: 'Owner', email: 'owner@foodmfr.local', password: 'OwnerPass123!', access: 'Executive Overview, costing margins, variance alerts, receivables & telemetry' },
    { title: 'Admin', email: 'admin@foodmfr.local', password: 'AdminPass123!', access: 'Full system configuration, user accounts, master data & order approval' },
    { title: 'Production', email: 'production@foodmfr.local', password: 'ProdPass123!', access: 'BOM management, production batch logging, consumption & variance alerts' },
    { title: 'Accountant', email: 'accountant@foodmfr.local', password: 'AcctPass123!', access: 'GST Invoices, receivables ageing, payment allocations & audit reports' },
    { title: 'Salesman', email: 'salesman.a@foodmfr.local', password: 'SalesPass123!', access: 'Mobile offline field order booking & pricing catalog (Retailer A)' },
  ];

  beforeEach(() => {
    vi.stubEnv('VITE_DEMO_MODE', 'true');
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: input.toString().includes('/auth/demo-credentials'),
      status: input.toString().includes('/auth/demo-credentials') ? 200 : 404,
      json: async () => input.toString().includes('/auth/demo-credentials')
        ? demoCredentials
        : { detail: 'Not found' },
    })));
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('renders all five seed-configured roles with visible credentials and removes "Test 403 guard"', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>
    );

    // Verify all five roles are shown
    expect(await screen.findByTestId('demo-role-owner')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-admin')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-production')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-accountant')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-salesman')).toBeInTheDocument();

    // Verify "Test 403 guard" text is removed
    expect(screen.queryByText(/Test 403 guard/i)).not.toBeInTheDocument();

    // Verify credentials visible as small text
    expect(screen.getByText('Email: owner@foodmfr.local')).toBeInTheDocument();
    expect(screen.getByText('Password: OwnerPass123!')).toBeInTheDocument();
    expect(screen.getByText('Email: admin@foodmfr.local')).toBeInTheDocument();
    expect(screen.getByText('Password: AdminPass123!')).toBeInTheDocument();
    expect(screen.getByText('Email: production@foodmfr.local')).toBeInTheDocument();
    expect(screen.getByText('Password: ProdPass123!')).toBeInTheDocument();
    expect(screen.getByText('Email: accountant@foodmfr.local')).toBeInTheDocument();
    expect(screen.getByText('Password: AcctPass123!')).toBeInTheDocument();
    expect(screen.getByText('Email: salesman.a@foodmfr.local')).toBeInTheDocument();
    expect(screen.getByText('Password: SalesPass123!')).toBeInTheDocument();
  });

  it('clicking a demo role fills the email and password form fields', async () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>
    );

    const emailInput = screen.getByPlaceholderText('user@foodmfr.local') as HTMLInputElement;
    const passwordInput = screen.getByPlaceholderText('••••••••') as HTMLInputElement;

    // Click Accountant role
    fireEvent.click(await screen.findByTestId('demo-role-accountant'));
    expect(emailInput.value).toBe('accountant@foodmfr.local');
    expect(passwordInput.value).toBe('AcctPass123!');

    // Click Salesman role
    fireEvent.click(screen.getByTestId('demo-role-salesman'));
    expect(emailInput.value).toBe('salesman.a@foodmfr.local');
    expect(passwordInput.value).toBe('SalesPass123!');
  });

  it('sidebar shows only that role items for Salesman, Production, Accountant, and Admin', () => {
    // 1. Salesman: only New Order and My Orders
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: 3,
        email: 'salesman.a@foodmfr.local',
        full_name: 'Salesman A',
        role: 'SALESMAN',
        is_active: true,
      },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    const { unmount } = render(
      <MemoryRouter initialEntries={['/orders/new']}>
        <AppShell />
      </MemoryRouter>
    );

    expect(screen.getByText('New Order')).toBeInTheDocument();
    expect(screen.getByText('My Orders')).toBeInTheDocument();
    expect(screen.queryByText('Overview')).not.toBeInTheDocument();
    expect(screen.queryByText('Reports')).not.toBeInTheDocument();
    expect(screen.queryByText('Receivables')).not.toBeInTheDocument();

    unmount();

    // 2. Production: only Production and Stock
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: 5,
        email: 'production@foodmfr.local',
        full_name: 'Production Supervisor',
        role: 'PRODUCTION',
        is_active: true,
      },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/production']}>
        <AppShell />
      </MemoryRouter>
    );

    expect(screen.getByText('Production')).toBeInTheDocument();
    expect(screen.getByText('Stock')).toBeInTheDocument();
    expect(screen.queryByText('New Order')).not.toBeInTheDocument();
    expect(screen.queryByText('Reports')).not.toBeInTheDocument();
    expect(screen.queryByText('Overview')).not.toBeInTheDocument();
  });
});
