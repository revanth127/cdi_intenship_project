import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RoleLanding } from '../../../App';
import * as AuthContextModule from '../AuthContext';

const renderLanding = (role: string | null) => {
  vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
    user: role
      ? { id: 1, email: 'x@x.local', full_name: 'X', role: role as any, is_active: true }
      : null,
    isAuthenticated: !!role,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
  });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<RoleLanding />} />
        <Route path="/login" element={<div data-testid="login">login</div>} />
        <Route path="/orders/new" element={<div data-testid="orders-new">salesman home</div>} />
        <Route path="/orders" element={<div data-testid="orders">admin home</div>} />
        <Route path="/production" element={<div data-testid="production">production home</div>} />
        <Route path="/reports" element={<div data-testid="reports">accountant home</div>} />
        <Route path="/receivables" element={<div data-testid="receivables">receivables</div>} />
      </Routes>
    </MemoryRouter>
    </QueryClientProvider>
  );
};

describe('Role landing pages', () => {
  it('salesman -> /orders/new', () => {
    renderLanding('SALESMAN');
    expect(screen.getByTestId('orders-new')).toBeInTheDocument();
  });
  it('admin -> /orders', () => {
    renderLanding('ADMIN');
    expect(screen.getByTestId('orders')).toBeInTheDocument();
  });
  it('production -> /production', () => {
    renderLanding('PRODUCTION');
    expect(screen.getByTestId('production')).toBeInTheDocument();
  });
  it('accountant -> /reports', () => {
    renderLanding('ACCOUNTANT');
    expect(screen.getByTestId('reports')).toBeInTheDocument();
  });
  it('owner -> overview (no redirect)', () => {
    renderLanding('OWNER');
    // owner renders dashboard in place; not redirected to another route
    expect(screen.queryByTestId('orders-new')).not.toBeInTheDocument();
    expect(screen.queryByTestId('orders')).not.toBeInTheDocument();
    expect(screen.queryByTestId('reports')).not.toBeInTheDocument();
  });
  it('unauthenticated -> /login', () => {
    renderLanding(null);
    expect(screen.getByTestId('login')).toBeInTheDocument();
  });
});
