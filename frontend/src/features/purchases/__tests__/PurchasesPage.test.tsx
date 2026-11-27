import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PurchasesPage } from '../PurchasesPage';
import { apiClient } from '@/lib/api/client';

describe('PurchasesPage (Group A)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('loads suppliers, items and recent purchases and renders the new-purchase form', async () => {
    vi.spyOn(apiClient, 'get').mockImplementation(async (url: string) => {
      if (url === '/suppliers') return [{ id: 1, name: 'Sri Lakshmi Agro Mills', gstin: '33AAAAA1111A1Z1', is_active: true }] as any;
      if (url === '/items') return [{ id: 1, name: 'Flour', item_type: 'RAW_MATERIAL', base_unit: 'g', display_unit: 'kg', is_active: true }] as any;
      if (url === '/purchases') return [] as any;
      return [] as any;
    });

    render(
      <MemoryRouter>
        <PurchasesPage />
      </MemoryRouter>
    );

    // data loaded + empty state for recent purchases
    await waitFor(() => expect(screen.getByRole('button', { name: /new purchase receipt/i })).toBeInTheDocument());

    // open the form
    screen.getByRole('button', { name: /new purchase receipt/i }).click();

    await waitFor(() => expect(screen.getByTestId('purchase-form')).toBeInTheDocument());
    // supplier + invoice + line fields present
    expect(screen.getByLabelText(/^supplier \*/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/supplier invoice no/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/item for line 1/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/quantity for line 1/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/unit for line 1/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/rate for line 1/i)).toBeInTheDocument();
  });
});
