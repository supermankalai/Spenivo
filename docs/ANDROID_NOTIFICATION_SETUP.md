# Android notification tracking — setup & device testing

## 1. Build and install on a phone

Expo Go **cannot** load the custom notification listener. Use a development build:

```bash
cd mobile
npm install
# Phone: Settings › About phone › tap Build number 7× › Developer options › USB debugging ON
adb devices                     # the phone must be listed as "device"
npx expo run:android            # builds, installs and starts Metro
```

Or build a self-contained APK (no Metro needed):

```bash
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease
adb install -r app/build/outputs/apk/release/app-release.apk
```

`android/` is generated (Continuous Native Generation) and git-ignored. Native behaviour lives in `modules/upi-notifications` and `app.json`; rerun `npx expo prebuild --clean` after changing them.

## 2. Turn tracking on (as a user would)

1. Open Daily Spend → tap the **"Auto-tracking off"** pill (or Settings → Automatic tracking).
2. Read the explanation, then **"I understand — open Android settings"**.
3. Android shows *Notification access* (or *Device & app notifications*). Select **Daily Spend**, allow, confirm the system warning.
4. Return to the app: status should say **Notification access: Allowed** and **Listener connected**.

**Android 13+ "Restricted setting":** for apps installed outside a store (adb / APK), Android may grey out the switch. Open Android Settings › Apps › Daily Spend › ⋮ (top right) › **Allow restricted settings**, then repeat step 3.

**Samsung / Xiaomi / Oppo / Vivo:** set Daily Spend's battery usage to *Unrestricted* (Settings › Apps › Daily Spend › Battery), or the OS may stop the listener. Payments made while it is stopped are missed — enter them manually.

## 3. Which app is watched (bank SMS alerts)

Daily Spend reads **bank debit alert SMS** through the notifications of your SMS app. This works for UPI payments from any app, cards, ATM and NEFT, and needs no SMS permission. UPI-app notifications (PhonePe, Google Pay, …) are **not** watched by default: many apps do not notify for in-app payments, and watching both would create duplicates.

Watched by default: the phone's **default SMS app** plus `com.google.android.apps.messaging` (Google Messages), `com.samsung.android.messaging` (Samsung Messages), `com.android.mms` and `com.android.messaging`.

Requirements:

- Notifications must be **on** for your SMS app and for bank conversations (not muted/blocked; spam-filtered messages that never notify cannot be read).
- Check your default SMS app: `adb shell cmd role get-role-holders android.app.role.SMS`.

Edit the list in the app: Settings › Automatic tracking › *Read bank alerts from*. SMS apps use the bank-alert parser (a message must mention an account, card, UPI/VPA, reference or bank before anything else is checked); any other package you add uses the generic payment-app rules.

## 4. Test without spending money

Real bank SMS cannot be faked over adb, but Android's shell can post notifications. They come from package **`com.android.shell`** (parsed with the generic rules, which handle bank-style wording too), so temporarily add `com.android.shell` to *Read bank alerts from* in the app, make sure tracking is on and access granted, then:

```bash
# Bank-style debit alert → confirmed, payee SWIGGY, method UPI
adb shell cmd notification post -t "'AD-HDFCBK'" sms1 "'Rs.250.00 debited from A/c XX1234 to VPA swiggy@icici on 25-10-26. UPI Ref No 529812345678'"

# Successful payment → should appear on Today as confirmed (Other/Food category)
adb shell cmd notification post -t "'₹250 paid to Swiggy'" upi1 "'Payment successful. UPI Ref No. 412345678901'"

# Same reference again → ignored as exact duplicate
adb shell cmd notification post -t "'₹250 paid to Swiggy'" upi2 "'Payment successful. UPI Ref No. 412345678901'"

# Pending → appears under "to review", not counted
adb shell cmd notification post -t "'Payment processing'" upi3 "'Your payment of ₹2,000 to Electricity Board is pending'"

# Failed → ignored entirely
adb shell cmd notification post -t "'Payment failed'" upi4 "'Your payment of ₹450 to Ola could not be completed'"

# Incoming → ignored
adb shell cmd notification post -t "'₹800 received'" upi5 "'Anil Sharma sent you ₹800'"

# Person-to-person → recorded under Transfers (not counted as spending by default)
adb shell cmd notification post -t "'Money sent'" upi6 "'₹500 sent to Priya S successfully'"
```

Quoting: the outer double quotes are for your local shell, the inner single quotes keep the text as one argument on the device. In PowerShell, use `adb shell "cmd notification post -t '₹250 paid to Swiggy' upi1 'Payment successful'"`.

Then open the app (or Settings › Automatic tracking › *Check for detected payments now*). The tracking screen shows recorded/ignored counters.

Developer shortcut (bypasses the consent screen; **test devices only**):

```bash
adb shell cmd notification allow_listener com.dailyspend.app/com.dailyspend.upinotifications.UpiNotificationListenerService
adb shell cmd notification disallow_listener com.dailyspend.app/com.dailyspend.upinotifications.UpiNotificationListenerService
```

Debug reason codes (no content is ever logged):

```bash
adb shell setprop log.tag.DailySpendListener DEBUG
adb logcat -s DailySpendListener
```

**Remove `com.android.shell` from the list after testing.**

## 5. Adding real notification samples

1. Make a small real payment; capture the notification with the `dumpsys` command above.
2. **Redact** names, VPAs, account digits and references (replace with fake values of the same shape).
3. Add a case to `modules/upi-notifications/fixtures/notifications.json` with the expected result.
4. Run `cd mobile/android && ./gradlew :upi-notifications:testDebugUnitTest`. Adjust `TextRules.kt` or the app-specific parser in `Parsers.kt` until it passes.

## 6. Release checklist

- Generate a private upload keystore and configure signing (never commit it); the template signs release builds with the debug key.
- Review Google Play policies for notification listener use, sensitive financial data and the Data safety form; prepare the in-app prominent disclosure (already on the tracking screen) and a public privacy policy (base it on `docs/PRIVACY.md`).
- Remove `com.android.shell` from any default allowlist (it is not in the defaults).
- Test on several OEMs and Android versions with real, redacted samples.
