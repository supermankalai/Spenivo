# Backend API (v1)

Base path `/api/v1`. JSON only. Amounts are integer paise; timestamps are epoch milliseconds (UTC). Authenticated routes need `Authorization: Bearer <token>`. Interactive docs: `/docs` (non-production only).

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register` | – | `{email, password(≥10)}` → `201 {id, email}`; `409` if taken |
| POST | `/auth/login` | – | `{email, password}` → `{access_token, token_type}`; `401` on any failure |
| GET | `/transactions` | ✓ | `?limit=1..200&offset&start&end&status` → `{items, total, limit, offset}`, newest first, excludes deleted |
| POST | `/transactions` | ✓ | Create; optional client `id`; `409` if the id exists for this user |
| PATCH | `/transactions/{id}` | ✓ | Partial update (unknown fields → `422`); `404` if not yours/deleted |
| DELETE | `/transactions/{id}` | ✓ | Soft delete (tombstone, propagates via sync) → `204` |
| GET | `/insights/summary` | ✓ | `?now=` optional; today/week/month, daily average, budget remaining, previous-month comparison (IST) |
| GET | `/insights/categories` | ✓ | `?now=` optional; category totals for that IST month |
| GET | `/budgets` | ✓ | `{monthly_budget_minor, updated_at}` |
| PUT | `/budgets` | ✓ | `{monthly_budget_minor: int > 0 \| null}` |
| POST | `/sync` | ✓ | Push/pull, see below |
| GET | `/healthz` | – | Liveness |

## Transaction fields

`amount_minor_units` (1..1,000,000,000), `currency` ("INR"), `transaction_type` (expense\|income), `category_id`, `merchant` (≤120), `description` (≤500), `payment_method` (UPI\|cash\|debit_card\|credit_card\|bank_transfer\|other), `transaction_datetime`, `source` (manual\|notification\|import), `source_package`, `external_reference`, `status` (confirmed\|pending_review\|excluded), `confidence` (0..1), `is_user_confirmed`, plus server-managed `id`, `created_at`, `updated_at`, `deleted_at`.

## Sync protocol

Request:

```json
{
  "cursor": 41,
  "transactions": [ { "id": "…", "...": "all fields", "updated_at": 1741766400000, "deleted_at": null } ],
  "categories":   [ { "id": "food", "name": "Food", "icon": "…", "color": "#E8833A", "counts_as_spending": true, "is_archived": false, "sort_order": 0, "updated_at": 1 } ],
  "budget": { "monthly_budget_minor": 3000000, "updated_at": 1741766400000 }
}
```

Server behaviour:

1. Locks the user row (serialises concurrent syncs).
2. For each pushed row: apply if new, or if `updated_at` is **strictly newer** than the stored row (ties keep the server copy). Each accepted change gets the next per-user `server_version`.
3. Returns all rows with `server_version > cursor` (including just-accepted ones) and the new `cursor`.

The client skips echoed rows, applies newer rows locally with the same rule, and stores the cursor. At most `SYNC_MAX_BATCH` (2000) rows per list per request (`413` above that).

## Errors

`401` unauthenticated, `404` not found (also for other users' ids), `409` conflict, `413` batch too large, `422` validation. Bodies: `{"detail": …}`. Every response carries `x-request-id`.

## Configuration

Environment variables (see `backend/.env.example`): `DATABASE_URL`, `JWT_SECRET` (required, ≥32 chars, app refuses to start otherwise), `ACCESS_TOKEN_MINUTES`, `ENVIRONMENT`, `LOG_LEVEL`, `CORS_ORIGINS`, `SYNC_MAX_BATCH`.

## Not implemented

Password reset, email verification, account deletion endpoint, rate limiting / lockout, refresh tokens, pagination cursors for very large histories.
