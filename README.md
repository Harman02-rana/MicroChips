# Microchip Cart

Responsive ecommerce website for microchip products built with Flask, HTML, CSS, JavaScript, email/password auth, and a Supabase PostgreSQL data layer.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open:

- Storefront: http://127.0.0.1:5000
- Admin: http://127.0.0.1:5000/admin
- Owner panel: http://127.0.0.1:5000/owner

Default local admin:

- Email: `microchipcaty025@gmail.com`
- Password: `Micro#025`

Default owner login uses `OWNER_EMAIL` / `OWNER_PASSWORD` when set, otherwise it falls back to the admin credentials.

## Supabase PostgreSQL

Use the Supabase database host and keep the password in `.env`. Recommended setup:

```text
SUPABASE_DB_HOST=aws-1-ap-south-1.pooler.supabase.com
SUPABASE_DB_PORT=6543
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres.ybbomppuyrucifdwgmpf
SUPABASE_DB_PASSWORD=your-real-supabase-db-password
```

The app uses the Supabase pooler endpoint for IPv4-compatible local and serverless deployments. It builds a safe `postgresql://` URL from those fields, URL-encodes the password, and adds `sslmode=require` for Supabase.

You can also use a full URL:

```text
DATABASE_URL=postgresql://postgres.ybbomppuyrucifdwgmpf:your-url-encoded-password@aws-1-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require
```

Do not leave `[YOUR-PASSWORD]` in `DATABASE_URL`.

For the full auth/database checklist, see `AUTH_SETUP.md`.

## SMTP

Copy `.env.example` values into your environment and set `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM` if you want order emails to be sent to the admin. Signup and login do not require SMTP.

## Payments

Card/UPI checkout uses Stripe Checkout when `STRIPE_SECRET_KEY` is configured. Add a Stripe webhook that points to:

```text
https://your-domain.com/api/payments/stripe-webhook
```

Listen for `checkout.session.completed` and put the webhook signing secret in `STRIPE_WEBHOOK_SECRET`. Without Stripe keys, online checkout is disabled and customers can still use cash on delivery.

## Launch checklist

- Set `APP_ENV=production`.
- Set a long random `FLASK_SECRET_KEY`.
- Change `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `ADMIN_NOTIFICATION_EMAIL`.
- Set `OWNER_EMAIL` and `OWNER_PASSWORD` for the company-only owner dashboard.
- Set `PUBLIC_BASE_URL` to your live HTTPS domain.
- Use Supabase PostgreSQL with the real database password.
- Configure SMTP if you want order notification emails.
- Configure Stripe live keys and the webhook endpoint before accepting online payments.
- Add your real products from `/admin`; sample products hide automatically after the first real product.
- Deploy with `gunicorn wsgi:app` or the included `Procfile`.
- Check `/api/health` after deployment.

## Product Images

Admin product upload accepts `.webp` only. The suggested path starts at:

```text
static/uploads/products/0.webp
```

The next product suggestion checks both the folder and saved product records, then moves to `1.webp`, `2.webp`, and so on. Sample product images live under `static/images/samples/`, so real product numbering stays clean. Once one real product is added, sample products are hidden from the storefront automatically.
