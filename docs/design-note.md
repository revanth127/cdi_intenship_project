# Stock Ledger & Valuation Design Note

## 1. Why an Immutable Stock Ledger Beats a Mutable Balance Column

In traditional naive CRUD applications, inventory is often modeled as a mutable column:
```sql
-- The Naive Anti-Pattern
UPDATE items SET current_stock = current_stock - 10 WHERE id = 1;
```

While simple, this pattern is dangerous in manufacturing and enterprise accounting for several critical reasons:

### A. Total Loss of Provenance ("How Did We Get Here?")
A mutable column only tells you **what** the balance is right now. It cannot answer:
- Who altered the stock?
- Was a decrease caused by production usage, customer dispatch, theft, or spoilage?
- Which supplier invoice or production batch was responsible for an increase?

In our **Order-to-Audit** architecture, every single inventory change is an immutable entry in `stock_movements`. The current stock is strictly computed:
$$\text{Balance} = \sum \text{quantity\_base}$$

### B. Prevention of Race Conditions and Lost Updates
When two concurrent processes read `stock = 10` and both subtract `8`:
- With mutable updates without locking, both may write `stock = 2`, effectively issuing 16 units when only 10 were available (creating negative inventory).
- In our system, stock reductions strictly acquire a row-level write lock (`SELECT ... FOR UPDATE`) on the `Item` row, verify the aggregate balance from the ledger, and append an immutable signed negative movement. If requested > available, an `InsufficientStockError` (HTTP 409) is raised before any row is written.

### C. Point-in-Time Auditing ("As-Of" Queries)
Financial auditors and tax accountants regularly require inventory valuation as of a specific fiscal close (e.g. midnight March 31):
$$\text{Balance}(t) = \sum_{movement\_date \le t} \text{quantity\_base}$$
With an overwritten balance column, historical reconstruction is impossible without restoring database backups. With our ledger, point-in-time valuation is a native, deterministic SQL aggregation.

### D. Fraud Resistance & Tamper Proofing
Corrections are never made by modifying existing records. If an incorrect purchase was entered, a `CANCELLED` status triggers a reversing movement (`REVERSAL` with a pointer to `reverses_movement_id`). Both the mistake and the correction are permanently preserved in the ledger and the `audit_logs` table.

---

## 2. Moving Weighted Average Valuation Method

Inventory valuation uses the **Moving Weighted Average Cost** method.

### Method Specification:
1. **Receipts (Purchases, Openings, Production Output)**:
   When inventory is received, the per-base-unit cost is recorded with up to 6 decimal places (`Numeric(18, 6)` in paise per base unit) to avoid penny-rounding distortion on bulk purchases.
   $$\text{New Average Cost} = \frac{\text{Current Inventory Value} + \text{Receipt Value}}{\text{Current Quantity} + \text{Receipt Quantity}}$$
   
   *Example*:
   - Opening balance: 100 kg (100,000 g) flour @ Rs 42/kg (4.200000 paise/g) = Rs 4,200 (420,000 paise).
   - Purchase: 60 kg (60,000 g) flour @ Rs 45/kg (4.500000 paise/g) = Rs 2,700 (270,000 paise).
   - Total Quantity = 160,000 g.
   - Total Value = 690,000 paise.
   - New Moving Weighted Average Cost:
     $$\frac{690000 \text{ paise}}{160000 \text{ g}} = 4.312500 \text{ paise/g} = \text{Rs } 43.125\text{/kg}$$
   Stored with full 6-decimal-place precision (`Decimal("4.312500")`).

2. **Issues (Production Consumption, Sales Dispatch, Wastage)**:
   When stock is consumed or issued, it is valued at the current moving weighted average cost at the time of issue:
   $$\text{Issue Value} = \text{ROUND\_HALF\_UP}(\text{Quantity Issued} \times \text{Current Average Unit Cost})$$
   The unit cost of remaining inventory remains unchanged.

3. **Stock Adjustments**:
   Manual inventory adjustments (e.g. physical cycle count discrepancies) require an administrative reason and are valued at the prevailing weighted average cost.


---

## 3. Available-to-Promise (ATP) Inventory & Order Approval Protection

### The Core Problem: Why On-Hand Ledger Balance Alone Leads to Over-Commitment
In high-volume manufacturing and distribution, simply checking `current_stock >= requested` when approving sales orders is a dangerous flaw:
- Suppose current finished goods on hand = 100 packets.
- Salesman A submits Order 1 for 80 packets $\implies$ approved because $100 \ge 80$.
- Before Order 1 is physically dispatched from the warehouse, on-hand ledger balance remains 100 packets.
- If Salesman B submits Order 2 for 80 packets and the system only checks on-hand stock, it would also approve Order 2 ($100 \ge 80$), committing 160 packets against an inventory of only 100.
- When both trucks arrive at the dispatch bay, the warehouse faces an immediate stockout and customer fulfillment crisis.

### The Available-to-Promise (ATP) Rule
In our architecture, sales order verification strictly checks **Available-to-Promise (ATP)**:
$$\text{ATP}(\text{product}) = \text{Finished Goods Ledger Balance} - \sum_{\text{order.status} \in \{\text{APPROVED}, \text{INVOICED}\}} \text{quantity\_packets}$$

Where:
1. **Finished Goods Ledger Balance**:
   The exact, tamper-proof inventory balance derived from `stock_movements`:
   $$\text{Balance} = \sum \text{quantity\_base}$$
2. **Committed to Orders**:
   The sum of packet quantities across all active orders that have been promised/approved or invoiced, but have not yet been deducted from the ledger via a physical `DISPATCH` movement.
3. **Dispatch Reduction**:
   In Phase 6, when an order is dispatched, a `DISPATCH` stock movement decreases the ledger balance, and the order transitions to `DISPATCHED`. This seamlessly transfers the commitment from the order book to the physical ledger with zero double-counting or stock leaks.

### Concurrency Protection & Atomicity
To prevent race conditions where two administrators approve competing orders at the exact same millisecond:
1. The approval transaction strictly acquires an exclusive row-level write lock (`SELECT ... FOR UPDATE`) on the finished goods `Item` record.
2. Under this lock, the system recalculates the current ATP.
3. If $\text{requested} > \text{available}$, approval is blocked with an `HTTP 409 Conflict` response returning a structured shortage breakdown (`requested`, `on_hand`, `committed_elsewhere`, `available`, `shortage`).
4. Only if $\text{available} \ge \text{requested}$ (or if the admin explicitly passes `approve_with_shortage=true`) does the transaction transition the order status to `APPROVED`, atomically reserving the stock before releasing the row lock.
