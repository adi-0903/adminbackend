# Collector API Documentation

Base URL: /api/collector/
Authentication: Bearer token (DRF IsAuthenticated on all endpoints)
Date format: DD-MM-YYYY unless stated otherwise

- Collection model key fields: see `collector/models.py:Collection`
- Pro-rata flag used across reports: `is_pro_rata` (True for pro-rata collections)

## Collections
Route: /api/collector/collections/

- GET /
  - List collections for the authenticated user.
  - Query params (filters):
    - collection_time: morning | evening
    - milk_type: cow | buffalo | cow_buffalo
    - collection_date: YYYY-MM-DD (exact)
    - search: customer name (icontains)
    - ordering: collection_date, created_at, liters, kg, fat_percentage, fat_kg, snf_percentage, snf_kg, rate, amount
  - Pagination: page, page_size
  - Note: Report endpoints below handle date ranges and formatting.

- POST /
  - Create a collection.
  - Validates edit constraints and wallet balance per kg fee (see settings COLLECTION_FEE) before create.
  - Body: Collection fields (see serializer in `collector/serializers.py`).

- GET /{id}/
- PUT/PATCH /{id}/
  - Update is limited by edit policy in settings COLLECTION_EDIT (MAX_EDIT_DAYS, MAX_EDIT_COUNT).

- DELETE /{id}/
  - Soft deletes the collection.

## Customers
Route: /api/collector/customers/

- GET /
  - List active customers.
  - Query params:
    - search: name or phone (icontains)
  - If total_count > 40, page size increases to 100 automatically.

- POST /, GET /{id}/, PUT/PATCH /{id}/, DELETE /{id}/

## Market Milk Prices
Route: /api/collector/market-milk-prices/

- GET /
  - Returns only the most recent active price for the user.

- POST /
  - Creates a new active price and soft-deactivates previous.

- PUT/PATCH /{id}/, DELETE /{id}/

## Dairy Information
Route: /api/collector/dairy-information/

- GET /
  - Returns only the most recent active dairy info for the user.

- POST /
  - Creates a new active dairy info and soft-deactivates previous.

- PUT/PATCH /{id}/, DELETE /{id}/

## Raw Collections
Route: /api/collector/raw-collections/

- Standard CRUD for raw milk entries (without rate calculations).
- Filters: collection_time, milk_type, collection_date

## Normal Report Endpoints (non pro-rata)
All these endpoints EXCLUDE pro-rata collections (is_pro_rata=True) from results.

- GET /api/collector/collections/purchase-report/
  - JSON grouped by date with totals.

- GET /api/collector/collections/generate_purchase_report/?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - Generates PDF purchase report by date.

- GET /api/collector/collections/generate_purchase_summary_report/?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - Generates PDF milk purchase summary by customer.

- GET /api/collector/collections/generate_full_report/?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - Generates combined PDF: purchase report + summary + per-customer bills.

- GET /api/collector/collections/generate_full_customer_report/?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - Generates PDF with milk bills for all customers in range.

- GET /api/collector/collections/generate_customer_report/?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY&customer_ids=1,2,3
  - Generates PDF with bills for specified customers.

- GET /api/collector/collections/purchase-summary-report/?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - JSON purchase summary (by customer) for date range.

## Pro-Rata Report Endpoints
Base Route: /api/collector/pro-rata-reports/
These endpoints ONLY include pro-rata collections (is_pro_rata=True).

### JSON Data Endpoints
- GET /purchase-report/
  - JSON purchase report data grouped by date for pro-rata collections only.
  - Pagination: page, page_size
  - Returns: collection_date, total_weight, total_fat_percentage, total_snf_percentage, total_fat_kg, total_snf_kg, total_amount

- GET /purchase-summary-data?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - JSON summary data (by customer) for pro-rata collections only.
  - Returns: summary_data array and grand_totals object

### PDF Generation Endpoints
- GET /purchase-report-pdf?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - PDF purchase report (by date) for pro-rata only.

- GET /purchase-summary-report?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - PDF milk purchase summary (by customer) for pro-rata only.

- GET /full-report?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - Combined PDF: purchase report + summary + per-customer bills (pro-rata only).

- GET /customer-bills?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY
  - PDF bills for all customers (pro-rata only).

- GET /customer-report?start_date=DD-MM-YYYY&end_date=DD-MM-YYYY&customer_ids=1,2,3
  - PDF for specific customers (pro-rata only).

## Common Query Parameters
- start_date: DD-MM-YYYY
- end_date: DD-MM-YYYY
- customer_ids: Comma-separated list of integer IDs (for specific customer reports)

## Notes
- Date in list filters for collections is YYYY-MM-DD (exact match), while report endpoints use DD-MM-YYYY per implementation in `collector/views.py` and `collector/pro_rata_report_generation_views.py`.
- All responses require authentication.
