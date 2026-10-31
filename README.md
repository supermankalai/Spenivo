# MyExpenses

**Know Where Your Money Goes.** A simple, private expense tracker for India (project codename: Daily Spend). Record an expense in a few seconds, see what you spent today and this month, and — on Android, if you allow it — have payments recorded automatically from your bank's SMS debit alerts (any UPI app, card, ATM or NEFT).

- **Local-first:** all data lives in SQLite on the phone. No account, no internet needed.
- **Automatic tracking (optional, Android):** a native `NotificationListenerService` reads the notifications of your SMS app, uses only bank debit alerts, keeps amount / payee / reference / method / time, and discards the text. No SMS permission is used.
- **Safe by default:** failed, incoming, ambiguous and possibly duplicate payments are never counted silently — uncertain ones wait in a review queue.
- **Daily and monthly budgets with alerts:** notifications at 50%, 80% and 90%, one sound alert at 100%, and a red over-budget state that asks for (and stores) the reason. Alerts also fire for bank-SMS payments recorded while the app is closed.
- **Reminders:** morning "how much will you spend today?" (sets today's budget), evening cash-expense check, and a 1st-of-month budget prompt. All configurable in Settings › Notifications & reminders.
- **Optional sync:** a FastAPI + PostgreSQL backend for backup across devices, off unless you sign in.

| | |
|---|---|
| Currency | INR, stored as integer paise |
| Timezone | Asia/Kolkata for all day/week/month boundaries |
| Platform | Android (iOS would need a different import strategy) |

## Repository layout

```
mobile/                      Expo SDK 58 app (React Native 0.88, TypeScript, Expo Router)
  src/app/                   Screens (file-based routes): Today, Insights, Settings + Add/Edit, Review, …
  src/domain/                Pure logic: money, IST dates, insights, categorisation, duplicate detection
  src/database/              SQLite schema/migrations and repositories
  src/services/              Notification import (inbox drain), tracking bridge, cloud sync client
  modules/upi-notifications/ Local Expo native module (Kotlin): listener service, parsers, durable inbox
    fixtures/                Synthetic notification fixtures shared by the Kotlin tests
  tests/                     Jest tests (domain, real-SQLite repository tests, import pipeline, UI)
backend/                     FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL (optional sync)
docs/                        Architecture, privacy, Android setup, testing, API
```

## Quick start (mobile)

Requirements: Node 20+ (tested with 24), JDK 17+ (tested with 21), Android SDK (platform 36/37), a physical Android phone with USB debugging.

```bash
cd mobile
npm install
npx expo run:android          # builds a development build and installs it on the connected phone
```

**Expo Go cannot run this app's automatic tracking**: the notification listener is custom native code. Use `npx expo run:android` (local development build) or EAS Build. Without the native module (Expo Go, web), the app still works with manual entry and shows "Auto-tracking unavailable".

Standalone APK without a dev server:

```bash
cd mobile
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease   # app/build/outputs/apk/release/app-release.apk
adb install -r app/build/outputs/apk/release/app-release.apk
```

**Windows:** native builds currently fail with "Filename longer than 260 characters" unless Windows long paths are enabled and a newer SDK CMake is installed — see [docs/TESTING.md](docs/TESTING.md#results). WSL2 / Linux / macOS / EAS Build avoid this.

The release build is signed with the debug keystore from the Expo template. **Create your own upload key before distributing** (see `docs/ANDROID_NOTIFICATION_SETUP.md` → Release checklist).

Testing automatic tracking on a real phone: see [docs/ANDROID_NOTIFICATION_SETUP.md](docs/ANDROID_NOTIFICATION_SETUP.md).

## Quick start (backend, optional)

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows; use bin/activate elsewhere
pip install -r requirements-dev.txt
# Create role daily_spend_app, databases daily_spend + daily_spend_test, schema daily_spend:
psql -h localhost -U postgres -v app_password='<strong password>' -f sql/setup_database.sql
cp .env.example .env                                  # set DATABASE_URL (daily_spend_app) and a random JWT_SECRET
alembic upgrade head                                  # creates the tables inside schema daily_spend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API docs at `http://localhost:8000/docs` (disabled when `ENVIRONMENT=production`). See [docs/API.md](docs/API.md).

The account server address is set at build time with `EXPO_PUBLIC_API_URL` in `mobile/.env` (copy `mobile/.env.example`; restart Metro after changing it) and is never shown in the app. Users sign in with Google (optional) — during the first-run steps or later in Settings › Account & backup. That needs `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` in `mobile/.env` and `GOOGLE_CLIENT_IDS` on the server (see `docs/API.md`). For a phone on USB, `adb reverse tcp:8000 tcp:8000` makes `http://localhost:8000` reach the PC; release builds need an `https://` URL.

## Checks

```bash
cd mobile
npm run typecheck && npm run lint && npm test
cd android && ./gradlew :upi-notifications:testDebugUnitTest    # Kotlin parser tests (after prebuild)

cd backend
pytest && ruff check .
```

See [docs/TESTING.md](docs/TESTING.md) for what each suite covers and the latest verified results.

## Known limitations

- **Not a bank ledger.** Notification parsing misses payments (apps that don't notify, notifications dismissed/blocked, OEM battery killers) and can misread details. Check your bank/UPI app for authoritative records.
- **Parsers are rule-based and tested only against synthetic fixtures** modelled on common HDFC / SBI / ICICI / Axis / Kotak alert formats. Real bank wording varies and changes; add redacted real samples to `modules/upi-notifications/fixtures/notifications.json` and adjust rules.
- **Watched apps** default to the phone's default SMS app plus Google Messages / Samsung Messages / AOSP Messages. If SMS notifications are muted or hidden, alerts cannot be read. UPI-app notifications are not watched by default (a package can still be added manually).
- English notifications only; amounts must be shown with ₹ / Rs / INR.
- Bank **SMS** are not read (no SMS permission by design).
- Date picker uses the device timezone; totals always use IST. Users outside IST may see picked times shifted.
- Sync uses last-writer-wins on device clocks; badly wrong clocks can lose an edit. No sync conflict UI, no rate limiting on the backend. Backup runs a few seconds after each change while the app is open (and via "Back up now"), not in the background.
- Transfers are excluded from spending by default; the rule is per category (Settings → Manage categories).
- Google Play: apps using `NotificationListenerService` for this purpose may need a declaration and a prominent disclosure. Review current Play policy before publishing.
