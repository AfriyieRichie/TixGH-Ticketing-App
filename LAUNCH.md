# Launch checklist

Everything between the free test setup and selling real tickets. Work top to bottom.

## 1. Business and brand
- [ ] Choose the brand name (another Ghana platform already uses "TixGh") and check the trademark.
- [ ] Register the business (Registrar-General's Department) and get a TIN.
- [ ] Buy the domain (e.g. `yourbrand.com`) and matching social handles.
- [ ] Rename the app: `PLATFORM_NAME` (Render), `NEXT_PUBLIC_SITE_NAME` (Vercel), `mobile/app.json` name.
- [ ] Have a lawyer review `/legal/terms`, `/legal/privacy` and `/legal/refunds`.
- [ ] Register with Ghana's **Data Protection Commission** (required for organisations processing personal data).

## 2. Payments (Paystack)
- [ ] Complete Paystack **Compliance** (Profile, Contact, Owner, Account, Service agreement) as a Registered Business.
- [ ] Ask Paystack to confirm: split payments/subaccounts for a marketplace, **mobile money subaccounts** for organizers,
      and **how refunds are funded on split transactions** (from your balance vs the subaccount's).
- [ ] Switch Render to live keys: `PAYSTACK_SECRET_KEY=sk_live_…`, `PAYSTACK_PUBLIC_KEY=pk_live_…`.
- [ ] Set the **Live** webhook URL in Paystack: `https://<api-domain>/api/v1/payments/webhook/paystack/`.
- [ ] Make one real GHS 1 purchase and refund it end to end.

## 3. Messaging
- [ ] SMS: open an **Arkesel** or **Hubtel** account, register the sender ID, set `SMS_BACKEND` + keys on Render.
- [ ] Email: authenticate your domain in **Brevo** (SPF/DKIM/DMARC), set `DEFAULT_FROM_EMAIL=YourBrand <tickets@yourdomain>`.
- [ ] Check Brevo's daily limit vs expected volume; set `CAMPAIGN_DAILY_LIMIT` accordingly (or upgrade Brevo).

## 4. Hosting (from free to always-on)
- [ ] Render: upgrade `tixgh-api` to an always-on instance (no 50 s cold starts).
- [ ] Website: Vercel Pro **or** move to Cloudflare Workers Paid (Vercel Hobby is non-commercial).
- [ ] Neon: confirm storage headroom; enable point-in-time restore / backups on a paid plan when revenue allows.
- [ ] Custom domains: `yourdomain.com` → Vercel, `api.yourdomain.com` → Render. Update `FRONTEND_URL`,
      `CORS_ALLOWED_ORIGINS`, `BACKEND_URL`, `NEXT_PUBLIC_API_URL`, Paystack webhook, cron-job.org URL.
- [ ] Rotate secrets that were shared during setup (Paystack test keys, cron secret).

## 5. Before the first real event
- [ ] Create the organizer account, payout account (verify the subaccount appears in Paystack), and get verified.
- [ ] Gate rehearsal: 2 phones scanning (one offline), re-entry on/off, a group ticket, a duplicate.
- [ ] Badge desk rehearsal (conference events): laptop + label printer, Chrome `--kiosk-printing`, label size.
- [ ] Publish the mobile app (EAS build → Play Store first) or use the web ticket pages until it's live.

## 6. Known follow-ups (not blockers)
- Website login tokens are in browser storage; move to httpOnly cookies.
- Organizer plans (Pro) and paid add-ons (featured listings, SMS bundles): Phase 8b.
- Error monitoring (e.g. Sentry free tier) and uptime alerts.
