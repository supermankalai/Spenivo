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
- The service ignores every notification whose package is not in the watch list (by default only SMS apps) **before reading its content**. From SMS apps, only messages that look like bank debit alerts are used; personal chats are dropped without being stored. No SMS permission is requested, so the app cannot read the SMS inbox.
- For allowed apps, title and text are held **in memory only** while parsing. Kept fields: amount, payee name, transaction reference, posting time, parser id, confidence. The text itself is never written to disk, logs, or the network.
- Ignored entirely: OTP / password / "do not share" messages, chats, payment requests and reminders, offers and cashback promotions, failed / declined / cancelled payments, money received, refunds.
- Logs contain reason codes only (e.g. `Ignored notification: FAILED`), and only when debug logging is enabled for the tag.
- The app does **not** use an Accessibility Service, does **not** request the SMS permission (it only sees SMS that the SMS app shows as notifications, and cannot read the inbox or past messages), and does not try to bypass Android's permission flow.
- Turning tracking off in the app stops recording immediately; revoking access in Android Settings stops delivery entirely.

## Account & backup (optional, Google sign-in)

Only when the user signs in with Google:

- The server receives the Google account id (`sub`), name and email from a verified Google ID token. No password exists.
- Backed up automatically a few seconds after changes: transactions (amount, category, payee, note, method, time, status, source, source package, reference), categories, monthly and daily budgets, per-day budgets, over-budget reasons.
- Never sent: notification text (it does not exist anywhere to send), the inbox, repost hashes.
- Session tokens are the server's own JWTs (30 days by default), kept in Keystore-backed secure storage on the phone.
- Server logs record method, path, status and timing only — no bodies, query strings, headers or financial values.
- Every row is stored under the authenticated user's id; one user cannot read or change another's data (covered by `backend/tests/test_isolation.py`).

**Local vs synced:** without sync, deleting the app or using "Delete all local data" removes everything. With an account, a copy also exists on the server until the user deletes the account (Settings › Account & backup › Delete account and backup, `DELETE /api/v1/auth/me`), which removes every synced row.

## App lock

Optional. Uses Android's biometric prompt (fingerprint/face, falling back to the screen-lock PIN/pattern). The app only learns pass/fail. It re-locks after the app has been in the background for more than 30 seconds.

## Pro subscription (optional)

- Google Play handles the payment; the app never sees card, UPI or bank details.
- The app only asks Google Play whether this Google account has an active Pro subscription, and keeps that yes/no on the phone.
- Nothing about the subscription is sent to the MyExpenses server.

## User control

- Export CSV / full JSON backup (Settings → Your data). CSV cells are neutralised against spreadsheet formula injection.
- Delete all local data (two confirmations). It also clears the native inbox, turns tracking off and signs out of sync.
- Edit or delete any transaction; confirm or exclude anything detected automatically.

## Before publishing

- Write a public privacy policy based on this document.
- Complete the Google Play Data safety form (financial info, collected only when sync is used).
- Review Google Play's policy on notification listener / sensitive permissions and provide the prominent in-app disclosure (already shown on the Automatic tracking screen).
