# Architecture

## Overview

```
┌──────────────────────────── Android phone ────────────────────────────┐
│                                                                        │
│  Payment app notification                                              │
│        │ (only after user grants Notification Access)                  │
│        ▼                                                               │
│  UpiNotificationListenerService (Kotlin)                               │
│   1. tracking enabled?  package in allowlist?  (else return, unread)   │
│   2. NotificationProcessor → ParserRegistry → Generic/PhonePe/… parser │
│   3. repost suppression (SHA-256 of content, 2 min window)             │
│   4. InboxStore.insert(parsed fields only)  ── raw text discarded      │
│        │                                                               │
│        ▼ daily_spend_inbox.db (app-private SQLite, durable queue)      │
│        │                                                               │
│  ┌─────┴──────── React Native (may not be running) ────────────────┐  │
│  │ On app start, resume, or live "onInboxChanged" event:            │  │
│  │   drainInbox(): read → importInboxItems() → acknowledge           │  │
│  │     • idempotent via transactions.import_key (UNIQUE)             │  │
│  │     • duplicate check (reference / fingerprint)                   │  │
│  │     • confirmed vs pending_review                                  │  │
│  │     • categorise (user rules → built-in keywords → P2P→Transfers)  │  │
│  │        ▼                                                            │  │
│  │   daily_spend.db (expo-sqlite) ── source of truth for the UI       │  │
│  │        ▼                                                            │  │
│  │   Today / Insights / Review screens (useDbQuery + version bump)    │  │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                  │ optional, user-initiated               │
└──────────────────────────────────┼────────────────────────────────────────┘
                                   ▼
                     FastAPI /api/v1/sync  →  PostgreSQL
```

## Why a native inbox instead of a JS listener

A JavaScript event listener only works while the React Native runtime is alive. Android can deliver notifications while the app process exists only for the service. So the service **never depends on JS**: it writes to its own small SQLite database (`InboxStore`). The app drains it later. The handoff is:

1. JS reads pending items (`getPendingInboxItems`).
2. JS inserts them into the main database. Each row carries `import_key = inbox id` (UNIQUE), so re-imports are no-ops.
3. Only then does JS call `acknowledgeInboxItems(ids)`, which deletes them natively.

If the app dies between 2 and 3, the next drain re-reads the same items and step 2 skips them (tested in `tests/notificationImport.test.ts`). The `onInboxChanged` event is a best-effort shortcut for when the app is in the foreground.

## Mobile layers

| Layer | Path | Notes |
|---|---|---|
| Routes/screens | `mobile/src/app` | Expo Router. Tabs: Today, Insights, Settings. Stack: expense (add/edit, modal), review, transactions, budget, categories, tracking, privacy, sync |
| State | `src/state/DataContext.tsx` | Provides the DB, a `version` counter bumped on every write, and `now`. `useDbQuery` re-runs queries on version change and screen focus. No global store needed |
| Domain (pure) | `src/domain` | `money.ts` (paise; parse/format with Indian grouping), `time.ts` (IST without relying on device TZ), `insights.ts`, `categorize.ts`, `dedupe.ts` |
| Database | `src/database` | `DbClient` interface (expo-sqlite on device, `node:sqlite` in tests), `PRAGMA user_version` migrations, repositories |
| Services | `src/services` | `notificationImport.ts` (pure import pipeline), `tracking.ts` (native bridge, null-safe), `sync.ts` |

### Data model (SQLite)

`transactions`: `id` (UUID), `amount_minor_units` (INTEGER > 0, paise), `currency` ('INR'), `transaction_type` (expense/income), `category_id`, `merchant`, `description`, `payment_method` (UPI/cash/debit_card/credit_card/bank_transfer/other), `transaction_datetime` (epoch ms), `source` (manual/notification/import), `source_package`, `external_reference`, `status` (confirmed/pending_review/excluded), `confidence`, `is_user_confirmed`, `import_key` (UNIQUE), `duplicate_of`, `review_reason`, `created_at`, `updated_at`, `deleted_at` (soft-delete tombstone for sync).

Indexes: `transaction_datetime`, `(status, transaction_datetime)`, `external_reference`, `category_id`, `updated_at`.

`categories` (with `counts_as_spending`, archived instead of deleted), `settings` (key/JSON value), `merchant_rules` (learned "payee → category").

### What counts as spending

`status = 'confirmed' AND transaction_type = 'expense' AND deleted_at IS NULL AND category.counts_as_spending`. Transfers is seeded with `counts_as_spending = 0`, so payments to people are not treated as consumption unless the user changes it.

### Duplicate handling

| Situation | Result |
|---|---|
| Same inbox item imported twice | skipped (`import_key`) |
| Same UPI reference already stored | skipped as exact duplicate |
| Different references | always distinct |
| Same amount, within ±10 min, compatible payee (or a payee missing) | imported as **pending_review** with `duplicate_of`, the user decides |
| Identical notification content re-posted within 2 min (native) | ignored as a repost |

### Confirmed vs pending review

Native parser output → JS decision:

- failed / declined / cancelled / incoming / requests / OTP / promotional / no amount → **dropped natively**, never stored
- explicit success wording + amount + (payee or reference), single amount → confidence ≥ 0.85 → **confirmed**
- pending/processing wording, no explicit success, several amounts, or missing payee and reference → **pending_review**

## Native module (`modules/upi-notifications`)

- `parsing/` — pure Kotlin (no Android imports), so it is JVM-unit-testable: `TextRules`, `GenericUpiParser` and app subclasses, `ParserRegistry`, `NotificationProcessor`.
- `UpiNotificationListenerService` — filters by allowlist **before** reading extras, parses on a single background thread, never logs content.
- `TrackingConfig` — SharedPreferences: enabled flag (default **off**), allowlist, counters.
- `InboxStore` — `SQLiteOpenHelper` queue plus `seen` hash table (24 h retention).
- `UpiNotificationsModule` — Expo Modules API bridge: access status, open settings, toggle, allowlist, inbox read/ack, events.

## Backend

FastAPI app (`backend/app`): `core/` (settings from env, JWT, Argon2 hashing, JSON logging), `models/` (SQLAlchemy 2), `schemas.py` (Pydantic validation), `services/` (IST insights mirroring the TS logic; sync merge), `api/` (routes, `get_current_user` dependency).

- Rows use composite primary keys `(user_id, id)` — a user can never address another user's row, even with a guessed id.
- User identity comes only from the bearer token; bodies cannot set `user_id` (unknown fields are ignored or rejected).
- Sync: client pushes rows changed since its last push; server applies last-writer-wins on client `updated_at` (ties keep server), stamps each accepted change with a per-user monotonic `server_version`, and returns everything with `server_version > cursor`. A row lock on the user serialises concurrent syncs on PostgreSQL.
- Alembic migration `0001_initial` defines the schema; tests build their database by running it.

## Not implemented / deliberately out of scope

Background/periodic sync, push notifications, password reset, rate limiting, multi-currency, iOS import, SMS parsing, accessibility-service scraping (deliberately avoided).
