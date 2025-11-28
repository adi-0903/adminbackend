# Dudhiya User API Documentation

> **Scope**: This document describes the REST APIs exposed by the `user` Django app. The endpoints are registered in `user/urls.py`.

- **Base path (example)**: `/api/user/`
- All endpoint paths below are **relative** to this base path, e.g. `login/` means `/api/user/login/`.
- Actual base prefix depends on your project-level `urls.py`.

---

## 1. Authentication & Conventions

- **Authentication**
  - `UserLoginView` and `VerifyOTPView` use `AllowAny` (public entry points for login/registration).
  - `ApplyReferralCodeView` and `UserInformationView` use `IsAuthenticated`.
- **Auth mechanism**
  - JWT tokens are generated using `rest_framework_simplejwt.tokens.AccessToken.for_user(user)`.
  - Responses return a `token` string which should be used as `Authorization: Bearer <token>` in subsequent requests (depending on your global DRF/JWT configuration).
- **SMS OTP toggle**
  - Controlled via `settings.USE_OTP_FOR_LOGIN`:
    - If `True`: login is OTP-based (`login/` sends OTP, `verify-otp/` verifies and issues JWT).
    - If `False`: `login/` directly returns a JWT token for an existing user (no OTP).
- **Phone number format**
  - Externally (API): phone numbers are always passed as **10-digit** strings (no `+91` prefix).
  - Internally: stored as `+91XXXXXXXXXX`.

### 1.1 Models (overview)

#### User

Custom user model with fields:

- `phone_number` (unique, validated as `+91` + 10 digits internally).
- `is_active`, `is_staff`, `is_superuser`, `date_joined`.
- `referral_code` (unique 5-character alphanumeric, auto-generated).

Helper methods:

- `soft_delete()` – marks user inactive.
- `check_and_apply_referral_code(referral_code)` – forwards to referral utility and returns `(success, result_dict)`.

#### ReferralUsage

Tracks usage of referral codes between users.

Key concepts (driven by `settings.REFERRAL_SETTINGS`):

- `ENABLED` – global toggle.
- `REFERRER_CREDIT`, `REFEREE_CREDIT` – wallet credit amounts.
- `MAX_REFERRAL_USES`, `MAX_REFEREE_USES`, `MAX_REFERRAL_SYSTEM` – optional usage limits.

Fields:

- `referrer` (User) – who shared the code.
- `referred_user` (User) – who used the code.
- `created_at`, `is_rewarded`.

#### UserInformation

Per-user profile record:

- `user` (OneToOne to `User`).
- `name`, `email`.
- `is_active`, `deleted_at` (soft delete via `delete()`).

---

## 2. Throttling

### 2.1 CustomAnonRateThrottle

Used by `ApplyReferralCodeView`:

- Base class: `AnonRateThrottle` (but view is `IsAuthenticated`; effective rate limiter per IP/user).
- **Rate**: `'100/minute'`.
- On throttle failure, raises `Throttled` with a detailed payload:

```json
{
  "error": "Request was throttled",
  "wait_seconds": 30
}
```

(Example `wait_seconds` value; actual value depends on configuration and usage.)

---

## 3. Login API (UserLoginView)

**Path**: `login/`

- **Method**: `POST`
- **Permissions**: `AllowAny`
- **Serializer**: `UserLoginSerializer`

### 3.1 Request body

```json
{
  "phone_number": "9876543210"
}
```

Validation rules:

- Must be exactly 10 digits.
- Non-digit characters or incorrect length → `400` with error.

### 3.2 Behavior when `USE_OTP_FOR_LOGIN = True`

1. Normalize phone number to `+91` form internally.
2. If user exists with `phone_number = '+91<phone>'`:
   - Call `send_otp(phone_number)` (where `phone_number` is the 10-digit value).
3. If user does **not** exist:
   - Create new `User` with `phone_number = '+91<phone>'`.
   - Then call `send_otp`.

`send_otp` response handling:

- On success: respond with

```json
{
  "message": "OTP sent to the phone number.",
  "verificationId": "<id-from-otp-service>",
  "mobileNumber": "9876543210"
}
```

- On error or timeout:
  - If error message contains "timed out" (network delay):

```json
{
  "message": "OTP request timed out but the OTP might still be delivered. If you receive the OTP, please use it to login.",
  "possible_otp_sent": true
}
```

  with HTTP `202 Accepted`.

  - For all other errors:

```json
{
  "error": "Failed to send OTP. Please try again later."
}
```

  with HTTP `503 Service Unavailable` (error text may be more specific from `send_otp`).

### 3.3 Behavior when `USE_OTP_FOR_LOGIN = False`

- No OTP is sent.
- If user with `+91<phone>` exists:

```json
{
  "token": "<jwt-access-token>",
  "message": "Login successful",
  "user": {
    "id": 1,
    "phone_number": "+919876543210"
  }
}
```

- If no such user exists:

```json
{ "error": "User not found." }
```

### 3.4 Error responses

- Validation failure:
  - `400` with serializer error details.
- Database integrity error:
  - `400` with `{ "error": "Database Error", "detail": "..." }`.
- Unexpected exceptions:
  - `500` with `{ "error": "An unexpected error occurred. Please try again later." }`.

---

## 4. OTP Verification API (VerifyOTPView)

**Path**: `verify-otp/`

- **Method**: `POST`
- **Permissions**: `AllowAny`
- **Serializer**: `VerifyOTPSerializer`

### 4.1 Request body

```json
{
  "phone_number": "9876543210",
  "verificationId": "<id-from-login-response>",
  "otp": "123456"
}
```

Validation:

- `phone_number`: 10-digit numeric.
- `verificationId`: required.
- `otp`: 6-character string.

### 4.2 Behavior when `USE_OTP_FOR_LOGIN = True`

1. Call `verify_otp(phone_number, verificationId, otp)`.
2. If response contains `"error"`:
   - If the error message contains `"timed out"`:

```json
{
  "message": "OTP verification request timed out. Your OTP might still be valid. Please try again.",
  "verification_timeout": true
}
```

HTTP `202 Accepted`.

   - Otherwise:

```json
{ "error": "OTP verification failed" }
```

HTTP `400 Bad Request` (error message may be more specific).

3. On successful verification:
   - Get or create user with `phone_number = '+91<phone>'`.
   - Issue JWT token and return:

```json
{
  "token": "<jwt-access-token>",
  "message": "Login successful",
  "user": {
    "id": 1,
    "phone_number": "+919876543210"
  }
}
```

### 4.3 Behavior when `USE_OTP_FOR_LOGIN = False`

- No external OTP verification is performed.
- The view simply retrieves `User` by `+91<phone>`, issues token, and returns the same response shape.

### 4.4 Error responses

- Serializer validation errors → `400`.
- Unexpected exceptions → `500` with a generic error message.

---

## 5. Apply Referral Code API (ApplyReferralCodeView)

**Path**: `apply-referral-code/`

- **Method**: `POST`
- **Permissions**: `IsAuthenticated`
- **Throttle**: `CustomAnonRateThrottle` (effectively per authenticated client; 100/minute).
- **Serializer**: `ApplyReferralCodeSerializer`

### 5.1 Request body

```json
{
  "referral_code": "ABCDE"
}
```

Validation:

- User must be authenticated (checked in serializer context and view).
- `referral_code` must exist on some `User` record; otherwise `"Invalid referral code"`.

### 5.2 Behavior

1. If `request.user` is not authenticated (should not happen under `IsAuthenticated`):

```json
{ "error": "Authentication required" }
```

2. On valid serializer:
   - Lookup `referrer` by `referral_code`.
   - Call `apply_referral_code(referrer, user)` from `user.utils`.
   - The utility encapsulates referral rules (`REFERRAL_SETTINGS`) and may
     create `ReferralUsage` and wallet bonus transactions.

3. Return values:

- On success (`success == true`):

```json
{
  "message": "<success message>",
  "bonus_earned": "<referee_bonus>"
}
```

- On logical failure (`success == false`):

```json
{ "error": "<reason>" }
```

Other possible errors:

- `User.DoesNotExist` for invalid referral code → `400` with `{ "error": "Invalid referral code" }`.
- `ValidationError` from referral logic → `400` with `{ "error": "<validation message>" }`.
- Throttle limit exceeded → `429` with payload from `CustomAnonRateThrottle`.
- Any uncaught exception is handled by `BaseAPIView.handle_exception`, returning:

```json
{ "error": "An unexpected error occurred" }
```

with status `500`.

---

## 6. User Information API (UserInformationView)

**Path**: `user-info/`

- **Methods**: `GET`, `PUT`
- **Permissions**: `IsAuthenticated`
- **Serializer**: `UserInformationSerializer`

### 6.1 Get current user’s information

- **URL**: `user-info/`
- **Method**: `GET`

Behavior:

1. Try `UserInformation.objects.get(user=request.user)`.
2. If found:
   - Return serialized `UserInformation` data:

```json
{
  "id": 1,
  "name": "Ramesh",
  "email": "ramesh@example.com",
  "phone_number": "+919876543210",
  "referral_code": "ABCDE"
}
```

3. If **not found**:
   - Return a minimal profile derived from `User`:

```json
{
  "name": null,
  "email": null,
  "phone_number": "+919876543210",
  "referral_code": "ABCDE"
}
```

### 6.2 Update current user’s information

- **URL**: `user-info/`
- **Method**: `PUT`

**Request body example**

```json
{
  "name": "Ramesh Kumar",
  "email": "ramesh.k@example.com",
  "phone_number": "9876543210"  // 10-digit; serializer maps to user.phone_number
}
```

Behavior:

1. Fetch or create `UserInformation` for `request.user`.
2. Use `UserInformationSerializer` with `partial=True`.
3. On valid serializer:
   - If `phone_number` included:
     - Validate 10-digit format.
     - Ensure not already used by another user.
     - Save to `user.phone_number` as `+91<phone>`.
   - Update `name` and `email` on `UserInformation`.
4. Return updated data.

Errors:

- Validation errors (invalid phone/email, duplicate phone) → `400` with serializer error details.
- Other exceptions → `400` with `{ "error": "<exception message>" }`.

---

## 7. Summary of Endpoints (Relative Paths)

> Replace `<base>` with your actual app prefix, e.g. `/api/user/`.

- **Login & OTP**
  - `POST <base>/login/` — Start login flow.
    - With OTP enabled: sends OTP and returns `verificationId`.
    - With OTP disabled: returns JWT token for existing user.
  - `POST <base>/verify-otp/` — Verify OTP and obtain JWT token.

- **Referral system**
  - `POST <base>/apply-referral-code/` — Apply a referral code for the authenticated user and (if valid) award referral bonuses.

- **User information**
  - `GET  <base>/user-info/` — Get current user’s profile info (from `UserInformation` or fallback to `User`).
  - `PUT  <base>/user-info/` — Update current user’s name, email, and optionally phone number.
