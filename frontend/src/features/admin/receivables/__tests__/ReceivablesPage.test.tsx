import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ReceivablesPage } from '../ReceivablesPage';
import { apiClient } from '@/lib/api/client';
import * as AuthContextModule from '@/features/auth/AuthContext';

describe('ReceivablesPage (Group B)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 2, email: 'admin@foodmfr.local', full_name: 'Admin', role: 'ADMIN', is_active: true },
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
    });
  });

  it('shows outstanding + ageing and record-payment; accountant read-only hides payment', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
      if (url === '/receivables/outstanding') {
        return [{
          customer_id: 1, customer_name: 'Retailer A',
          total_invoiced_paise: 787500, total_credit_notes_paise: 0, total_payments_paise: 400000,
          open_invoices_outstanding_paise: 387500, unallocated_advance_paise: 0, total_outstanding_paise: 387500,
          invoices: [{ invoice_id: 1, invoice_no: 'INV/2026-27/0001', invoice_date: '2026-11-27T00:00:00Z', customer_id: 1, customer_name: 'Retailer A', grand_total_paise: 787500, credit_notes_total_paise: 0, paid_allocations_paise: 400000, outstanding_paise: 387500, age_days: 0, status: 'POSTED' }],
        }] as any;
      }
      if (url === '/receivables/ageing') {
        return { as_of: '2026-11-27T00:00:00Z', total_bucket_0_30_paise: 387500, total_bucket_31_60_paise: 0, total_bucket_61_90_paise: 0, total_bucket_90_plus_paise: 0, total_unallocated_advance_paise: 0, grand_total_outstanding_paise: 387500, customers: [] } as any;
      }
      return [] as any;
    });

    const { unmount } = render(<MemoryRouter><ReceivablesPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('INV/2026-27/0001')).toBeInTheDocument());
    expect(screen.getByText('Record payment')).toBeInTheDocument();
    expect(screen.getAllByText('₹3,875.00').length).toBeGreaterThan(0);
    unmount();

    // accountant read-only
    vi.spyOn(AuthContextModule, 'useAuth').mockReturnValue({
      user: { id: 4, email: 'accountant@foodmfr.local', full_name: 'Acc', role: 'ACCOUNTANT', is_active: true },
      isAuthenticated: true, isLoading: false, login: vi.fn(), logout: vi.fn(),
    });
    render(<MemoryRouter><ReceivablesPage isReadOnly /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText('INV/2026-27/0001')).toBeInTheDocument());
    expect(screen.queryByText('Record payment')).not.toBeInTheDocument();
  });
});
