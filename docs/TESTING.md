# Testing

## How to run

| Suite | Command | Needs |
|---|---|---|
| Mobile unit/integration (Jest) | `cd mobile && npm test` | Node 22.5+ (uses built-in `node:sqlite`) |
| Mobile typecheck / lint | `npm run typecheck` / `npm run lint` | |
| Expo config health | `npx expo-doctor` | |
| Kotlin parser tests | `cd mobile && npx expo prebuild -p android && cd android && ./gradlew :upi-notifications:testDebugUnitTest` | JDK 17+, Android SDK |
| Android build | `cd mobile/android && ./gradlew assembleRelease` | |
| Backend (pytest) | `cd backend && pytest` | Python 3.11+ |
| Backend on PostgreSQL | `TEST_DATABASE_URL=postgresql+psycopg://daily_spend_app:<pw>@localhost:5432/daily_spend_test pytest` | an **empty** throwaway database (it is migrated up and down) |
| Backend lint | `ruff check .` | |

## What is covered

### Mobile — Jest (`mobile/tests`)

- `money.test.ts` — paise parsing (Indian grouping, ₹/Rs/INR, rejects 0/negative/3-decimals), formatting `₹1,23,456.75`, no float drift, integer percentages.
- `time.test.ts` — IST day boundaries independent of device TZ (00:15 IST belongs to the new day), Monday weeks, month/leap-year boundaries, relative day labels.
- `insights.test.ts` — what counts as spending (pending/excluded/deleted/income/transfers excluded; per-category override), today/week/month totals, category aggregation, budget remaining/over, projection only after day 5, previous-month comparison over the same elapsed days, "not enough history".
- `categorize-dedupe.test.ts` — keyword rules at word starts (no "Ola" in "Coca Cola"), user rules win, P2P → Transfers, exact (reference) vs possible (amount+time+payee) duplicates, different references never collide.
- `repository.test.ts` — **real SQLite**: migrations + seeds, add/edit/delete manual expense with totals updating, validation at repository and CHECK-constraint level, soft-delete tombstones, duplicate-link release, categories, settings/budget, CSV (formula-injection safe) + JSON export, clear-all. Runs with no network = offline behaviour.
- `notificationImport.test.ts` — confirmed vs pending review (uncertain status / low confidence), exact duplicate by reference, manual entry + notification → possible duplicate for review, P2P to Transfers, learned merchant rules, malformed items dropped, **durable handoff**: ack only after save and idempotent re-drain after a crash.
- `sync.test.ts` — change collection since last push, last-writer-wins both directions, tombstones, dangling category ids.
- `TransactionRow.test.tsx` — React Native Testing Library: INR formatting, relative time, pending/not-counted badges, press handler.

### Kotlin — JUnit (`modules/upi-notifications/android/src/test`)

- `FixtureParserTest` runs every case in `modules/upi-notifications/fixtures/notifications.json` (25 synthetic cases): successful merchant/P2P payments, Indian number formats, bank-style "debited", PhonePe multi-line big text, Paytm "Paid Successfully to", pending → uncertain, ambiguous wording, two amounts, failed/declined/cancelled, incoming/credited/refund, collect requests, OTP, promotions, missing amount, malformed amount, unrelated chat, empty, group summaries, missing payee → below auto-confirm threshold.
- `TextRulesTest` — exact paise conversion, references require digits.
- `NotificationProcessorTest` — tracking off, package allowlist, repost suppression window.

The fixtures are **synthetic**. Passing them does not prove that real Google Pay / PhonePe / Paytm notifications parse correctly — see `ANDROID_NOTIFICATION_SETUP.md` §5.

### Backend — pytest (`backend/tests`)

Database created per test by running the Alembic migration.

- `test_auth.py` — register/login, duplicate email, weak input, identical errors for unknown user vs wrong password, missing/garbage/tampered/expired tokens.
- `test_transactions.py` — CRUD, client ids, validation (amount ≤ 0, fractional, enum values, null on PATCH, unknown fields), pagination and filters, budgets.
- `test_isolation.py` — users cannot list/patch/delete each other's rows, `user_id` in body ignored, same client id per user is separate, sync cannot overwrite or read other users' rows, insights/budget isolation.
- `test_sync_insights.py` — two devices converge, LWW and stale/tie handling, tombstones, categories/budget sync, sync validation, IST boundaries, summary excludes pending/excluded/transfers/income, same-period comparison, JS-compatible rounding.

## Results

Verified on 2026-10-25 (Windows 11, Node 24.21, JDK 21, Python 3.12.10, Expo SDK 58 / RN 0.88):

| Check | Result |
|---|---|
| `npx tsc --noEmit` | pass |
| `npx expo lint` | pass (0 problems) |
| `npx expo-doctor` | 20/20 checks passed |
| Jest | 8 suites, 77 tests passed |
| Kotlin unit tests | 3 classes, 6 tests passed (fixture test covers all 25 fixtures) |
| Backend pytest (SQLite) | 23 passed |
| Backend pytest (PostgreSQL 18.6, local `daily_spend_test`) | 23 passed |
| Backend `ruff check` | pass |
| Kotlin module compile (`:upi-notifications`, via unit-test task) | pass |
| Full app APK build on this Windows machine | **blocked** — see below |

**Blocker — full APK build on Windows:** `:app:buildCMakeRelWithDebInfo` fails with `ninja: error: … Filename longer than 260 characters`. React Native's autolinked codegen for `react-native-gesture-handler` produces an object path whose *suffix alone* is 277 characters, and the SDK's CMake 3.22.1 ships ninja 1.10.2, which is not long-path aware; `LongPathsEnabled` is 0 on this machine. Fix one of:

1. Enable Windows long paths (admin PowerShell: `New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force`, then reboot) **and** install a newer CMake (which bundles ninja ≥ 1.12) via Android Studio › SDK Manager › SDK Tools › CMake;
2. build in WSL2, Linux or macOS; or
3. build in the cloud with `npx eas-cli@latest build -p android --profile preview`.

(Mapping the project to a short drive letter with `subst` does not work: autolinking resolves real paths and Gradle then fails with "different roots".)

Consequently **not yet verified**: app launch on the phone, on-device notification capture, real payment-app notification wording, OEMs other than the Samsung test phone.

## Manual test script (physical phone)

1. Fresh install → Today shows ₹0, empty state, "Auto-tracking off". No permission prompts on launch.
2. Airplane mode on → Add expense: type `120`, keep category, Save. Today = ₹120, month = ₹120. (Offline works.)
3. Add another with Yesterday selected → Today unchanged, month increases.
4. Tap the expense → edit amount → Save → totals update; Delete → totals drop.
5. Settings → Monthly budget ₹3000 → Today shows remaining and progress.
6. Insights → numbers match; comparison says "Not enough history".
7. Automatic tracking flow and `adb` notification tests: `ANDROID_NOTIFICATION_SETUP.md` §2 and §4.
8. Settings → Export CSV → open in a spreadsheet; Delete all local data → everything resets.
