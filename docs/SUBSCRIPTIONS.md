# Free and Pro

MyExpenses has two plans. Pro is a Google Play subscription.

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

| Base plan | Price | Notes |
|---|---|---|
| `monthly` | ₹49 / month | |
| `yearly` | ₹399 / year | About 32% cheaper than monthly; has a 7-day free trial |

The app always shows the prices Google Play returns, so you can change them in Play Console without updating the app.

## Play Console setup (one time)

1. Upload a build that includes billing (this one, or later) to the **Internal testing** track. Play only lets you create subscriptions after a build with the billing permission has been uploaded.
2. Go to **Monetize → Subscriptions → Create subscription**:
   - **Product ID:** `dailyspend_pro`. It must match exactly, and it can't be changed later.
   - **Name:** MyExpenses Pro.
3. Add two **base plans** to it:
   - `monthly`: auto-renewing, billed every month, ₹49.
   - `yearly`: auto-renewing, billed every year, ₹399.
4. On the `yearly` base plan, add an **offer**:
   - **Eligibility:** new customer acquisition, i.e. "Never had this subscription".
   - **Phase:** a 7-day free trial.
   - Then activate the offer and both base plans.
5. Go to **Setup → License testing** and add the Google accounts that should be able to buy without being charged.
6. Install the app from the internal testing link on a tester's phone.

## How it works in the app

- **Google Play decides who has Pro.** The app checks at launch and whenever it comes back to the front (`checkPro` in `mobile/src/services/billing.ts`). Pro follows the Google account, so it returns after a reinstall or on a new phone. **Restore purchase** on the Pro screen checks again on demand.
- **Purchases are acknowledged on the phone.** Google refunds any purchase that isn't acknowledged within 3 days.
- **Offline:** if Play can't be reached, the last known answer is used for up to 7 days.
- **Development builds** have a "pretend to be Pro" switch at the bottom of the Pro screen, so the Pro features can be tried before Play Console is set up. It doesn't exist in release builds.

### Not done yet: checking purchases on the server

The backend doesn't verify purchases. The app trusts Google Play on the phone. That's normal for a small app, but a modified APK could unlock Pro.

To make it tamper-proof later:
1. Send `purchaseToken` to a backend endpoint.
2. Verify it with the Google Play Developer API (`purchases.subscriptionsv2.get`) using a service account.
3. Subscribe to Real-time developer notifications so renewals and cancellations update the server.
