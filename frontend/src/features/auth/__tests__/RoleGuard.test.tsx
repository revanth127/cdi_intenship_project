import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { RoleGuard } from '../RoleGuard';
import * as AuthContextModule from '../AuthContext';

describe('RoleGuard Security & Navigation Guard', () => {
  it('allows access when user has an authorized role (OWNER)', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: 2,
        email: 'owner@foodmfr.local',
        full_name: 'Owner User',
        role: 'OWNER',
        is_active: true,
      },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <RoleGuard allowedRoles={['OWNER', 'ADMIN']}>
                <div data-testid="owner-dashboard">Confidential Owner Dashboard</div>
              </RoleGuard>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('owner-dashboard')).toBeInTheDocument();
    expect(screen.getByText('Confidential Owner Dashboard')).toBeInTheDocument();
    expect(screen.queryByTestId('guard-restricted')).not.toBeInTheDocument();
  });

  it('blocks access and displays access restricted screen when user is SALESMAN attempting to open owner dashboard', () => {
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: {
        id: 3,
        email: 'salesman@foodmfr.local',
        full_name: 'Field Salesman',
        role: 'SALESMAN',
        is_active: true,
      },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });

    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <Routes>
          <Route
            path="/dashboard"
            element={
              <RoleGuard allowedRoles={['OWNER', 'ADMIN']}>
                <div data-testid="owner-dashboard">Confidential Owner Dashboard</div>
              </RoleGuard>
            }
          />
        </Routes>
      </MemoryRouter>
    );

    // Salesman must NOT see the dashboard
    expect(screen.queryByTestId('owner-dashboard')).not.toBeInTheDocument();

    // Salesman must see explicit restricted message
    expect(screen.getByTestId('guard-restricted')).toBeInTheDocument();
    expect(screen.getByText(/Access restricted/i)).toBeInTheDocument();
    expect(screen.getByText(/Your role \(SALESMAN\) is not authorized to open this view/i)).toBeInTheDocument();
  });
});
