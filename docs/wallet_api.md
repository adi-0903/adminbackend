# Wallet API Documentation

Base URL: /api/
Authentication: Bearer token (DRF IsAuthenticated on all endpoints)
Pagination: Standard page/page_size on list endpoints

Routers (see `wallet/urls.py`):
- /api/wallet/
- /api/transactions/

Models referenced: see `wallet/models.py`
- Wallet fields (common): id, user, balance, is_active, created_at, updated_at
- WalletTransaction fields (common): id, wallet, amount, transaction_type, status, description, created_at, updated_at

Serializers: see `wallet/serializers.py`
- `WalletSerializer`: exposes phone_number (from user), balance, is_active, created_at, updated_at
- `WalletTransactionSerializer`: exposes phone_number (from wallet.user), wallet, amount, transaction_type, status, description
- `AddMoneySerializer`: amount (>= 0.01)

## Wallet Endpoints
Route: /api/wallet/
ViewSet: `wallet/views.py:WalletViewSet`

- GET /api/wallet/
  - Returns the authenticated user's wallet details (single object).
  - Response: `WalletSerializer`

- PATCH /api/wallet/
  - Partially update wallet (currently supports updating balance via `balance` field).
  - Body:
    - balance: decimal >= 0
  - Notes:
    - Server enforces non-negative balance.

- POST /api/wallet/add_money/
  - Creates a Razorpay payment link and corresponding pending wallet transaction(s).
  - Body (JSON):
    - amount: decimal >= 0.01
  - Response (200):
    - payment_link: short_url to complete payment
    - amount: string
  - Behavior details:
    - Rate-limited by `AddMoneyRateThrottle` (`100/minute` per user).
    - Uses Razorpay payment links, schedules async verification (`wallet/tasks.py:verify_pending_payment`).
    - Also creates a bonus transaction (PENDING) when applicable:
      - >= 1000: 10% bonus
      - >= 500: 5% bonus
    - Concurrency-safe using `select_for_update()` on the wallet.
    - Prevents abuse: If there are 3+ PENDING transactions in the last 30 minutes, returns 400.

- GET /api/wallet/transactions/
  - Paginated list of the authenticated user's wallet transactions.
  - Query params: page, page_size
  - Response: `WalletTransactionSerializer` list (paginated structure)

## Transactions Endpoints
Route: /api/transactions/
ViewSet: `wallet/views.py:WalletTransactionViewSet`

- GET /api/transactions/
  - Paginated list of transactions for the authenticated user's wallet.
  - Query params: page, page_size

- POST /api/transactions/
  - Create a transaction (CREDIT or DEBIT) directly.
  - Body (JSON):
    - wallet: wallet id (belongs to current user)
    - amount: decimal >= 0.01
    - transaction_type: CREDIT | DEBIT
    - status: PENDING | SUCCESS | FAILED (see model choices)
    - description: optional string
  - Logic:
    - For DEBIT, validates sufficient balance. Updates wallet balance atomically.
    - For CREDIT, increments wallet balance.
    - Returns created transaction (status set to SUCCESS on create).

- PATCH /api/transactions/{id}/
  - Partially update a transaction (e.g., status or description).

## Error Codes
- 400: Validation errors, throttling violations, insufficient balance
- 401: Authentication required
- 404: Wallet not found (when listing transactions) or invalid resource id
- 500: Payment creation failure (Razorpay or infra issues)

## Notes
- Razorpay credentials must be present in settings: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`.
- OTP-based login is currently disabled in settings (`USE_OTP_FOR_LOGIN = False`), but unrelated to wallet APIs.
- Background verification of pending payments is handled via Celery; if workers are down, verification may be delayed.
