import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  saveToOutbox,
  getOutboxOrders,
  getOutboxOrder,
  updateOutboxOrder,
  deleteFromOutbox,
  setCachedReference,
  getCachedReference,
  getUnsentOrdersCount,
  clearAllOfflineData,
  resetDBPromise,
} from '../db';
import {
  calculateBackoffSeconds,
  flushOutbox,
  resumeSyncAfterAuth,
  getIsPausedForAuth,
  resetSyncEngineState,
  MAX_BACKOFF_SECONDS,
} from '../syncEngine';
import { formatPricesAsOf } from '@/features/salesman/SalesmanOrderPage';
import type { OutboxOrder } from '../types';

describe('Offline Order Sync & Reference Cache', () => {
  beforeEach(async () => {
    resetDBPromise();
    resetSyncEngineState();
    await clearAllOfflineData();
    vi.restoreAllMocks();
  });

  afterEach(async () => {
    resetSyncEngineState();
    await clearAllOfflineData();
    resetDBPromise();
  });

  describe('1. Exponential Backoff Calculation', () => {
    it('increases exponentially and caps at 300 seconds (5 minutes)', () => {
      expect(calculateBackoffSeconds(0)).toBe(0);
      expect(calculateBackoffSeconds(1)).toBe(5); // 5 * 2^0
      expect(calculateBackoffSeconds(2)).toBe(10); // 5 * 2^1
      expect(calculateBackoffSeconds(3)).toBe(20); // 5 * 2^2
      expect(calculateBackoffSeconds(4)).toBe(40); // 5 * 2^3
      expect(calculateBackoffSeconds(5)).toBe(80); // 5 * 2^4
      expect(calculateBackoffSeconds(6)).toBe(160); // 5 * 2^5
      expect(calculateBackoffSeconds(7)).toBe(300); // capped at 300
      expect(calculateBackoffSeconds(10)).toBe(MAX_BACKOFF_SECONDS);
      expect(calculateBackoffSeconds(100)).toBe(300);
    });
  });

  describe('2. Offline Submit Queues Order & Online Sends Once', () => {
    it('offline submit queues the order; coming online sends it once', async () => {
      const client_uuid = 'test-offline-uuid-1';
      const order: OutboxOrder = {
        client_uuid,
        payload: {
          client_uuid,
          customer_id: 1,
          lines: [{ product_id: 1, quantity_packets: 10, unit_price_paise: 5000 }],
        },
        customer_id: 1,
        customer_name: 'Annapoorna Sweets',
        lines: [
          {
            product_id: 1,
            product_name: 'Murukku 200 g',
            quantity_packets: 10,
            unit_price_paise: 5000,
            line_total_paise: 50000,
          },
        ],
        total_amount_paise: 50000,
        status: 'queued',
        attempts: 0,
        created_at: new Date().toISOString(),
      };

      // 1. Order saved to local outbox while offline
      await saveToOutbox(order);
      const saved = await getOutboxOrder(client_uuid);
      expect(saved).toBeDefined();
      expect(saved?.status).toBe('queued');

      // 2. Setup mock fetch for online synchronization
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({ id: 99, order_no: 'ORD-2026-0099', client_uuid }),
      });
      globalThis.fetch = fetchSpy;

      // 3. Coming online: flush outbox
      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
      await flushOutbox();

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const sentOrder = await getOutboxOrder(client_uuid);
      expect(sentOrder?.status).toBe('sent');
      expect(sentOrder?.server_order_no).toBe('ORD-2026-0099');

      // 4. Subsequent flush does NOT resend already sent order
      await flushOutbox();
      expect(fetchSpy).toHaveBeenCalledTimes(1); // Still 1
    });
  });

  describe('3. Idempotency with client_uuid', () => {
    it('retrying the same client_uuid after a lost response results in one order', async () => {
      const client_uuid = 'uuid-idempotent-key-42';
      const order: OutboxOrder = {
        client_uuid,
        payload: {
          client_uuid,
          customer_id: 2,
          lines: [{ product_id: 2, quantity_packets: 5, unit_price_paise: 12000 }],
        },
        customer_id: 2,
        customer_name: 'Murugan Supermarket',
        lines: [
          {
            product_id: 2,
            product_name: 'Murukku 500 g',
            quantity_packets: 5,
            unit_price_paise: 12000,
            line_total_paise: 60000,
          },
        ],
        total_amount_paise: 60000,
        status: 'queued',
        attempts: 1,
        created_at: new Date().toISOString(),
      };

      await saveToOutbox(order);

      // Backend returns HTTP 200 with existing order when same client_uuid is sent
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          id: 42,
          order_no: 'ORD-2026-0042',
          client_uuid,
          duplicate: true,
        }),
      });
      globalThis.fetch = fetchSpy;

      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
      await flushOutbox({ force: true });

      expect(fetchSpy).toHaveBeenCalledTimes(1);
      const updated = await getOutboxOrder(client_uuid);
      expect(updated?.status).toBe('sent');
      expect(updated?.server_order_no).toBe('ORD-2026-0042');
    });
  });

  describe('4. FIFO Queue Processing', () => {
    it('orders are sent oldest first, one at a time', async () => {
      const order1: OutboxOrder = {
        client_uuid: 'uuid-order-1-oldest',
        payload: { client_uuid: 'uuid-order-1-oldest', customer_id: 1, lines: [] },
        customer_id: 1,
        customer_name: 'Cust 1',
        lines: [],
        total_amount_paise: 1000,
        status: 'queued',
        attempts: 0,
        created_at: '2026-11-26T08:00:00.000Z',
      };

      const order2: OutboxOrder = {
        client_uuid: 'uuid-order-2-middle',
        payload: { client_uuid: 'uuid-order-2-middle', customer_id: 2, lines: [] },
        customer_id: 2,
        customer_name: 'Cust 2',
        lines: [],
        total_amount_paise: 2000,
        status: 'queued',
        attempts: 0,
        created_at: '2026-11-26T08:30:00.000Z',
      };

      const order3: OutboxOrder = {
        client_uuid: 'uuid-order-3-newest',
        payload: { client_uuid: 'uuid-order-3-newest', customer_id: 3, lines: [] },
        customer_id: 3,
        customer_name: 'Cust 3',
        lines: [],
        total_amount_paise: 3000,
        status: 'queued',
        attempts: 0,
        created_at: '2026-11-26T09:00:00.000Z',
      };

      // Save in scrambled order
      await saveToOutbox(order3);
      await saveToOutbox(order1);
      await saveToOutbox(order2);

      const receivedOrderUuids: string[] = [];
      const fetchSpy = vi.fn().mockImplementation(async (_, init) => {
        const body = JSON.parse(init.body);
        receivedOrderUuids.push(body.client_uuid);
        return {
          ok: true,
          status: 201,
          json: async () => ({ id: Math.random(), order_no: `ORD-${body.client_uuid}` }),
        };
      });
      globalThis.fetch = fetchSpy;

      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
      await flushOutbox();

      expect(receivedOrderUuids).toEqual([
        'uuid-order-1-oldest',
        'uuid-order-2-middle',
        'uuid-order-3-newest',
      ]);
    });
  });

  describe('5. Error Handling: 401 Auth Pause & 422 Validation Error', () => {
    it('401 pauses sync and resumes after login', async () => {
      const orderA: OutboxOrder = {
        client_uuid: 'uuid-order-auth-test',
        payload: { client_uuid: 'uuid-order-auth-test', customer_id: 1, lines: [] },
        customer_id: 1,
        customer_name: 'Customer Auth',
        lines: [],
        total_amount_paise: 10000,
        status: 'queued',
        attempts: 0,
        created_at: new Date().toISOString(),
      };
      await saveToOutbox(orderA);

      // Server returns 401
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ detail: 'JWT expired' }),
      });
      globalThis.fetch = fetchSpy;

      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
      await flushOutbox();

      // Check paused
      expect(getIsPausedForAuth()).toBe(true);
      const after401 = await getOutboxOrder('uuid-order-auth-test');
      expect(after401?.status).toBe('queued');
      expect(after401?.last_error).toContain('Session expired');

      // Subsequent flush while paused is blocked
      await flushOutbox();
      expect(fetchSpy).toHaveBeenCalledTimes(1);

      // Resume after login
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 201,
        json: async () => ({ id: 55, order_no: 'ORD-RESUMED' }),
      });

      resumeSyncAfterAuth();
      expect(getIsPausedForAuth()).toBe(false);

      // Allow flush to complete
      await new Promise((r) => setTimeout(r, 50));
      const finalOrder = await getOutboxOrder('uuid-order-auth-test');
      expect(finalOrder?.status).toBe('sent');
      expect(finalOrder?.server_order_no).toBe('ORD-RESUMED');
    });

    it('422 moves the order to needs_attention and stops retrying it', async () => {
      const orderBad: OutboxOrder = {
        client_uuid: 'uuid-order-validation-err',
        payload: { client_uuid: 'uuid-order-validation-err', customer_id: 99, lines: [] },
        customer_id: 99,
        customer_name: 'Unassigned Customer',
        lines: [],
        total_amount_paise: 5000,
        status: 'queued',
        attempts: 0,
        created_at: new Date().toISOString(),
      };
      await saveToOutbox(orderBad);

      const fetchSpy = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Customer 99 is not assigned to this salesman territory' }),
      });
      globalThis.fetch = fetchSpy;

      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
      await flushOutbox();

      const orderUpdated = await getOutboxOrder('uuid-order-validation-err');
      expect(orderUpdated?.status).toBe('needs_attention');
      expect(orderUpdated?.last_error).toBe('Customer 99 is not assigned to this salesman territory');
      expect(orderUpdated?.attempts).toBe(1);

      // A subsequent flush does not retry needs_attention orders!
      await flushOutbox();
      expect(fetchSpy).toHaveBeenCalledTimes(1); // Not called again!
    });
  });

  describe('6. Reference Cache Stale-While-Revalidate & Timestamp', () => {
    it('reference cache stores fetched_at time and formats correctly when offline', async () => {
      const timestamp = '2026-11-26T10:42:00';
      await setCachedReference('customers', [{ id: 1, name: 'Annapoorna Sweets' }], timestamp);

      const cached = await getCachedReference<any[]>('customers');
      expect(cached).toBeDefined();
      expect(cached?.data[0].name).toBe('Annapoorna Sweets');
      expect(cached?.fetched_at).toBe(timestamp);

      // Test format function matches exact requirement: "Prices as of 26 Nov 2026, 10:42"
      const formatted = formatPricesAsOf(timestamp);
      expect(formatted).toBe('Prices as of 26 Nov 2026, 10:42');
    });
  });

  describe('7. Security: Sign out warning and cache purge', () => {
    it('warns when unsent orders exist and wipes all offline data on confirmed sign out', async () => {
      const order: OutboxOrder = {
        client_uuid: 'uuid-pending-signout',
        payload: { client_uuid: 'uuid-pending-signout', customer_id: 1, lines: [] },
        customer_id: 1,
        customer_name: 'Cust 1',
        lines: [],
        total_amount_paise: 1000,
        status: 'queued',
        attempts: 0,
        created_at: new Date().toISOString(),
      };
      await saveToOutbox(order);
      await setCachedReference('customers', [{ id: 1 }], new Date().toISOString());

      // 1. Unsent orders count is detected
      const unsentCount = await getUnsentOrdersCount();
      expect(unsentCount).toBe(1);

      // 2. Clear all data on confirmed sign out
      await clearAllOfflineData();

      const remainingOrders = await getOutboxOrders();
      expect(remainingOrders.length).toBe(0);

      const cachedCust = await getCachedReference('customers');
      expect(cachedCust).toBeUndefined();

      expect(await getUnsentOrdersCount()).toBe(0);
    });
  });
});
