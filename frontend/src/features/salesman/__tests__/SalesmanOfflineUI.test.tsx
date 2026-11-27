import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SalesmanOrderPage } from '../SalesmanOrderPage';
import { SalesmanOrdersList } from '../SalesmanOrdersList';
import {
  saveToOutbox,
  clearAllOfflineData,
  resetDBPromise,
  setCachedReference,
} from '@/lib/offline/db';
import type { OutboxOrder } from '@/lib/offline/types';

describe('Salesman Mobile Offline UI States', () => {
  beforeEach(async () => {
    resetDBPromise();
    await clearAllOfflineData();
    vi.restoreAllMocks();
  });

  afterEach(async () => {
    await clearAllOfflineData();
    resetDBPromise();
  });

  describe('SalesmanOrderPage Offline Behavior', () => {
    it('shows "Prices as of 26 Nov 2026, 10:42", amber review strip, and "Save order" button when offline', async () => {
      // Set offline
      Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
      await setCachedReference('customers', [
        { id: 1, name: 'Annapoorna Sweets', city: 'Madurai', state_code: '33' },
      ], '2026-11-26T10:42:00');

      render(
        <MemoryRouter>
          <SalesmanOrderPage />
        </MemoryRouter>
      );

      // Verify prices timestamp banner
      await waitFor(() => {
        expect(screen.getByTestId('offline-prices-banner')).toBeInTheDocument();
      });
      expect(screen.getByText(/Prices as of 26 Nov 2026, 10:42/i)).toBeInTheDocument();

      // Verify amber review strip
      expect(screen.getByTestId('offline-review-strip')).toBeInTheDocument();
      expect(
        screen.getByText(/You are currently offline. This order will be saved on this phone/i)
      ).toBeInTheDocument();

      // Verify button label is "Save order" (not "Submit order")
      const submitBtn = screen.getByTestId('order-submit-button');
      expect(submitBtn).toHaveTextContent('Save order');

      // Order entry is NEVER blocked: click Save order
      fireEvent.click(submitBtn);

      // Success screen says "Saved on this phone" when queued offline
      await waitFor(() => {
        expect(screen.getByTestId('order-success-screen')).toBeInTheDocument();
      });
      expect(screen.getByTestId('success-title')).toHaveTextContent('Saved on this phone');
    });

    it('shows "Submit order" button when online', async () => {
      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });

      render(
        <MemoryRouter>
          <SalesmanOrderPage />
        </MemoryRouter>
      );

      await waitFor(() => {
        const submitBtn = screen.getByTestId('order-submit-button');
        expect(submitBtn).toHaveTextContent('Submit order');
      });

      // No offline warning banner when online
      expect(screen.queryByTestId('offline-prices-banner')).not.toBeInTheDocument();
      expect(screen.queryByTestId('offline-review-strip')).not.toBeInTheDocument();
    });
  });

  describe('SalesmanOrdersList Chips & Sorting', () => {
    it('renders queued orders with gray "Waiting to send" chip and needs_attention with red chip and error', async () => {
      const orderQueued: OutboxOrder = {
        client_uuid: 'uuid-queued-1',
        payload: { client_uuid: 'uuid-queued-1', customer_id: 1, lines: [] },
        customer_id: 1,
        customer_name: 'Annapoorna Sweets',
        lines: [
          {
            product_id: 1,
            product_name: 'Murukku 200 g',
            quantity_packets: 20,
            unit_price_paise: 5000,
            line_total_paise: 100000,
          },
        ],
        total_amount_paise: 100000,
        status: 'queued',
        attempts: 0,
        created_at: '2026-11-26T10:00:00Z',
      };

      const orderAttention: OutboxOrder = {
        client_uuid: 'uuid-attn-1',
        payload: { client_uuid: 'uuid-attn-1', customer_id: 2, lines: [] },
        customer_id: 2,
        customer_name: 'Murugan Supermarket',
        lines: [
          {
            product_id: 2,
            product_name: 'Murukku 500 g',
            quantity_packets: 10,
            unit_price_paise: 12000,
            line_total_paise: 120000,
          },
        ],
        total_amount_paise: 120000,
        status: 'needs_attention',
        attempts: 1,
        last_error: 'Credit limit breached by 50,000 paise',
        created_at: '2026-11-26T10:05:00Z',
      };

      const orderSent: OutboxOrder = {
        client_uuid: 'uuid-sent-1',
        payload: { client_uuid: 'uuid-sent-1', customer_id: 1, lines: [] },
        customer_id: 1,
        customer_name: 'Annapoorna Sweets',
        lines: [],
        total_amount_paise: 50000,
        status: 'sent',
        server_order_no: 'ORD-2026-0001',
        attempts: 1,
        created_at: '2026-11-26T09:00:00Z',
      };

      await saveToOutbox(orderSent);
      await saveToOutbox(orderQueued);
      await saveToOutbox(orderAttention);

      render(
        <MemoryRouter>
          <SalesmanOrdersList />
        </MemoryRouter>
      );

      // Verify "Waiting to send" chip is displayed
      await waitFor(() => {
        expect(screen.getByTestId('chip-waiting-to-send')).toBeInTheDocument();
      });
      expect(screen.getByText('Waiting to send')).toBeInTheDocument();

      // Verify "Needs attention" chip and the server reason are displayed
      expect(screen.getByTestId('chip-needs-attention')).toBeInTheDocument();
      expect(screen.getByText('Needs attention')).toBeInTheDocument();
      expect(screen.getByText('Credit limit breached by 50,000 paise')).toBeInTheDocument();

      // Verify Sent chip
      expect(screen.getByTestId('chip-sent')).toBeInTheDocument();
      expect(screen.getByText('ORD-2026-0001')).toBeInTheDocument();

      // Verify Edit and Discard buttons are available on needs_attention row
      expect(screen.getByTestId('edit-button')).toBeInTheDocument();
      expect(screen.getByTestId('discard-button')).toBeInTheDocument();
    });
  });
});
