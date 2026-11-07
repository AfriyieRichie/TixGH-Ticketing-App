# Deploying TixGH (free staging setup)

| Part | Host | Plan |
|---|---|---|
| Website (`web/`) | Vercel | Hobby (free, for testing; upgrade or move before selling real tickets) |
| API (`backend/`) | Render | Free web service (Frankfurt) |
| Database | Neon | Free Postgres (Frankfurt) |
| Images | Cloudinary | Free |
| Scheduled jobs + keep-awake | cron-job.org | Free |

Payments stay in **Paystack test mode**: no real money moves.

Do the steps in order. Keep a notepad open for the values you'll copy.

---

## 1. Database: Neon
1. Sign up at **neon.tech** (GitHub login is fine).
2. Create a project: name `tixgh`, Postgres 17, region **AWS Europe Central 1 (Frankfurt)**.
3. On the dashboard, click **Connect** and copy the connection string. It looks like
   `postgresql://user:password@ep-xxx-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require`
   → save it as **DATABASE_URL**.

## 2. Images: Cloudinary
1. Sign up at **cloudinary.com** (free plan).
2. On the dashboard, find **API environment variable**. It looks like
   `cloudinary://123456789:abcDEF...@your-cloud-name` → save it as **CLOUDINARY_URL**.

## 3. API: Render
1. Sign up at **render.com** with GitHub.
2. **New → Blueprint** → choose the `TixGH-Ticketing-App` repo. Render reads `render.yaml`.
3. Fill in the values it asks for:
   | Key | Value |
   |---|---|
   | DATABASE_URL | from step 1 |
   | CLOUDINARY_URL | from step 2 |
   | FRONTEND_URL | `https://example.com` for now (fixed in step 5) |
   | CORS_ALLOWED_ORIGINS | `https://example.com` for now |
   | PAYSTACK_SECRET_KEY / PAYSTACK_PUBLIC_KEY | your Paystack **test** keys (`sk_test_…`, `pk_test_…`) |
   | DJANGO_SUPERUSER_EMAIL | the email you'll use for the admin panel |
   | DJANGO_SUPERUSER_PASSWORD | a strong password (store it safely) |
4. Click **Apply**. The first build takes ~5 minutes.
5. When it's live, copy the service URL, e.g. `https://tixgh-api.onrender.com` → save it as **API_URL**.
6. Check: open `API_URL/api/v1/events/` and you should see the demo events as JSON.
   Admin panel: `API_URL/admin/`.

## 4. Website: Vercel
1. On vercel.com: **Add New → Project** → import `TixGH-Ticketing-App`.
2. Click **Import single project** next to **web (Next.js)**. Don't use "Services" or import `backend`.
3. Root Directory: `web` (set automatically by the step above).
4. **Environment Variables**:
   | Key | Value |
   |---|---|
   | NEXT_PUBLIC_API_URL | your **API_URL** (no trailing slash) |
   | NEXT_PUBLIC_SITE_NAME | `TixGH` |
5. **Deploy**. Copy the site URL, e.g. `https://tixgh-ticketing-app.vercel.app` → save it as **SITE_URL**.

## 5. Connect the two
In Render → your service → **Environment**, change:
| Key | Value |
|---|---|
| FRONTEND_URL | your **SITE_URL** |
| CORS_ALLOWED_ORIGINS | your **SITE_URL** |

Save. Render redeploys automatically (~3 minutes).

## 6. Scheduled jobs and keep-awake: cron-job.org
Render's free plan sleeps after 15 minutes without visitors. This job keeps it awake, expires unpaid orders and sends event reminders.
1. In Render → Environment, copy the value of **CRON_SECRET**.
2. Sign up at **cron-job.org** → **Create cronjob**:
   - URL: `API_URL/api/v1/internal/cron/`
   - Schedule: every **10 minutes**
   - Advanced → Request method: **POST**; Headers: `X-Cron-Secret` = your CRON_SECRET
3. Save, then **Test run**. The response should be like `{"expired_orders":0,"reminders_sent":0}`.

## 7. Paystack webhook (test mode)
Paystack dashboard → **Settings → API Keys & Webhooks** (Test mode):
- **Test Webhook URL:** `API_URL/api/v1/payments/webhook/paystack/`

Tickets are now issued even if a buyer closes the browser after paying.

---

## 8. Email delivery: Brevo
Render's free plan blocks SMTP (Gmail SMTP won't work there), so email goes through Brevo's web API.
1. Sign up at **brevo.com** (free: 300 emails/day).
2. **Senders, Domains & Dedicated IPs → Senders → Add a sender** with the address emails should come from, then verify it from the email Brevo sends.
3. **SMTP & API → API Keys → Generate a new API key** → copy it (starts with `xkeysib-`).
4. In Render → Environment, set:
   | Key | Value |
   |---|---|
   | EMAIL_BACKEND | `apps.core.email_backends.BrevoAPIBackend` |
   | BREVO_API_KEY | your Brevo API key |
   | DEFAULT_FROM_EMAIL | `TixGH <the verified sender address>` |
   The `EMAIL_HOST*` / `EMAIL_PORT` / `EMAIL_USE_TLS` settings aren't used with Brevo and can be deleted.

Until you have your own domain, emails sent from a Gmail address may land in Spam.

## Signing in on staging
SMS isn't connected yet, so login codes are printed in **Render → your service → Logs** (search for `[SMS]`).
You can also sign in with **Use password instead** using your admin email and password.

## Updating
Every `git push` to `main` redeploys both Render and Vercel automatically.

## Before real sales (costs then)
- Render: upgrade to an always-on instance (~$7/month), or keep the cron keep-awake.
- Website: Vercel Pro ($20/month), or move to Cloudflare Workers Paid ($5/month).
- Paystack: complete Compliance, switch keys to `sk_live_…`/`pk_live_…`.
- Connect an SMS provider (Arkesel/Hubtel) and an email service.
