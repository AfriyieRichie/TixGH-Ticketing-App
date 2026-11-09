# TixGH: event ticketing for Ghana

> "TixGH" is a placeholder name. Change `PLATFORM_NAME` in `backend/.env`.

A ticketing platform for events and programs in Ghana: concerts, conferences,
church programs, school events, sports and more. It has Mobile Money first
checkout, QR tickets by SMS, email and WhatsApp, organizer dashboards and
offline gate check-in.

## Repository layout

| Folder     | What                                   | Stack                              |
|------------|----------------------------------------|------------------------------------|
| `backend/` | REST API, admin panel, background jobs | Python, Django, DRF, Celery        |
| `web/`     | Attendee site and organizer dashboard  | Next.js 15, TypeScript, Tailwind   |
| `mobile/`  | Attendee app and gate-scanner app      | React Native / Expo (SDK 58)       |

## Running the backend locally (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env          # then edit SECRET_KEY
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver
```

- API docs: http://127.0.0.1:8000/api/docs/
- Admin panel: http://127.0.0.1:8000/admin/ (fees, organizer verification, users)
- Tests: `.\.venv\Scripts\python manage.py test`
- Demo events: `.\.venv\Scripts\python manage.py seed_demo` (add `--reset` to recreate)

In development, SMS and email codes are printed in the server terminal instead
of being sent.

## Running the web app

In a second terminal:
```powershell
cd web
npm install
npm run dev        # http://localhost:3000
```
`web/.env.local` points at the API (`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`). Keep the backend running too.

## Running the mobile app

```powershell
cd mobile
npm install
npx expo start        # scan the QR with the Expo Go app (same Wi-Fi as your PC)
```
It talks to the live API by default; to use a local backend, copy `.env.example` to `.env`
and set `EXPO_PUBLIC_API_URL`. The **Scan** tab appears for users on an organizer team with
the Owner, Admin or Gate scanner role.

## Build phases

1. **Foundation** ✅ accounts (phone/email + OTP), organizers, teams and roles, payout accounts, platform fee settings, admin
2. **Events** ✅ venues, events, ticket types (Early Bird/VIP/tables), promo and access codes, publishing, public search
3. **Checkout and payments** ✅ guest checkout, 10-minute ticket holds, promo codes, Paystack (MoMo and cards) with automatic split, simulated gateway for development
4. **Ticket delivery** ✅ signed QR codes, SMS and email with PDF, no-app ticket pages, WhatsApp share, wallet, transfers, reminders, cancellation notices
5. **Web app** ✅ home, search, event pages, checkout, login, my tickets, organizer dashboard (events, tickets, promo codes, sales, attendees + CSV, payouts, team)
6. **Mobile app** ✅ one Expo app: events, offline ticket wallet, and a gate scanner (offline-capable, multi-gate sync, forged/duplicate detection)
7. Growth: discovery, affiliates, campaigns, reviews
8. Subscriptions and add-ons, refunds and resale, production deployment

## Business model

- **Ticket fee** on paid tickets (default 5% + GHS 1, editable in admin). Free tickets are never charged.
  The buyer pays it by default, or the organizer can absorb it. The Paystack charge is covered from this fee.
- **Organizer plans and add-ons** (Phase 8): Pro plan with a lower fee, SMS blasts, featured listings, instant payouts.

## API overview (Phase 1)

All endpoints are under `/api/v1/`. Authenticate with `Authorization: Bearer <access token>`.

| Endpoint | Purpose |
|---|---|
| `POST auth/otp/request/` | Send a code to a phone or email (`purpose`: login, verify_contact, password_reset) |
| `POST auth/otp/verify/` | Log in with the code; creates the account on first login |
| `POST auth/login/` | Password login with email or phone |
| `POST auth/token/refresh/`, `auth/logout/` | Token refresh and revoke |
| `GET/PATCH auth/me/` | Profile |
| `POST auth/me/contact/` | Add a verified email or phone to the account |
| `POST auth/password/change/`, `auth/password/reset/` | Passwords |
| `GET/POST organizations/` | My organizations; create one (you become owner) |
| `GET/PATCH organizations/{slug}/` | Organization profile |
| `POST organizations/{slug}/submit-verification/` | Request a Verified badge |
| `organizations/{slug}/members/` | Team (roles: owner, admin, finance, marketing, scanner) |
| `organizations/{slug}/invitations/` | Invite by phone or email |
| `GET/POST organizations/invitations/{token}/` | Preview and accept an invite |
| `organizations/{slug}/payout-accounts/` | MoMo or bank payout accounts |
| `GET organizations/public/{slug}/` | Public organizer profile |
| `GET config/` | Public settings for the apps (fees, regions, MoMo networks) |

## API overview (Phase 2)

| Endpoint | Purpose |
|---|---|
| `GET events/` | Public search. Filters: `q`, `category`, `region`, `city`, `organizer`, `when` (today, tomorrow, this_weekend, this_week, next_7_days, this_month), `date_from`/`date_to`, `price` (free/paid), `format`, `featured`, `sort` (date/newest) |
| `GET events/{slug}/` | Public event page with ticket prices (incl. booking fee) and "only X left" |
| `POST events/{slug}/promo-check/` | Check a promo or access code; returns discounted prices and unlocked hidden tickets |
| `GET categories/` | Event categories |
| `organizations/{org}/venues/` | Organizer's saved venues |
| `organizations/{org}/events/` | Organizer's events (drafts included); filter `status`, `when=upcoming/past` |
| `POST organizations/{org}/events/{slug}/publish/` · `unpublish/` · `cancel/` · `duplicate/` | Event lifecycle |
| `organizations/{org}/events/{slug}/ticket-types/` | Ticket types |
| `organizations/{org}/events/{slug}/promo-codes/` | Promo and access codes |

## API overview (Phase 3)

| Endpoint | Purpose |
|---|---|
| `POST checkout/` | Reserve tickets and start payment (guests allowed). Returns `payment.authorization_url` |
| `GET orders/{reference}/?token=` | View an order (owner, or a guest with the order's access token) |
| `POST orders/{reference}/verify/` | Confirm payment after returning from the gateway; issues tickets (safe to repeat) |
| `POST orders/{reference}/retry-payment/` | New payment attempt while tickets are still held |
| `GET orders/` | Signed-in user's orders (guest orders are attached when the phone or email is verified) |
| `POST payments/webhook/paystack/` | Paystack webhook (signature checked) |
| `GET payments/simulated/{payment_ref}/` | Test-mode payment page (only when `PAYMENT_GATEWAY=simulated`) |

### Going live with Paystack
Set these in `backend/.env`, then point Paystack's webhook to `https://<your-domain>/api/v1/payments/webhook/paystack/`:
```
PAYMENT_GATEWAY=paystack
PAYSTACK_SECRET_KEY=sk_live_...
PAYSTACK_PUBLIC_KEY=pk_live_...
```
Unpaid orders are expired by `python manage.py expire_orders` or the Celery beat task. Holds are also enforced without it.

## API overview (Phase 4)

| Endpoint | Purpose |
|---|---|
| `GET tickets/` | My ticket wallet (`when=upcoming/past/all`), with QR payloads |
| `GET/PATCH tickets/{code}/` | One ticket; set the attendee name |
| `POST tickets/{code}/transfer/` | Send to a friend by phone or email (new code issued, old QR stops working) |
| `GET tickets/{code}/pdf/` | PDF ticket |
| `POST orders/{reference}/resend/` | Re-send tickets by SMS and email (3 per hour) |
| `/t/{order_ref}/{token}/` | Private, no-login ticket page linked from SMS/email (plus `pdf/`) |

QR codes contain `TX1:<code>:<signature>`, signed with a per-event key (`apps/tickets/signing.py`),
so gate scanners can reject forged tickets offline. Background jobs: order confirmation on payment,
hourly event reminders (24 h before), and cancellation notices. Every SMS and email is logged under
**Deliveries** in the admin panel.

## API overview (Phase 5)

| Endpoint | Purpose |
|---|---|
| `GET organizations/{org}/overview/` | Dashboard headline numbers (earnings, tickets, recent orders, top events) |
| `GET organizations/{org}/events/{slug}/stats/` | Per-event sales, per ticket type, daily earnings, check-ins |
| `GET organizations/{org}/events/{slug}/attendees/` | Attendee list (`q`, `status`, `ticket_type`, `export=csv`) |
| `GET payments/banks/` | Ghana banks for payout accounts (from the gateway, cached daily) |

## API overview (Phase 6: gate scanning)

| Endpoint | Purpose |
|---|---|
| `GET scanner/events/` | Events the user can scan, with check-in counts |
| `GET scanner/events/{slug}/manifest/?since=` | Offline data: event signing key and ticket list (deltas with `since`) |
| `POST scanner/events/{slug}/scan/` | Check one ticket in (server decides; row-locked against double entry) |
| `POST scanner/events/{slug}/sync/` | Upload offline scans; later duplicates are reported back |
| `POST scanner/events/{slug}/undo/` | Reverse a mistaken check-in |
