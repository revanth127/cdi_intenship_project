import { openDB, DBSchema, IDBPDatabase } from 'idb';
import type { OutboxOrder, ReferenceCacheEntry } from './types';

export const DB_NAME = 'order_to_audit_salesman_db';
export const DB_VERSION = 1;

export interface SalesmanDBSchema extends DBSchema {
  outbox: {
    key: string; // client_uuid
    value: OutboxOrder;
    indexes: {
      'by_status': string;
      'by_created_at': string;
    };
  };
  reference_cache: {
    key: string;
    value: ReferenceCacheEntry<any>;
  };
}

let dbPromise: Promise<IDBPDatabase<SalesmanDBSchema>> | null = null;

export function getDB(): Promise<IDBPDatabase<SalesmanDBSchema>> {
  if (!dbPromise) {
    dbPromise = openDB<SalesmanDBSchema>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        // 1. Outbox store
        if (!db.objectStoreNames.contains('outbox')) {
          const outboxStore = db.createObjectStore('outbox', { keyPath: 'client_uuid' });
          outboxStore.createIndex('by_status', 'status');
          outboxStore.createIndex('by_created_at', 'created_at');
        }

        // 2. Reference cache store (customers, products, prices, metadata)
        if (!db.objectStoreNames.contains('reference_cache')) {
          db.createObjectStore('reference_cache', { keyPath: 'key' });
        }
      },
    });
  }
  return dbPromise;
}

/**
 * Saves a new order into the Outbox store.
 */
export async function saveToOutbox(order: OutboxOrder): Promise<void> {
  const db = await getDB();
  await db.put('outbox', order);
}

/**
 * Returns all orders in the outbox sorted with queued/sending/needs_attention first,
 * followed by newest created.
 * Queued orders are listed first, oldest first.
 */
export async function getOutboxOrders(): Promise<OutboxOrder[]> {
  const db = await getDB();
  const orders = await db.getAll('outbox');
  return orders.sort((a, b) => {
    // Priority: queued/sending/needs_attention before sent
    const isPendingA = a.status !== 'sent';
    const isPendingB = b.status !== 'sent';
    if (isPendingA && !isPendingB) return -1;
    if (!isPendingA && isPendingB) return 1;

    // For pending orders, oldest first
    if (isPendingA && isPendingB) {
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    }

    // For sent orders, newest first
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });
}

/**
 * Retrieves a single order by client_uuid.
 */
export async function getOutboxOrder(client_uuid: string): Promise<OutboxOrder | undefined> {
  const db = await getDB();
  return db.get('outbox', client_uuid);
}

/**
 * Updates status, attempts, or server order info for an order in the outbox.
 */
export async function updateOutboxOrder(
  client_uuid: string,
  updates: Partial<OutboxOrder>
): Promise<OutboxOrder | undefined> {
  const db = await getDB();
  const tx = db.transaction('outbox', 'readwrite');
  const existing = await tx.store.get(client_uuid);
  if (!existing) {
    await tx.done;
    return undefined;
  }
  const updated: OutboxOrder = {
    ...existing,
    ...updates,
  };
  await tx.store.put(updated);
  await tx.done;
  return updated;
}

/**
 * Removes an order from the outbox (e.g. salesman discards an unfixable order).
 */
export async function deleteFromOutbox(client_uuid: string): Promise<void> {
  const db = await getDB();
  await db.delete('outbox', client_uuid);
}

/**
 * Reference Cache helpers
 */
export async function setCachedReference<T>(
  key: string,
  data: T,
  fetched_at?: string
): Promise<ReferenceCacheEntry<T>> {
  const db = await getDB();
  const entry: ReferenceCacheEntry<T> = {
    key,
    data,
    fetched_at: fetched_at || new Date().toISOString(),
  };
  await db.put('reference_cache', entry);
  return entry;
}

export async function getCachedReference<T>(key: string): Promise<ReferenceCacheEntry<T> | undefined> {
  const db = await getDB();
  return db.get('reference_cache', key);
}

/**
 * Checks if there are unsent orders in outbox (queued, sending, or needs_attention).
 */
export async function getUnsentOrdersCount(): Promise<number> {
  const db = await getDB();
  const all = await db.getAll('outbox');
  return all.filter((o) => o.status !== 'sent').length;
}

/**
 * Wipes outbox and reference cache completely (e.g. on confirmed sign out).
 */
export async function clearAllOfflineData(): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(['outbox', 'reference_cache'], 'readwrite');
  await tx.objectStore('outbox').clear();
  await tx.objectStore('reference_cache').clear();
  await tx.done;
}

/**
 * Helper to reset connection for tests.
 */
export function resetDBPromise(): void {
  dbPromise = null;
}
