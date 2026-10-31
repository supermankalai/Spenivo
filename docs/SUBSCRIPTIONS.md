# Free and Pro

MyExpenses has two plans. Pro is paid by **UPI** and confirmed by hand. There's no Google Play Billing, so the app is shared as an APK rather than through the Play Store: Play requires its own billing for subscriptions.

## What each plan gets

| | Free | Pro |
|---|---|---|
| Auto-tracking of UPI payments, manual expenses, income | ✓ | ✓ |
| Daily & monthly budgets, alerts, over-budget notes | ✓ | ✓ |
| Insights, home-screen widget, dark mode, app lock | ✓ | ✓ |
| Backup & sync, CSV/JSON export | ✓ | ✓ |
| EMI & bill reminders | 3 | Unlimited |
| Reminders on the due day | Once | Up to 3×, at chosen times |
| Category budgets | 1 | Unlimited |
| Receipt photos | — | ✓ |
| Split with friends / Who owes you | — | ✓ |
| Monthly reports | This month & last month | All months |

The limits live in `mobile/src/domain/plan.ts` (`FREE_LIMITS`).

**Going back to Free never deletes data.** Everything already created keeps working:
- Reminders keep firing.
- Budgets keep alerting.
- Receipts can still be viewed.
- Splits can still be edited and settled.

The only thing that changes is that you can't add more past the Free limits.

## Prices

| Plan | Price | Length |
|---|---|---|
| Monthly | ₹49 | 30 days |
| Yearly | ₹399 | 365 days |

Prices are set on the server (`PRO_PRICE_MONTHLY_MINOR`, `PRO_PRICE_YEARLY_MINOR` in paise), and the app shows whatever the server returns. Change them in `.env`, then restart the API.

Pro doesn't auto-renew. Renewing early adds to the time left.

## How a purchase works

**In the app:**
1. The user signs in with Google. Pro belongs to the account, so it survives a reinstall or a new phone.
2. They pick a plan. The server creates a reference code, e.g. `MX-7K3P9`.
3. **Open UPI app** launches their UPI app with your UPI ID, the amount and the code filled in. They can also copy the UPI ID and code and pay from another phone.
4. They enter the **12-digit UTR** (UPI reference) shown in their UPI app and tap **I've paid**.

**On the server:** you check your bank or UPI app for that UTR and amount, then approve:
```bash
cd /opt/spenivo/backend
sudo -u myexpenses .venv/bin/python -m app.admin pending           # who's waiting
sudo -u myexpenses .venv/bin/python -m app.admin approve MX-7K3P9   # turn Pro on
sudo -u myexpenses .venv/bin/python -m app.admin reject MX-7K3P9    # money not received
sudo -u myexpenses .venv/bin/python -m app.admin grant friend@gmail.com 30   # free Pro
sudo -u myexpenses .venv/bin/python -m app.admin users              # everyone with Pro
```

The app picks up the change by itself the next time it's opened. Pulling down on the Pro screen also checks.

**Safety checks:**
- A UTR can only be used once.
- One account can have at most 3 unconfirmed payments.
- Users can only see and claim their own payments.

## Server setup

Add to `backend/.env`:
```
PRO_UPI_ID=yourname@okaxis
PRO_UPI_NAME=MyExpenses
```
Leave `PRO_UPI_ID` empty to stop selling Pro. The app then shows "Pro isn't on sale yet".

**Tip:** a free **business/merchant UPI ID** works more reliably than a personal one. Some UPI apps refuse "pay with a pre-filled amount" links to personal IDs. Free options include PhonePe Business, Paytm for Business and BharatPe. If the link is refused, users can still copy the UPI ID and pay by hand.

## Development

Debug builds have a "pretend to be Pro" switch at the bottom of the Pro screen. Release builds don't.
