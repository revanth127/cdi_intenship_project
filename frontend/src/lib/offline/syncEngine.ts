import { getOutboxOrders, updateOutboxOrder } from './db';
import type { OutboxOrder, SyncEngineStatus } from './types';
import { getAccessToken } from '@/lib/api/client';

let isSyncRunning = false;
let isPausedForAuth = false;
let syncIntervalId: any = null;
let onAuthRequiredCallback: (() => void) | null = null;

export const MAX_BACKOFF_SECONDS = 300; // 5 minutes cap

/**
 * Calculates exponential backoff delay in seconds:
 * Attempt 1: 5s
 * Attempt 2: 10s
 * Attempt 3: 20s
 * Attempt 4: 40s
 * Attempt 5: 80s
 * Attempt 6: 160s
 * Attempt 7+: 300s (capped at 5 minutes)
 */
export function calculateBackoffSeconds(attempts: number): number {
  if (attempts <= 0) return 0;
  const delay = Math.pow(2, attempts - 1) * 5;
  return Math.min(MAX_BACKOFF_SECONDS, delay);
}

export function setOnAuthRequired(callback: (() => void) | null): void {
  onAuthRequiredCallback = callback;
}

export function getIsPausedForAuth(): boolean {
  return isPausedForAuth;
}

export function resumeSyncAfterAuth(): void {
  isPausedForAuth = false;
  flushOutbox({ force: true });
}

export function resetSyncEngineState(): void {
  isSyncRunning = false;
  isPausedForAuth = false;
  if (syncIntervalId) {
    clearInterval(syncIntervalId);
    syncIntervalId = null;
  }
}

/**
 * Sends a single order to POST /orders (or /api/v1/orders) using fetch with in-memory token.
 */
export async function sendOrderToServer(
  order: OutboxOrder
): Promise<{ success: boolean; data?: any; status: number; errorMsg?: string }> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const payload = order.payload || {
    client_uuid: order.client_uuid,
    customer_id: order.customer_id,
    lines: order.lines.map((l) => ({
      product_id: l.product_id,
      quantity_packets: l.quantity_packets,
      unit_price_paise: l.unit_price_paise,
    })),
    notes: order.notes,
  };

  try {
    const res = await fetch('/api/v1/orders', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    let resData: any = null;
    try {
      resData = await res.json();
    } catch {
      // Non-json response
    }

    // Success response: 200 OK (e.g. duplicate client_uuid returned) or 201 Created
    if (res.ok || res.status === 200 || res.status === 201) {
      return { success: true, data: resData, status: res.status };
    }

    // 409 conflict that returns an existing order with same client_uuid is also treated as success
    if (res.status === 409 && resData && (resData.order_no || resData.id)) {
      return { success: true, data: resData, status: 200 };
    }

    // Extract detail message
    let detailMsg = `Server returned HTTP ${res.status}`;
    if (resData) {
      if (typeof resData.detail === 'string') {
        detailMsg = resData.detail;
      } else if (Array.isArray(resData.detail)) {
        detailMsg = resData.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
      }
    }

    return { success: false, status: res.status, errorMsg: detailMsg };
  } catch (netErr: any) {
    return {
      success: false,
      status: 0,
      errorMsg: netErr.message || 'Network unreachable or offline',
    };
  }
}

/**
 * Flushes the outbox:
 *  - Sends one order at a time
 *  - Oldest first
 *  - Exponential backoff
 *  - Handles 401 (pauses) and 4xx (needs_attention)
 */
export async function flushOutbox(options?: { force?: boolean }): Promise<void> {
  if (isSyncRunning || isPausedForAuth) {
    return;
  }

  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    notifyStatusChange();
    return;
  }

  isSyncRunning = true;
  notifyStatusChange();

  try {
    const orders = await getOutboxOrders();
    // Eligible orders: queued or sending, sorted oldest first
    const pendingOrders = orders
      .filter((o) => o.status === 'queued' || o.status === 'sending')
      .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());

    // Process one order at a time, oldest first
    for (const order of pendingOrders) {
      if (isPausedForAuth) break;
      if (typeof navigator !== 'undefined' && !navigator.onLine) break;

      // Check exponential backoff delay based on attempts
      if (!options?.force && order.attempts > 0 && order.last_attempt_at) {
        const backoffSec = calculateBackoffSeconds(order.attempts);
        const elapsedSec = (Date.now() - new Date(order.last_attempt_at).getTime()) / 1000;
        if (elapsedSec < backoffSec) {
          // Backoff not elapsed yet; skip this order
          continue;
        }
      }

      // Mark order as 'sending'
      await updateOutboxOrder(order.client_uuid, { status: 'sending' });
      notifyStatusChange();

      const result = await sendOrderToServer(order);

      if (result.success) {
        // Success: store server order number and mark sent
        await updateOutboxOrder(order.client_uuid, {
          status: 'sent',
          server_order_no: result.data?.order_no || 'ORD-SENT',
          server_order_id: result.data?.id,
          sent_at: new Date().toISOString(),
          last_error: undefined,
        });
        notifyStatusChange();
        continue;
      }

      // Failure Handling:
      if (result.status === 401) {
        // 401: Authentication session expired.
        // Pause syncing, keep order queued, prompt salesman to log in again.
        isPausedForAuth = true;
        await updateOutboxOrder(order.client_uuid, {
          status: 'queued',
          last_error: 'Session expired. Please sign in to resume sync.',
        });
        notifyStatusChange();
        if (onAuthRequiredCallback) {
          onAuthRequiredCallback();
        }
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('sync:auth-required'));
        }
        break;
      } else if (result.status >= 400 && result.status < 500) {
        // 4xx: Business validation or permission error (e.g. 422 unassigned customer, 400 bad data)
        // Stop retrying this order! Mark 'needs_attention' with server error message.
        await updateOutboxOrder(order.client_uuid, {
          status: 'needs_attention',
          last_error: result.errorMsg || `Client error (${result.status})`,
          attempts: order.attempts + 1,
          last_attempt_at: new Date().toISOString(),
        });
        notifyStatusChange();
      } else {
        // 5xx or Network error (status 0): keep queued with exponential backoff
        await updateOutboxOrder(order.client_uuid, {
          status: 'queued',
          attempts: order.attempts + 1,
          last_error: result.errorMsg || 'Connection error. Retrying...',
          last_attempt_at: new Date().toISOString(),
        });
        notifyStatusChange();
      }
    }
  } catch (err) {
    console.error('Error during outbox flush:', err);
  } finally {
    isSyncRunning = false;
    notifyStatusChange();
  }
}

/**
 * Registers all synchronization triggers:
 *  1. On app start
 *  2. Window online event
 *  3. Document visibility change (user returns to tab)
 *  4. 30-second recurring timer while online
 *  5. Background Sync registration (where supported)
 */
export function initSyncEngine(): () => void {
  // 1. Initial flush on app start
  flushOutbox();

  // 2. Window online event
  const handleOnline = () => {
    flushOutbox();
  };
  const handleOffline = () => {
    notifyStatusChange();
  };

  // 3. Document visibility change (tab becomes visible)
  const handleVisibilityChange = () => {
    if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
      flushOutbox();
    }
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', handleVisibilityChange);
  }

  // 4. Periodic 30-second timer while online
  if (typeof setInterval !== 'undefined') {
    syncIntervalId = setInterval(() => {
      if (typeof navigator !== 'undefined' && navigator.onLine) {
        flushOutbox();
      }
    }, 30000);
  }

  // 5. Background Sync registration where supported (e.g. Chrome, Edge on Android/Desktop)
  if (
    typeof navigator !== 'undefined' &&
    'serviceWorker' in navigator &&
    typeof window !== 'undefined' &&
    'SyncManager' in window
  ) {
    navigator.serviceWorker.ready
      .then((registration: any) => {
        return registration.sync?.register('outbox-order-sync');
      })
      .catch(() => {
        // Fallback for browsers without Background Sync (e.g. Safari on iOS)
      });
  }

  // Cleanup function
  return () => {
    if (typeof window !== 'undefined') {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    }
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    }
    if (syncIntervalId) {
      clearInterval(syncIntervalId);
      syncIntervalId = null;
    }
  };
}

/**
 * Broadcasts sync status to UI components.
 */
export async function getSyncStatus(): Promise<SyncEngineStatus> {
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;
  try {
    const orders = await getOutboxOrders();
    const queuedCount = orders.filter((o) => o.status === 'queued').length;
    const sendingCount = orders.filter((o) => o.status === 'sending').length;
    const needsAttentionCount = orders.filter((o) => o.status === 'needs_attention').length;

    return {
      isOnline,
      isSyncing: isSyncRunning,
      isPausedForAuth,
      queuedCount,
      sendingCount,
      needsAttentionCount,
      totalPendingCount: queuedCount + sendingCount + needsAttentionCount,
    };
  } catch {
    return {
      isOnline,
      isSyncing: false,
      isPausedForAuth: false,
      queuedCount: 0,
      sendingCount: 0,
      needsAttentionCount: 0,
      totalPendingCount: 0,
    };
  }
}

export function notifyStatusChange(): void {
  if (typeof window !== 'undefined') {
    getSyncStatus().then((status) => {
      window.dispatchEvent(new CustomEvent('sync:status-changed', { detail: status }));
    });
  }
}
