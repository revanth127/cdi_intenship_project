import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from '../LoginPage';
import { AppShell } from '@/app/AppShell';
import * as AuthContextModule from '../AuthContext';

describe('Part 2: Demo Logins & Role Views', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_DEMO_MODE', 'true');
    sessionStorage.clear();
    localStorage.clear();
  });

  it('renders all five demo roles with one-line access descriptions and visible credentials, and removes "Test 403 guard"', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      mockLoginAs: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>
    );

    // Verify all five roles are shown
    expect(screen.getByTestId('demo-role-owner')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-admin')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-production')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-accountant')).toBeInTheDocument();
    expect(screen.getByTestId('demo-role-salesman')).toBeInTheDocument();

    // Verify "Test 403 guard" text is removed
    expect(screen.queryByText(/Test 403 guard/i)).not.toBeInTheDocument();

    // Verify credentials visible as small text
    expect(screen.getByText(/owner@foodmfr\.local • OwnerPass123!/i)).toBeInTheDocument();
    expect(screen.getByText(/admin@foodmfr\.local • AdminPass123!/i)).toBeInTheDocument();
    expect(screen.getByText(/production@foodmfr\.local • ProdPass123!/i)).toBeInTheDocument();
    expect(screen.getByText(/accountant@foodmfr\.local • AcctPass123!/i)).toBeInTheDocument();
    expect(screen.getByText(/salesman\.a@foodmfr\.local • SalesPass123!/i)).toBeInTheDocument();
  });

  it('clicking a demo role fills the email and password form fields', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      mockLoginAs: vi.fn(),
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
    fireEvent.click(screen.getByTestId('demo-role-accountant'));
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
      mockLoginAs: vi.fn(),
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
      mockLoginAs: vi.fn(),
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
