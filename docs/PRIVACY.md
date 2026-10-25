# Privacy

Daily Spend handles financial information, so it collects as little as possible and keeps it on the phone by default.

## Local data (always)

| Data | Where | Who can read it |
|---|---|---|
| Expenses, categories, budget, settings | `daily_spend.db` in app-private storage | Only the app (Android sandbox). `allowBackup` is off, so it is not copied by Android cloud backup |
| Detected payments waiting to be imported | `daily_spend_inbox.db` in app-private storage | Only the app. Rows are deleted once imported |
| Repost-detection hashes | same inbox DB, `seen` table | One-way SHA-256 hashes, kept for 24 hours |
| Tracking settings and counters | SharedPreferences (app-private) | Only the app |
| Sync sign-in token (only if sync is used) | `expo-secure-store` (Android Keystore-backed) | Only the app |

## Notification access (optional, off by default)

- The user must turn it on in Daily Spend **and** grant Notification Access in Android Settings. The app explains what happens before it opens Android Settings.
- The service ignores every notification whose package is not in the user's allowlist **before reading its content**.
- For allowed apps, title and text are held **in memory only** while parsing. Kept fields: amount, payee name, transaction reference, posting time, parser id, confidence. The text itself is never written to disk, logs, or the network.
- Ignored entirely: OTP / password / "do not share" messages, chats, payment requests and reminders, offers and cashback promotions, failed / declined / cancelled payments, money received, refunds.
- Logs contain reason codes only (e.g. `Ignored notification: FAILED`), and only when debug logging is enabled for the tag.
- The app does **not** use an Accessibility Service, does **not** read SMS, and does not try to bypass Android's permission flow.
- Turning tracking off in the app stops recording immediately; revoking access in Android Settings stops delivery entirely.

## Cloud sync (optional, off by default)

Only when the user signs in to a server they choose:

- Sent: transactions (amount, category, payee, note, method, time, status, source, source package, reference), categories, monthly budget.
- Never sent: notification text (it does not exist anywhere to send), the inbox, repost hashes.
- Passwords are hashed with Argon2id on the server. Tokens are JWTs that expire (30 days by default).
- Server logs record method, path, status and timing only — no bodies, query strings, headers or financial values.
- Every row is stored under the authenticated user's id; one user cannot read or change another's data (covered by `backend/tests/test_isolation.py`).

**Local vs synced:** without sync, deleting the app or using "Delete all local data" removes everything. With sync, a copy also exists on the server until the account's data is deleted there. Account deletion is not implemented yet and must be done by the server operator.

## User control

- Export CSV / full JSON backup (Settings → Your data). CSV cells are neutralised against spreadsheet formula injection.
- Delete all local data (two confirmations). It also clears the native inbox, turns tracking off and signs out of sync.
- Edit or delete any transaction; confirm or exclude anything detected automatically.

## Before publishing

- Write a public privacy policy based on this document.
- Complete the Google Play Data safety form (financial info, collected only when sync is used).
- Review Google Play's policy on notification listener / sensitive permissions and provide the prominent in-app disclosure (already shown on the Automatic tracking screen).
