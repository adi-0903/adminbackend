# Wallet Add Money Flow

This document describes the end-to-end flow for topping up a user's wallet using Razorpay Orders. All endpoints are authenticated with a Bearer token. The base API prefix is `/api/`.

## Overview

1. Mobile app requests an order using `POST /api/wallet/add_money/`.
2. Backend creates a Razorpay Order, records pending wallet transactions (including any bonus), and returns order details.
3. Mobile app launches Razorpay's native SDK/UPI intent with the returned `order_id` and `key_id`.
4. After a successful payment, Razorpay provides `payment_id` and a `signature`. The mobile app sends these to `POST /api/wallet/verify_payment/` to finalize the credit immediately.
5. Razorpay also sends asynchronous webhooks to `/api/wallet/razorpay/webhook/` to reconcile payments (success or failure). The backend verifies the webhook signature before updating wallet state.

## Endpoint: `POST /api/wallet/add_money/`

- **View**: `wallet/views.py:WalletViewSet.add_money`
- **Purpose**: Create a Razorpay Order and record a pending wallet transaction.
- **Request Body** (`application/json`):
  ```json
  {
    "amount": 750.00
  }
  ```
- **Validation**:
  - `amount` must be ≥ 0.01 (see `wallet/serializers.py:AddMoneySerializer`).
  - Throttled per user by `AddMoneyRateThrottle` (`wallet/views.py`).
  - Rejects if the user already has 3 or more `PENDING` transactions created within the last 30 minutes.
- **Processing Steps**:
  - Locks the user's `Wallet` row via `select_for_update()` to ensure atomic updates.
  - Creates a Razorpay Order (`razorpay-python` client) with `payment_capture=1`, unique `receipt`, and amount in paise.
  - Persists a `PENDING` `WalletTransaction` with `transaction_type='CREDIT'` and `razorpay_order_id=order['id']`.
  - Calculates optional recharge bonus using `calculate_bonus_amount()` and creates a child `WalletTransaction` (status `PENDING`) when applicable.
- **Response (200 OK)**:
  ```json
  {
    "order_id": "order_Kya...",
    "amount": "750.00",
    "currency": "INR",
    "key_id": "rzp_test_..."
  }
  ```
- **Error Responses**:
  - `400`: Validation errors (amount, pending transaction limit, Razorpay rejection).
  - `404`: Wallet not found for the authenticated user.
  - `500`: Unexpected exceptions creating the order.

## Launching Razorpay from the Client

The React Native client should:

- Use `key_id` and `order_id` in Razorpay's mobile SDK (or UPI intent) to start payment.
- Provide customer details (name, contact) directly to the SDK if required.
- Handle cancellations gracefully and back off if the server hits throttling limits.

### Expo React Native Checklist

- **Order creation**: Call `POST /api/wallet/add_money/` and persist `order_id`, `amount`, `currency`, and `key_id` locally until verification finishes.
- **Payment launch**: Use a Razorpay-compatible module (e.g., `react-native-razorpay` via the Expo config plugin or your chosen UPI intent bridge) to open the Razorpay checkout with the order payload.
- **Success handler**: Capture `{ razorpay_payment_id, razorpay_order_id, razorpay_signature }` returned by the SDK. Immediately POST these values to `/api/wallet/verify_payment/`.
- **Failure handler**: Surface error codes/messages to the user and consider retry logic after the pending transaction limit cool-down.
- **State updates**: On verification success, refresh wallet balance via `GET /api/wallet/` or update cached state; on failure, show toast/snackbar guidance.
- **Background/webhook awareness**: If the app is backgrounded when payment finishes, still submit verification once the app resumes, because the backend will not credit funds without the signature.

## Endpoint: `POST /api/wallet/verify_payment/`

- **View**: `wallet/views.py:WalletViewSet.verify_payment`
- **Purpose**: Client-side confirmation that the Razorpay signature matches the order and payment.
- **Request Body** (`application/json`):
  ```json
  {
    "order_id": "order_Kya...",
    "payment_id": "pay_Kyb...",
    "signature": "generated_signature",
    "amount": 750.00
  }
  ```
  - `amount` is optional; if provided, it is used for additional logging/validation.
- **Validation**:
  - Ensures all required fields exist (`wallet/serializers.py:PaymentVerificationSerializer`).
  - Recomputes HMAC SHA256 using `RAZORPAY_KEY_SECRET` and compares to submitted signature; rejects if mismatch.
- **Processing Steps**:
  - Calls `wallet/services.py:complete_transaction_success()` to atomically mark the main transaction `SUCCESS`, save the `razorpay_payment_id`, and increment wallet balance using `F` expressions.
  - Updates any `PENDING` bonus child transactions to `SUCCESS` and credits their amounts.
- **Response (200 OK)**:
  - Returns the updated `WalletTransactionSerializer` data (status `SUCCESS`, credited balance reflected).
- **Error Responses**:
  - `400`: Invalid signature or serializer errors.
  - `404`: No matching pending transaction (e.g., order expired or already processed).

## Webhook: `POST /api/wallet/razorpay/webhook/`

- **View**: `wallet/views.py:RazorpayWebhookView`
- **Authentication**: None (Razorpay calls it); signature header check enforced.
- **Configured URL**: `http://dudhiya-backend-version-five-rq4i8f-c4369a-31-97-60-222.traefik.me/api/wallet/razorpay/webhook/`
- **Headers**:
  - `X-Razorpay-Signature`: provided by Razorpay; verified using `RAZORPAY_WEBHOOK_SECRET` (`Milk_Saas/settings.py`).
- **Supported events**:
  - `payment.captured` or payload `status` = `captured`: triggers `complete_transaction_success()`.
  - `failed`/`cancelled`: triggers `mark_transaction_failed()` to clean up pending records.
- **Response**: Always `200 OK` on processed payloads, `400` if signature missing/invalid.

## Bonus Logic

- For recharges ≥ ₹500, the system creates an additional pending credit:
  - ₹500–₹999: 5% bonus.
  - ≥ ₹1000: 10% bonus.
- Bonus transactions inherit the same parent transaction (`parent_transaction` field). When the main payment succeeds, bonuses are marked `SUCCESS` and credited.

## Failure Scenarios

- **Client cancels payment**: Razorpay SDK returns an error; no signature verification call is made. Pending transaction remains `PENDING` until webhook marks it failed or operations team reconciles.
- **Signature mismatch**: Backend logs the attempt, marks the transaction `FAILED`, and returns `400` to client.
- **Razorpay webhook delays**: Client-side verification should still succeed immediately after payment. Webhooks act as redundancy.
- **Amount mismatch**: If webhook-reported amount differs from stored transaction amount, a warning is logged but processing continues (extra verification recommended for reconciliation).

## Environment Variables

- `RAZORPAY_KEY_ID`
- `RAZORPAY_KEY_SECRET`
- `RAZORPAY_WEBHOOK_SECRET` (defaults to key secret if not set)

Ensure these are configured in production and staging environments.

## Frontend Checklist

- Store the `order_id`, `payment_id`, and `signature` returned by Razorpay.
- POST to `/api/wallet/verify_payment/` immediately after successful payment.
- Refresh wallet balance by calling `GET /api/wallet/` or updating local state with the verification response.
- Display errors when verification fails (e.g., signature mismatch or pending too long).

## Monitoring & Logs

- Backend logs creation of Razorpay orders and verification outcomes (`wallet/views.py`).
- `wallet/services.py` logs discrepancies (missing transactions, amount mismatches).
- Webhook failures (invalid signature or payload) are logged for operational visibility.

## Celery Background Tasks

- Legacy payment-link verification tasks remain in `wallet/tasks.py`. They can be repurposed or retired after confirming the new order-based flow is stable.
- Consider creating new Celery jobs to flag long-running `PENDING` orders if needed.
