# Dudhiya Wallet API Documentation

> **Scope**: This document describes the REST APIs exposed by the `wallet` Django app. All endpoints are registered via DRF `DefaultRouter` in `wallet/urls.py`.

- **Base path (example)**: `/api/wallet/`
- All endpoint paths below are **relative** to this base path, e.g. `wallet/` means `/api/wallet/wallet/`.
- Actual base prefix depends on your project-level `urls.py`.

---

## 1. Authentication & Conventions

- **Authentication**
  - `WalletViewSet` and `WalletTransactionViewSet` use `IsAuthenticated`.
  - `RazorpayWebhookView` uses `AllowAny` (secured by signature header).
- **Ownership**
  - `WalletViewSet` always operates on the **authenticated user’s** wallet.
  - `WalletTransactionViewSet` filters `WalletTransaction` by `wallet__user = request.user`.
- **Soft delete**
  - `Wallet` and `WalletTransaction` use `SoftDeletionManager`.
  - Soft-deleted rows are hidden from default queries (`objects`), but available via `all_objects`.
- **Content type**
  - Standard endpoints: JSON (`application/json`).
  - Webhook: JSON request body from Razorpay; response is an empty `200/400` HTTP response.

### 1.1 Pagination

The wallet app defines `StandardResultsSetPagination`:

- **Query params**
  - `page`: Page number (1-based).
  - `page_size`: Optional; default `50`, max `1000`.

Paginated responses follow DRF’s standard format:

```json
{
  "count": 10,
  "next": "<url or null>",
  "previous": "<url or null>",
  "results": [ ... ]
}
```

### 1.2 Common model concepts

#### Wallet

- One-to-one with `User` (`user.wallet`).
- `balance` is a non-negative `Decimal` (2 decimal places).
- `is_active` and `is_deleted` flags control availability.
- Helper methods:
  - `add_balance(amount)`
  - `subtract_balance(amount)`
  - `set_balance(amount)`
  - `soft_delete()`

#### WalletTransaction

- Linked to a `Wallet`.
- `transaction_type` (choices): `CREDIT`, `DEBIT`.
- `status` (choices): `PENDING`, `SUCCESS`, `FAILED`.
- Optional Razorpay references: `razorpay_order_id`, `razorpay_payment_id`.
- `parent_transaction` may reference another transaction (e.g. bonus linked to main recharge).

---

## 2. Throttling

### 2.1 AddMoneyRateThrottle

- Applied to all actions of `WalletViewSet`.
- **Rate**: `'100/minute'` per user (as configured in `AddMoneyRateThrottle`).
- Intended to protect the `add_money` endpoint from abuse.

---

## 3. Wallet API

**Router basename**: `wallet` → `wallet/`

Viewset: `WalletViewSet`

Serializer: `WalletSerializer`

### 3.1 Wallet data model (API shape)

```json
{
  "id": 1,
  "phone_number": "+919876543210",
  "balance": "250.00",
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:05:00Z"
}
```

- `phone_number`: sourced from `user.phone_number` (read-only).
- `balance`:
  - Must be `>= 0`.
  - Attempts to set a negative balance will be rejected.

### 3.2 Get current user’s wallet

- **URL**: `wallet/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Returns the authenticated user’s wallet object.

**Response 200**

- JSON object with the wallet fields shown above.

**Response 200 with null** (edge case)

- If, for some reason, the user has no wallet and `get_object()` returns `None`, the serializer would normally fail; in practice you should ensure wallets are created (e.g. on signup) using `Wallet.create_wallet_with_welcome_bonus`.

### 3.3 Update wallet balance (admin / internal)

> Note: The viewset only exposes HTTP methods `GET` and `POST` via `http_method_names`. The `partial_update` method is primarily designed for internal/admin use; expose it over HTTP only if you explicitly enable `PATCH` routing.

- **URL**: `wallet/{id}/`
- **Method**: `PATCH` (if enabled)
- **Auth**: Required

**Request body example**

```json
{
  "balance": "500.00"
}
```

Behavior:

- Uses `Wallet.set_balance()` internally.
- Validates that new balance is non-negative; otherwise returns `400`:

```json
{ "error": "Balance cannot be negative" }
```

---

## 4. Wallet Recharge & Transactions via WalletViewSet

### 4.1 Initiate wallet recharge (create Razorpay order)

- **URL**: `wallet/add_money/`
- **Method**: `POST`
- **Auth**: Required
- **Throttle**: `AddMoneyRateThrottle` (up to 100/minute/user)
- **Description**: Creates a Razorpay order and corresponding pending wallet transaction(s).

**Request body** (validated by `AddMoneySerializer`)

```json
{
  "amount": "1000.00"
}
```

Rules:

- `amount` must be `> 0` (min `0.01`).

Internal logic:

1. Lock the user’s wallet row with `select_for_update()`.
2. Check for existing **pending** wallet transactions in the last 30 minutes:
   - If there are `>= 3` pending, respond with:

```json
{
  "error": "You have too many pending transactions. Please complete them first."
}
```

3. Create a Razorpay order (INR, `payment_capture=1`), with a unique `receipt`.
4. Log the order details.
5. Create a `PENDING` **main** `WalletTransaction` of type `CREDIT` with description `"Wallet Recharge"` and `razorpay_order_id` set.
6. Calculate **bonus** using `calculate_bonus_amount(amount)`:
   - If `amount >= 1000`: 10% bonus, description `"10% bonus on recharge above ₹1000"`.
   - Else if `amount >= 500`: 5% bonus, description `"5% bonus on recharge between ₹500-₹999"`.
   - Otherwise: no bonus.
7. If bonus > 0, create an additional **PENDING** `WalletTransaction` linked via `parent_transaction`.

**Response 200**

```json
{
  "order_id": "order_9A33XWu170gUtm",
  "amount": "1000.00",
  "currency": "INR",
  "key_id": "<RAZORPAY_KEY_ID>"
}
```

Error responses:

- Razorpay bad request → `400` with `{ "error": "<razorpay message>" }`.
- Wallet missing → `404` with `{ "error": "Wallet not found" }`.
- Unexpected error → `500` with `{ "error": "Failed to create order. Please try again later." }`.

### 4.2 List wallet transactions (via WalletViewSet)

- **URL**: `wallet/transactions/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Returns a paginated list of transactions for the current user’s wallet.

Behavior:

- Loads the current user’s wallet.
- Orders transactions by `created_at` descending.

**Response 200 (paginated)**

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "phone_number": "+919876543210",
      "wallet": 1,
      "amount": "1000.00",
      "transaction_type": "CREDIT",
      "status": "SUCCESS",
      "description": "Wallet Recharge",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

If wallet not found:

```json
{ "error": "Wallet not found" }
```

### 4.3 Verify payment from mobile client

- **URL**: `wallet/verify_payment/`
- **Method**: `POST`
- **Auth**: Required
- **Description**: Mobile client calls this after successful Razorpay payment capture, to verify signature and mark the corresponding wallet transaction as successful.

**Request body** (validated by `PaymentVerificationSerializer`)

```json
{
  "order_id": "order_9A33XWu170gUtm",
  "payment_id": "pay_29QQoUBi66xm2f",
  "signature": "<razorpay_signature>",
  "amount": "1000.00"  // optional in serializer, but recommended
}
```

Behavior:

1. Validate serializer (`order_id`, `payment_id`, `signature`, optional `amount > 0`).
2. Generate HMAC signature using `RAZORPAY_KEY_SECRET` and compare with provided signature.
3. On mismatch:
   - Call `mark_transaction_failed(order_id, reason='Signature verification failed')`.
   - Return `400` with `{ "error": "Invalid signature" }`.
4. On match:
   - Parse `captured_amount` (from `amount` if provided, else `0.0`).
   - Call `complete_transaction_success(order_id, payment_id, captured_amount)`.
     - This updates transaction(s) and wallet balance according to your `services` logic.
   - If no transaction found → `404` with `{ "error": "Transaction not found" }`.
   - Else return the updated `WalletTransaction` serialized.

**Response 200** (example)

```json
{
  "id": 1,
  "phone_number": "+919876543210",
  "wallet": 1,
  "amount": "1000.00",
  "transaction_type": "CREDIT",
  "status": "SUCCESS",
  "description": "Wallet Recharge",
  "created_at": "...",
  "updated_at": "..."
}
```

---

## 5. WalletTransaction API (Direct Access)

**Router basename**: `wallet-transaction` → `transactions/`

Viewset: `WalletTransactionViewSet`

Serializer: `WalletTransactionSerializer`

This viewset exposes a more generic transaction API. In many deployments, you may want to restrict create/update here to admins or internal services.

### 5.1 List transactions

- **URL**: `transactions/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Paginated list of transactions for the authenticated user.

Behavior:

- Filters `WalletTransaction` by `wallet__user = request.user`.
- Sorted by `created_at` descending.

### 5.2 Create a transaction (manual credit/debit)

- **URL**: `transactions/`
- **Method**: `POST`
- **Auth**: Required (typically admin/internal)

**Request body (example)**

```json
{
  "amount": "200.00",
  "transaction_type": "DEBIT",   // or CREDIT
  "status": "SUCCESS",
  "description": "Manual adjustment"
}
```

Behavior (atomic):

1. Validate payload (`amount > 0`, transaction_type and status within allowed choices).
2. Lock the user’s wallet row.
3. If `transaction_type == 'DEBIT'`:
   - Check `wallet.balance >= amount`.
   - If insufficient → `400` with `{ "error": "Insufficient balance" }`.
   - Else subtract amount using `F('balance') - amount`.
4. If `transaction_type == 'CREDIT'`:
   - Add amount using `F('balance') + amount`.
5. Save wallet and create a `WalletTransaction` with `status` forcibly set to `SUCCESS`.

**Response 201**: Created transaction serialized.

Error responses:

- Wallet missing → `404` with `{ "error": "Wallet not found" }`.
- Other errors → `400` with `{ "error": "<message>" }`.

### 5.3 Retrieve a transaction

- **URL**: `transactions/{id}/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Returns a single transaction belonging to the authenticated user.

### 5.4 Update transaction status (partial)

> As with `WalletViewSet`, only `GET` and `POST` are declared in `http_method_names` by default. The `partial_update` method is available in the class but may require enabling `PATCH` in routing if you want to use it over HTTP.

- **URL**: `transactions/{id}/`
- **Method**: `PATCH` (if enabled)

**Request body example**

```json
{
  "status": "FAILED"
}
```

Behavior:

- Validates the new status (`PENDING`, `SUCCESS`, `FAILED`).
- Saves updated transaction and returns the full serialized object.

---

## 6. Razorpay Webhook API

View: `RazorpayWebhookView` (`APIView`)

- **URL**: `razorpay/webhook/`
- **Method**: `POST`
- **Auth**: None (`AllowAny`), secured by `X-Razorpay-Signature` header.
- **Content-Type**: JSON (Razorpay standard webhook payload).

### 6.1 Signature verification

Headers and configuration:

- `X-Razorpay-Signature` (HTTP header `HTTP_X_RAZORPAY_SIGNATURE`)
- Secret used:
  - `settings.RAZORPAY_WEBHOOK_SECRET` if set, otherwise `settings.RAZORPAY_KEY_SECRET`.

Verification process:

1. Read raw `request.body` as `payload`.
2. Compute HMAC SHA256 using the webhook secret.
3. Compare with header signature using `hmac.compare_digest`.
4. If header missing or invalid → return `400`.

### 6.2 Payload handling

Razorpay payload example (simplified):

```json
{
  "event": "payment.captured",
  "payload": {
    "payment": {
      "entity": {
        "id": "pay_29QQoUBi66xm2f",
        "order_id": "order_9A33XWu170gUtm",
        "status": "captured",
        "amount": 100000
      }
    }
  }
}
```

Extracted fields:

- `event`
- `payment_entity = payload.payment.entity`
  - `order_id`
  - `id` (payment_id)
  - `status` (e.g. `captured`, `failed`, `cancelled`)
  - `amount` (integer, in paise)

Amount handling:

- If `amount` not null:
  - Convert to `Decimal(str(amount)) / Decimal('100')` to get INR.

### 6.3 Business logic

- If `event == 'payment.captured'` **or** `status == 'captured'`:
  - Call `complete_transaction_success(order_id, payment_id, amount_decimal)`.
- If `status` in `{ 'failed', 'cancelled' }`:
  - Call `mark_transaction_failed(order_id, reason=status_value)`.
- Returns HTTP `200` regardless once processed.

> Note: The webhook **does not** return any JSON body; only a status code. Razorpay expects `2xx` responses for successful processing.

---

## 7. Summary of Endpoints (Relative Paths)

> Replace `<base>` with your actual app prefix, e.g. `/api/wallet/`.

- **WalletViewSet (`wallet/`)**
  - `GET   <base>/wallet/`  — Get current user’s wallet.
  - `POST  <base>/wallet/`  — (Default DRF create; in practice wallet is usually created elsewhere.)
  - `POST  <base>/wallet/add_money/`  — Initiate Razorpay wallet recharge.
  - `GET   <base>/wallet/transactions/`  — List wallet transactions for current user.
  - `POST  <base>/wallet/verify_payment/`  — Verify Razorpay payment from client.
  - *(Optionally, if enabled)* `PATCH <base>/wallet/{id}/` — Set wallet balance.

- **WalletTransactionViewSet (`transactions/`)**
  - `GET   <base>/transactions/`  — List user’s wallet transactions.
  - `POST  <base>/transactions/`  — Create a credit/debit transaction (manual/administrative).
  - `GET   <base>/transactions/{id}/`  — Retrieve transaction.
  - *(Optionally, if enabled)* `PATCH <base>/transactions/{id}/`  — Update transaction status.

- **Razorpay Webhook**
  - `POST  <base>/razorpay/webhook/`  — Razorpay sends payment events here; no auth, signature-based verification.
