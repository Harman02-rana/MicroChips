# Auth and Supabase Setup

This app uses normal email/password auth for both Customer and Business accounts. Supabase is used as the PostgreSQL database for users, products, orders, and store data.

Google signup/login is handled through Supabase Auth and then converted into the app's normal storefront session.

## Supabase database

1. Go to `https://supabase.com/dashboard`.
2. Open your project, or create a new project.
3. Go to `Project Settings` -> `Database`.
4. Copy the database password or reset it if you do not know it.
5. Copy the database host or pooler connection details.

Set these values in `.env` locally and in your deployment provider:

```text
SUPABASE_DB_HOST=your-supabase-db-or-pooler-host
SUPABASE_DB_PORT=5432
SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=your-real-database-password
```

If Supabase gives you a pooler user like `postgres.<project-ref>`, put that full value in `SUPABASE_DB_USER`.

## Production values

```text
APP_ENV=production
FLASK_SECRET_KEY=a-long-random-secret
PUBLIC_BASE_URL=https://your-live-domain.com
```

With `APP_ENV=production`, the app will fail fast if Supabase cannot connect. In development it may fall back to local SQLite so you can still test the storefront.

## Google OAuth

1. In Google Cloud Console, create an OAuth 2.0 Web Client.
2. Add these authorized redirect URIs:

```text
http://127.0.0.1:5000/auth/google/callback
https://your-live-domain.com/auth/google/callback
```

3. In Supabase, open `Authentication` -> `Providers` -> `Google`.
4. Enable Google and paste the Google Client ID and Client Secret.
5. In Supabase `Authentication` -> `URL Configuration`, add the same callback URLs to the allowed redirect URLs.
6. Make sure the app has these environment values:

```text
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_KEY=your-anon-key
PUBLIC_BASE_URL=https://your-live-domain.com
```

For local testing, set `PUBLIC_BASE_URL=http://127.0.0.1:5000`.

## Verify

Open:

```text
http://127.0.0.1:5000/api/health
```

For production, you want:

```json
{
  "store_mode": "postgresql",
  "supabase_connected": true
}
```

Then test Customer signup/login and Business signup/login from the storefront.
