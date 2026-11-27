# Manual Test Script: Offline Order Capture in Chrome DevTools

This document provides a concise step-by-step verification guide for field testing the offline order booking capability of the Salesman Mobile Web App.

---

## Prerequisites
1. Start the backend: `cd backend && uvicorn app.main:app --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. Open Google Chrome at `http://localhost:3000` (or the mobile responsive view via DevTools `Ctrl+Shift+M` / `Cmd+Shift+M`).

---

## Test Scenario 1: Reference Cache & Offline Order Booking

### Step 1: Pre-warm Reference Cache while Online
1. In Chrome DevTools, ensure Network is set to **"No throttling" (Online)**.
2. Navigate to **New Order** (`/orders/new`).
3. Notice:
   - Top bar indicator displays green dot with text **"Online"**.
   - Customer dropdown contains Madurai retailers (e.g., *Annapoorna Sweets*, *Murugan Supermarket*).
   - Product table lists active items with standard prices (e.g., *Murukku 200 g* @ ₹50.00).
4. Open Chrome DevTools -> **Application** tab -> **IndexedDB** -> `order_to_audit_salesman_db` -> `reference_cache`.
   - Verify `customers` and `products` keys exist with valid `fetched_at` timestamps.

### Step 2: Simulate Field Disconnection (Go Offline)
1. In Chrome DevTools, open the **Network** panel.
2. Switch the throttling dropdown from **No throttling** to **Offline**.
3. Observe UI updates immediately:
   - Top bar shows amber indicator with **"Offline"**.
   - Header banner shows: **"Prices as of 26 Nov 2026, 10:42"** (or cached timestamp).
   - Review strip appears: *"You are currently offline. This order will be saved on this phone and sent automatically when connectivity returns."*
   - Order button transitions from "Submit order" to **"Save order"**.

### Step 3: Book an Order Offline
1. Select customer **"Annapoorna Sweets"**.
2. Add quantity: `20` packets of *Murukku 200 g*.
3. Add instructions: *"Offline test order for morning dispatch"*.
4. Click **"Save order"**.
5. Observe the Success Screen:
   - Title: **"Saved on this phone"**.
   - Subtitle: *"Your order has been recorded securely in the local device outbox. It will sync automatically as soon as internet connectivity returns."*
   - Status: `QUEUED (WAITING TO SEND)`.

### Step 4: Verify Outbox in My Orders
1. Click **"View My Orders"** (or navigate to `/orders/my`).
2. Observe:
   - Queued orders are pinned to the top.
   - Status badge is a gray chip reading **"Waiting to send"** with clock icon.
   - Server Ref shows: `Queued on phone`.
3. Check Chrome DevTools -> **Application** -> **IndexedDB** -> `outbox`:
   - Order record is present with `status: "queued"`, `attempts: 0`, and `client_uuid` (crypto UUID).

---

## Test Scenario 2: Automatic Reconnect & Background Flush

### Step 1: Restore Network Connectivity
1. In DevTools Network tab, switch back to **"No throttling" (Online)**.
2. Notice:
   - Top bar immediately detects connectivity and displays **"Online"** (or transiently **"Sending 1 order"**).
   - The sync engine triggers immediately on the `window.online` event.
   - Network panel records a single `POST /api/v1/orders` request with the queued `client_uuid`.
   - Server responds with HTTP `201 Created` returning the generated order number (e.g., `ORD-2026-XXXX`).

### Step 2: Confirm Outbox Status Transition
1. In **My Orders**, observe:
   - The status chip automatically flips to green **"Sent"** with checkmark icon.
   - The server reference column now displays the confirmed server order number (e.g. `ORD-2026-0001`).
   - In IndexedDB `outbox`, `status` is now `"sent"` and `server_order_no` is stored.

---

## Test Scenario 3: Lost Response / Retry Idempotency

1. Take another order while online.
2. In DevTools Network, block `/api/v1/orders` response or simulate dropped connection during response transmission.
3. Because the order was saved in IndexedDB with a unique `client_uuid` before transmitting, the sync engine retries sending the same `client_uuid` on the next cycle.
4. The backend recognizes the identical `client_uuid`, returns the original order with HTTP `200 OK`, avoiding duplicate order creation in the database.
5. Outbox transitions to **"Sent"** without creating duplicate entries.

---

## Test Scenario 4: Validation Error (422) & Discard/Edit

1. Create an order with an invalid or unassigned customer (e.g. customer territory mismatch).
2. Sync engine receives HTTP `422 Unprocessable Entity` with error detail: *"Customer is not assigned to this salesman"*.
3. Observe:
   - Sync stops retrying this invalid order (retries are aborted).
   - In **My Orders**, the order displays a red **"Needs attention"** chip with the server reason.
   - Action buttons **Edit** (pencil icon) and **Discard** (trash icon) appear on that row.
   - Salesman can click **Edit** to correct the customer/lines or **Discard** to purge it from the outbox.

---

## Test Scenario 5: Security & Sign Out Warning

1. With at least 1 unsent order in the outbox, click **"Sign out"** in the top bar.
2. Observe:
   - A warning dialog pops up: **"Unsent Orders Warning"**.
   - Informs salesman that `1 unsent order` is saved locally and will be permanently erased.
   - Clicking **Cancel** preserves the queue.
   - Clicking **"Erase & Sign Out"** confirms deletion:
     - Outbox and reference cache are completely wiped via `clearAllOfflineData()`.
     - Salesman is redirected to `/login`.
