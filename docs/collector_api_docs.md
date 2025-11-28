# Dudhiya Collector API Documentation

> **Scope**: This document describes the REST APIs exposed by the `collector` Django app. All endpoints are registered via DRF `DefaultRouter` in `collector/urls.py`.

- **Base path (example)**: `/api/collector/`
- All endpoint paths below are **relative** to this base path, e.g. `collections/` means `/api/collector/collections/`.
- Actual base prefix depends on your project-level `urls.py`.

---

## 1. Authentication & Conventions

- **Authentication**: Except where noted, endpoints use `IsAuthenticated` and require a valid authenticated user (e.g. JWT, session auth, token, etc. depending on your global DRF setup).
- **Ownership**: Most queries are implicitly filtered by `author = request.user` and `is_active = True`.
- **Soft delete**: Deletions call `soft_delete()` and only mark records as inactive.
- **Content type**: JSON (`application/json`) for standard CRUD; PDF-generating endpoints return `application/pdf`.
- **Timestamps**: `created_at` and `updated_at` are in server time (Django `timezone.now`).

### 1.1 Pagination

`BaseViewSet` uses `StandardResultsSetPagination`:

- **Query params**
  - `page`: Page number (1-based).
  - `page_size`: Optional; default `50`, max `1000`.

Paginated responses follow standard DRF format:

```json
{
  "count": 123,
  "next": "<url or null>",
  "previous": "<url or null>",
  "results": [ ... ]
}
```

### 1.2 Common model fields

All main models inherit from `BaseModel`:

- `id` (int, read-only)
- `author` (user, read-only, set from authenticated user)
- `is_active` (bool, default `true`)
- `created_at` (datetime, read-only)
- `updated_at` (datetime, read-only)

Serializers that inherit from `BaseModelSerializer` treat these as **read-only**.

---

## 2. Market Milk Price API

**Router basename**: `market-milk-price` → `market-milk-prices/`

Model: `MarketMilkPrice`

```json
{
  "id": 1,
  "price": "42.50",
  "is_active": true,
  "created_at": "2024-01-01T10:00:00Z",
  "updated_at": "2024-01-01T10:00:00Z"
}
```

### 2.1 Get current active market milk price

- **URL**: `market-milk-prices/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Returns the **latest active** milk price for the current user.

**Response 200**

```json
{
  "id": 1,
  "price": "42.50",
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

**Response 404**

```json
{ "detail": "No milk price found." }
```

> Note: Regular list pagination is overridden; only a single latest record is returned.

### 2.2 Create new active market milk price

- **URL**: `market-milk-prices/`
- **Method**: `POST`
- **Auth**: Required
- **Description**: Creates a new price for the current user. Any existing active price is **soft-deleted** first.

**Request body**

```json
{
  "price": "45.00"
}
```

Validation:

- `price` must be `> 0`.

**Response 201**: Created object (same schema as above).

**Response 400**: Validation or other error.

### 2.3 Retrieve / Update / Delete specific price

- **URL**: `market-milk-prices/{id}/`
- **Methods**: `GET`, `PUT`, `PATCH`, `DELETE`
- **Auth**: Required

Notes:

- `DELETE` performs a **soft delete**.
- `PUT/PATCH` are wrapped with error handling and return `400` on failure.

---

## 3. Dairy Information API

**Router basename**: `dairy-information` → `dairy-information/`

Model: `DairyInformation`

Key fields:

- `dairy_name` (string, required)
- `dairy_address` (string, optional)
- `rate_type` (optional enum):
  - `kg_only`, `liters_only`, `fat_only`, `fat_snf`, `fat_clr`
- `base_snf` (decimal, optional; typical values 8.5 or 9.0)
- `fat_snf_ratio` (optional enum): `60/40`, `52/48`
- `clr_conversion_factor` (decimal, optional; typically `0.14` or `0.50`)

### 3.1 Get current active dairy information

- **URL**: `dairy-information/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Returns latest active dairy information for current user.

**Response 200**: Single `DairyInformation` record.

**Response 404**

```json
{ "detail": "No dairy information found." }
```

### 3.2 Create dairy information

- **URL**: `dairy-information/`
- **Method**: `POST`
- **Auth**: Required
- **Description**: Creates a new active dairy info; any previous active record for this user is soft-deleted.

**Request body (example)**

```json
{
  "dairy_name": "My Dairy",
  "dairy_address": "Village, District",
  "rate_type": "fat_snf",
  "base_snf": 9.0,
  "fat_snf_ratio": "60/40",
  "clr_conversion_factor": 0.14
}
```

Validation:

- `dairy_name` required and non-empty.
- If `rate_type` is provided, it must be one of the defined choices.
- For the same user, `dairy_name` must be unique among active records (case-insensitive).

### 3.3 Retrieve / Update / Delete

- **URL**: `dairy-information/{id}/`
- **Methods**: `GET`, `PUT`, `PATCH`, `DELETE`
- **Notes**: `DELETE` is soft delete; updates share same validations as create.

---

## 4. Pro Rata Rate Chart API

**Router basename**: `pro-rata-rate-chart` → `pro-rata-rate-chart/`

Model: `ProRataRateChart` with related `FatStepUpRate` and `SnfStepDownRate`.

Serializer shape:

```json
{
  "id": 1,
  "fat_step_up_rates": [
    { "id": 10, "step": "0.10", "rate": "0.50" }
  ],
  "snf_step_down_rates": [
    { "id": 20, "step": "0.10", "rate": "-0.30" }
  ],
  "is_active": true,
  "created_at": "...",
  "updated_at": "..."
}
```

### 4.1 Get current active pro-rata chart

- **URL**: `pro-rata-rate-chart/`
- **Method**: `GET`
- **Auth**: Required
- **Description**: Returns **latest active** chart for current user or 404.

### 4.2 Create a chart

- **URL**: `pro-rata-rate-chart/`
- **Method**: `POST`
- **Auth**: Required
- **Description**: Creates a new chart and optional nested step-up/down rates; any other active charts for user are deactivated.

**Request body example**

```json
{
  "fat_step_up_rates": [
    { "step": 0.10, "rate": 0.50 },
    { "step": 0.20, "rate": 1.00 }
  ],
  "snf_step_down_rates": [
    { "step": 0.10, "rate": -0.30 }
  ]
}
```

### 4.3 Update chart

- **URL**: `pro-rata-rate-chart/{id}/`
- **Method**: `PUT` / `PATCH`

Behavior when sending `fat_step_up_rates` / `snf_step_down_rates`:

- Existing child rows whose `id` is **not** included will be **deleted**.
- Rows with existing `id` will be updated.
- Rows without `id` will be created and linked to the chart.

### 4.4 Delete chart

- **URL**: `pro-rata-rate-chart/{id}/`
- **Method**: `DELETE` (soft delete)

---

## 5. Customer API

**Router basename**: `customer` → `customers/`

Model: `Customer`

Key fields:

- `id` (int, read-only)
- `customer_id` (int, read-only sequence per user)
- `name` (string, required)
- `father_name` (string, optional)
- `phone` (string, optional; stored as `+91XXXXXXXXXX`)
- `village` (string, optional)
- `address` (string, optional)
- `is_active` (bool)

Serializer: `CustomerSerializer`.

### 5.1 List customers

- **URL**: `customers/`
- **Method**: `GET`
- **Auth**: Required
- **Query params**:
  - `search`: optional; searches `name` and `phone` (case-insensitive) if provided.

Additional behavior:

- If total customers for user > 40, page size is temporarily increased to 100.
- Response body may include an extra field:

```json
{
  "count": 45,
  "next": "...",
  "previous": null,
  "results": [ ... ],
  "total_count": 45
}
```

### 5.2 Create customer

- **URL**: `customers/`
- **Method**: `POST`

**Request example**

```json
{
  "name": "Ramesh",
  "father_name": "Suresh",
  "phone": "9876543210",
  "village": "Village A",
  "address": "House 1"
}
```

Validations:

- `name` non-empty.
- If `phone` provided:
  - digits only (after stripping `+` or leading zeros),
  - exactly 10 digits.
- On save, phone is normalized to `+91XXXXXXXXXX` and `customer_id` is auto-assigned (`max(existing)+1`).

### 5.3 Retrieve / Update / Delete customer

- **URL**: `customers/{id}/`
- **Methods**: `GET`, `PUT`, `PATCH`, `DELETE`
- **Notes**: `DELETE` is soft delete.

---

## 6. Collection API

**Router basename**: `collection` → `collections/`

Model: `Collection`

### 6.1 Fields

Main serialized shapes:

- **List** (`CollectionListSerializer`):
  - `id`
  - `collection_time` (`"morning"` | `"evening"`)
  - `milk_type` (`"cow"` | `"buffalo"` | `"cow_buffalo"`)
  - `customer_id` (customer.customer_id, read-only)
  - `customer_name` (read-only)
  - `collection_date` (date)
  - `measured` (`"liters"` | `"kg"`)
  - `liters`, `kg`
  - `fat_percentage`, `fat_kg`
  - `clr` (decimal, nullable)
  - `snf_percentage`, `snf_kg`
  - `fat_rate`, `snf_rate`, `milk_rate`
  - `amount`
  - `solid_weight`
  - `base_snf_percentage`
  - `is_pro_rata` (bool)
  - `is_raw_collection` (bool)

- **Detail** (`CollectionDetailSerializer`): adds more fields:
  - `customer` (FK id)
  - `customer_name`
  - `base_fat_percentage`, `base_snf_percentage`
  - `created_at`, `updated_at`, `is_active`

### 6.2 List collections

- **URL**: `collections/`
- **Method**: `GET`
- **Auth**: Required
- **Query params**:
  - Filtering via `CollectionFilter` and `DjangoFilterBackend`:
    - `collection_time`, `milk_type`, `collection_date`
  - Search: `search` (by `customer__name`)
  - Ordering (via `ordering`): any of
    - `collection_date`, `created_at`, `liters`, `kg`,
      `fat_percentage`, `fat_kg`, `snf_percentage`, `snf_kg`,
      `rate`, `amount`

Returns paginated list using `CollectionListSerializer`.

### 6.3 Retrieve collection

- **URL**: `collections/{id}/`
- **Method**: `GET`
- **Serializer**: `CollectionDetailSerializer`

### 6.4 Create collection

- **URL**: `collections/`
- **Method**: `POST`
- **Auth**: Required

Key logic / validations:

- Request must include at least:
  - `collection_time`, `milk_type`, `customer`, `collection_date`,
  - measure & quantities (`measured`, `liters` / `kg`),
  - composition: `fat_percentage`, `snf_percentage`, etc.
- `base_snf_percentage` must be **between 8.0 and 9.5** (inclusive). Otherwise returns `400`.
- Wallet-based collection fee check:
  - Reads `settings.COLLECTION_FEE` (if `ENABLED`), with `PER_KG_RATE`.
  - Calculates `required_balance = PER_KG_RATE * kg`.
  - If wallet balance is insufficient, returns `400` with details.
- If no wallet exists for user, returns `400`.
- Duplicate prevention:
  - `Collection.save()` raises validation error if an identical collection already exists (same user, customer, date, time, quantities, fat/snf, rates, etc.).

### 6.5 Update collection

- **URL**: `collections/{id}/`
- **Methods**: `PUT`, `PATCH`

Edit restrictions (via `Collection.can_edit()` and settings `COLLECTION_EDIT`):

- If `COLLECTION_EDIT.ENABLED` is false → always editable.
- Else:
  - `edit_count` must be `< MAX_EDIT_COUNT` (default 1).
  - Days since creation must be `<= MAX_EDIT_DAYS` (default 7).
- If constraints violated, returns `400` with clear message and fields `edit_count` / `max_edits` or `days_since_creation` / `max_days`.
- On actual changes, `edit_count` increments and `last_edited_at` updated.

### 6.6 Delete collection

- **URL**: `collections/{id}/`
- **Method**: `DELETE`

Behavior:

- Soft-deletes the collection and returns `200` with message and deleted `id`.

### 6.7 Collection reports (non–pro-rata)

All below are actions on `CollectionViewSet` and use **non-pro-rata** collections (`is_pro_rata=False`).

#### 6.7.1 JSON purchase report (grouped by date)

- **URL**: `collections/purchase-report/`
- **Method**: `GET`
- **Auth**: Required

Returns aggregated data per date, with pagination applied to the list of dates.

Each item contains (field names from aggregation):

- `collection_date`
- `total_weight` (`Sum(kg)`)
- `total_fat_percentage` (`Avg(fat_percentage)`)
- `total_snf_percentage` (`Avg(snf_percentage)`)
- `total_fat_kg` (`Sum(fat_kg)`)
- `total_snf_kg` (`Sum(snf_kg)`)
- `total_amount` (`Sum(amount)`)

#### 6.7.2 PDF purchase report

- **URL**: `collections/generate_purchase_report/`
- **Method**: `GET`
- **Auth**: Required
- **Query params (required)**:
  - `start_date`: `DD-MM-YYYY`
  - `end_date`: `DD-MM-YYYY`

Returns a **PDF file** summarizing daily purchases between dates for non–pro-rata collections.

Errors:

- Missing dates → `400` with message.
- Invalid format → `400`.
- No collections in range → `404`.

#### 6.7.3 PDF purchase summary report

- **URL**: `collections/generate_purchase_summary_report/`
- **Method**: `GET`
- Same query params and error handling as above.
- Returns a **summary PDF** aggregated by customer (party-wise totals and grand totals).

#### 6.7.4 Full report (purchase + summary + customer bills)

- **URL**: `collections/generate_full_report/`
- **Method**: `GET`
- Same `start_date` / `end_date` query params.
- Generates one PDF containing purchase report, summary, and individual customer milk bills.

#### 6.7.5 All customers bills PDF

- **URL**: `collections/generate_full_customer_report/`
- **Method**: `GET`
- **Query params**: `start_date`, `end_date` (`DD-MM-YYYY`)
- Generates only customer-wise milk bill PDFs for all customers having collections in range.

#### 6.7.6 Selected customers report PDF

- **URL**: `collections/generate_customer_report/`
- **Method**: `GET`
- **Query params (all required)**:
  - `start_date` (`DD-MM-YYYY`)
  - `end_date` (`DD-MM-YYYY`)
  - `customer_ids`: comma-separated integers of `Customer.id`.

Returns a PDF containing milk bills for the specified customers only.

#### 6.7.7 JSON purchase summary

- **URL**: `collections/purchase-summary-report/`
- **Method**: `GET`
- **Query params**:
  - `start_date`, `end_date` (`DD-MM-YYYY`)

Returns JSON:

```json
{
  "summary_data": [
    {
      "party_name": "1-Ramesh",
      "phone": "+919876543210",
      "weight": "100.00",
      "fat_kg": "3.500",
      "snf_kg": "8.000",
      "purchase_value": "4500.00",
      "total_amount": "4495.00"  // after bank charges adjustment
    }
  ],
  "grand_totals": {
    "total_weight": 100.00,
    "total_fat_kg": 3.5,
    "total_snf_kg": 8.0,
    "purchase_amount": 4500.00,
    "total_amount": 4495.00,
    "total_solid_weight": 0,
    "customer_count": 1
  }
}
```

---

## 7. Raw Collection API

**Router basename**: `raw-collection` → `raw-collections/`

Model: `RawCollection` (raw entries typically without milk rate; can later be converted into `Collection`).

### 7.1 Fields

Similar to `Collection` but with:

- `clr`, `snf_percentage`, `snf_kg`, `fat_rate`, `snf_rate`, `milk_rate`, `solid_weight`, `amount` all nullable.
- `is_milk_rate` (bool): whether a milk rate has been added.

Serializers:

- `RawCollectionListSerializer`
- `RawCollectionDetailSerializer`
- `RawCollectionMilkRateSerializer` (for adding milk rate and copying to `Collection`).

### 7.2 List raw collections (without milk rate)

- **URL**: `raw-collections/`
- **Method**: `GET`
- **Auth**: Required
- **Behavior**:
  - Internally filters to `is_milk_rate = false`.
  - Supports filters on `collection_time`, `milk_type`, `collection_date`.
  - Search by `customer__name`.

### 7.3 Create raw collection

- **URL**: `raw-collections/`
- **Method**: `POST`

Validation:

- Numeric fields `liters`, `kg`, `fat_percentage`, `fat_kg`, `snf_percentage`, `snf_kg` must be `> 0` if provided.
- Percentages cannot exceed 100.
- `is_milk_rate` is **auto-managed**:
  - If `milk_rate` present and `> 0`, set `is_milk_rate = true` **and** immediately create a corresponding `Collection` record with copied data.
  - Else `is_milk_rate = false`.

### 7.4 Update raw collection

- **URL**: `raw-collections/{id}/`
- **Methods**: `PUT`, `PATCH`

Behavior specific to `update()`:

- If `milk_rate` is being set to `> 0` and `is_milk_rate` was previously `false`, a `Collection` is created mirroring the raw record.
- `last_edited_at` is updated to `timezone.now()`.

### 7.5 Delete raw collection

- **URL**: `raw-collections/{id}/`
- **Method**: `DELETE` (soft delete via BaseViewSet).

### 7.6 Add milk rate to an existing raw collection

- **URL**: `raw-collections/{id}/add-milk-rate/`
- **Method**: `PUT` or `PATCH`
- **Auth**: Required

**Request body (minimum)**

```json
{
  "milk_rate": 42.5,
  "amount": 1000.0,
  "fat_kg": 3.5,
  "snf_kg": 8.0,
  "solid_weight": 1.2
}
```

Validation:

- `milk_rate` must be provided and `> 0` (enforced by `RawCollectionMilkRateSerializer`).
- If already `is_milk_rate = true`, returns `400` (`"Milk rate already added"`).

Side-effects:

- Marks `is_milk_rate = true` and updates raw record fields.
- Creates a new corresponding `Collection` with copied/derived data.

**Response 200**

```json
{
  "message": "Milk rate added successfully",
  "detail": "Collection data has been copied to regular collections"
}
```

### 7.7 List raw collections that already have milk rate

- **URL**: `raw-collections/with-milk-rate/`
- **Method**: `GET`
- **Auth**: Required

Behavior:

- Filters `RawCollection` for `is_milk_rate = true` and `is_active = true` for current user.
- Applies same filters & pagination as list.
- Uses `RawCollectionMilkRateSerializer` for response.

---

## 8. Pro-Rata Reports API

**Router basename**: `pro-rata-report` → `pro-rata-reports/`

Viewset: `ProRataReportViewSet`

Uses `ProRataReportGenerator` internally to work on `Collection` records where `is_pro_rata = true`.

### 8.1 Pro-rata purchase report PDF

- **URL**: `pro-rata-reports/purchase-report-pdf/`
- **Method**: `GET`
- **Auth**: Required
- **Query params**: `start_date`, `end_date` (`DD-MM-YYYY`)

Returns purchase report PDF for **pro-rata** collections only.

### 8.2 Alias: generate_purchase_report (PDF)

- **URL**: `pro-rata-reports/generate_purchase_report/`
- **Method**: `GET`
- Same as `purchase-report-pdf` (for compatibility with non-pro-rata naming).

### 8.3 Pro-rata JSON purchase report

- **URL**: `pro-rata-reports/purchase-report/`
- **Method**: `GET`
- **Query params**:
  - `start_date`, `end_date` (`DD-MM-YYYY`) for JSON mode.
  - There may be additional query parameters for compatibility to force PDF; see implementation if needed.

Returns aggregated JSON similar to non-pro-rata purchase report but filtered to `is_pro_rata = true`.

### 8.4 Pro-rata purchase summary report (PDF)

- **URL**: `pro-rata-reports/purchase-summary-report/`
- **Method**: `GET`
- **Query params**: `start_date`, `end_date` (`DD-MM-YYYY`)

### 8.5 Pro-rata full report (PDF)

- **URL**: `pro-rata-reports/full-report/`
- **Method**: `GET`

Generates purchase report + summary + customer bills for pro-rata collections.

### 8.6 Pro-rata customer bills (PDF for all customers)

- **URL**: `pro-rata-reports/customer-bills/`
- **Method**: `GET`

### 8.7 Pro-rata customer report (selected customers)

- **URL**: `pro-rata-reports/customer-report/`
- **Method**: `GET`
- **Query params**: same as non-pro-rata `generate_customer_report` but applied to `is_pro_rata = true`.

### 8.8 Pro-rata purchase summary data (JSON)

- **URL**: `pro-rata-reports/purchase-summary-data/`
- **Method**: `GET`

Returns JSON summary data for pro-rata collections (similar structure to non-pro-rata `collections/purchase-summary-report/`).

---

## 9. YouTube Channel Link API

**Router basename**: `youtube-link` → `youtube-link/`

Viewset: `YouTubeLinkViewSet` (no auth required).

Model: `YouTubeChannelLink` with fields:

- `id`
- `link` (string URL)
- `is_active` (bool)
- `created_at`, `updated_at`

### 9.1 Get latest YouTube link

> **Public API** – `AllowAny`

- **URL**: `youtube-link/youtube-link/`
- **Method**: `GET`
- **Auth**: Not required

Behavior:

- Fetches the latest active `YouTubeChannelLink` ordered by `created_at`.

**Response 200** (if link exists)

```json
{
  "link": "https://www.youtube.com/@dudhiya-channel"
}
```

**Response 200** (if no active link)

```json
{
  "link": ""
}
```

---

## 10. Error Handling

- Validation errors (DRF or Django `ValidationError`) are normalized to:

```json
{ "error": "<message>" }
```

with HTTP `400`.

- Other unhandled exceptions in overridden methods return:

```json
{
  "error": "<exception message>",
  "detail": "<human friendly description>"
}
```

with appropriate status (`400` or `500`) depending on the view.

---

## 11. Summary of Endpoints (Relative Paths)

> Replace `<base>` with your actual app prefix, e.g. `/api/collector/`.

- **Market milk price**
  - `GET   <base>/market-milk-prices/`
  - `POST  <base>/market-milk-prices/`
  - `GET   <base>/market-milk-prices/{id}/`
  - `PUT   <base>/market-milk-prices/{id}/`
  - `PATCH <base>/market-milk-prices/{id}/`
  - `DELETE <base>/market-milk-prices/{id}/`

- **Dairy information**
  - `GET   <base>/dairy-information/`
  - `POST  <base>/dairy-information/`
  - `GET   <base>/dairy-information/{id}/`
  - `PUT   <base>/dairy-information/{id}/`
  - `PATCH <base>/dairy-information/{id}/`
  - `DELETE <base>/dairy-information/{id}/`

- **Pro-rata rate chart**
  - `GET   <base>/pro-rata-rate-chart/`
  - `POST  <base>/pro-rata-rate-chart/`
  - `GET   <base>/pro-rata-rate-chart/{id}/`
  - `PUT   <base>/pro-rata-rate-chart/{id}/`
  - `PATCH <base>/pro-rata-rate-chart/{id}/`
  - `DELETE <base>/pro-rata-rate-chart/{id}/`

- **Customers**
  - `GET   <base>/customers/`
  - `POST  <base>/customers/`
  - `GET   <base>/customers/{id}/`
  - `PUT   <base>/customers/{id}/`
  - `PATCH <base>/customers/{id}/`
  - `DELETE <base>/customers/{id}/`

- **Collections (non–pro-rata)**
  - `GET   <base>/collections/`
  - `POST  <base>/collections/`
  - `GET   <base>/collections/{id}/`
  - `PUT   <base>/collections/{id}/`
  - `PATCH <base>/collections/{id}/`
  - `DELETE <base>/collections/{id}/`
  - `GET   <base>/collections/purchase-report/`
  - `GET   <base>/collections/generate_purchase_report/`
  - `GET   <base>/collections/generate_purchase_summary_report/`
  - `GET   <base>/collections/generate_full_report/`
  - `GET   <base>/collections/generate_full_customer_report/`
  - `GET   <base>/collections/generate_customer_report/`
  - `GET   <base>/collections/purchase-summary-report/`

- **Raw collections**
  - `GET   <base>/raw-collections/`
  - `POST  <base>/raw-collections/`
  - `GET   <base>/raw-collections/{id}/`
  - `PUT   <base>/raw-collections/{id}/`
  - `PATCH <base>/raw-collections/{id}/`
  - `DELETE <base>/raw-collections/{id}/`
  - `PUT   <base>/raw-collections/{id}/add-milk-rate/`
  - `PATCH <base>/raw-collections/{id}/add-milk-rate/`
  - `GET   <base>/raw-collections/with-milk-rate/`

- **Pro-rata reports (`pro-rata-reports/`)**
  - `GET <base>/pro-rata-reports/purchase-report-pdf/`
  - `GET <base>/pro-rata-reports/generate_purchase_report/`
  - `GET <base>/pro-rata-reports/purchase-report/`
  - `GET <base>/pro-rata-reports/purchase-summary-report/`
  - `GET <base>/pro-rata-reports/full-report/`
  - `GET <base>/pro-rata-reports/customer-bills/`
  - `GET <base>/pro-rata-reports/customer-report/`
  - `GET <base>/pro-rata-reports/purchase-summary-data/`

- **YouTube link (public)**
  - `GET <base>/youtube-link/youtube-link/`
