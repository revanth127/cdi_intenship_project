export type OutboxOrderStatus = 'queued' | 'sending' | 'sent' | 'needs_attention';

export interface OutboxOrderLine {
  product_id: number;
  product_name: string;
  quantity_packets: number;
  unit_price_paise: number;
  line_total_paise: number;
}

export interface OrderPayloadLine {
  product_id: number;
  quantity_packets: number;
  unit_price_paise: number;
}

export interface OrderPayload {
  client_uuid: string;
  customer_id: number;
  lines: OrderPayloadLine[];
  notes?: string;
}

export interface OutboxOrder {
  client_uuid: string; // crypto.randomUUID()
  payload: OrderPayload;
  status: OutboxOrderStatus;
  attempts: number;
  last_error?: string;
  created_at: string; // ISO 8601 string
  server_order_no?: string;
  server_order_id?: number;
  sent_at?: string;
  last_attempt_at?: string;

  // Enriched presentation fields for display and offline rendering:
  customer_id: number;
  customer_name: string;
  lines: OutboxOrderLine[];
  total_amount_paise: number;
  notes?: string;
}

export interface ReferenceCustomer {
  id: number;
  name: string;
  city: string;
  state_code: string;
  credit_limit_paise?: number;
}

export interface ReferenceProduct {
  id: number;
  pack_name: string;
  family_name: string;
  net_weight_g: number;
  packets_per_carton: number;
  standard_price_paise: number;
}

export interface CustomerEffectivePrice {
  customer_id: number;
  product_id: number;
  effective_price_paise: number;
}

export interface ReferenceCacheEntry<T> {
  key: string;
  data: T;
  fetched_at: string; // ISO 8601 string
}

export interface SyncEngineStatus {
  isOnline: boolean;
  isSyncing: boolean;
  isPausedForAuth: boolean;
  queuedCount: number;
  sendingCount: number;
  needsAttentionCount: number;
  totalPendingCount: number;
}
