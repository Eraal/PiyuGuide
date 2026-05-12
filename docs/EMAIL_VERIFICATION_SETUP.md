# Email Verification with Brevo (Sendinblue) on Name.com

This guide explains how to enable and deploy the email verification flow using Brevo SMTP and a no-reply sender on your Name.com domain (e.g., no-reply@piyuguide.live).

## 1) DNS setup on Name.com (one-time)

- In Brevo, go to Senders & IP > Domains (or Senders & Domains) > Add domain: `piyuguide.live`.
- Follow Brevo’s instructions to add records in Name.com DNS:
  - SPF (TXT on root `@`) – typically: `v=spf1 include:spf.brevo.com ~all` (merge with existing SPF if you already have one)
  - DKIM (CNAME) – Brevo provides two DKIM records; add them exactly as shown
  - DMARC (TXT on `_dmarc`) – e.g., `v=DMARC1; p=none; rua=mailto:dmarc@piyuguide.live`
- Save records and wait for DNS to propagate, then verify the domain in Brevo.

Result: emails from `no-reply@piyuguide.live` will pass SPF/DKIM/DMARC and avoid spam.

## 2) Server environment variables (DigitalOcean)

Set these on your app server (systemd service or `.env` for gunicorn):

```bash
# Brevo SMTP
export MAIL_SERVER="smtp-relay.brevo.com"
export MAIL_PORT="587"
export MAIL_USE_TLS="true"
export MAIL_USERNAME="<your-brevo-smtp-login>"      # usually shown in Brevo SMTP settings
export MAIL_PASSWORD="<your-brevo-smtp-password>"   # generate in Brevo > SMTP & API
export MAIL_DEFAULT_SENDER="PiyuGuide <no-reply@piyuguide.live>"

# Optional HTTP API fallback (if SMTP is blocked by your provider, this will still send):
export BREVO_API_KEY="<your-brevo-v3-api-key>"

# App (ensure set in production)
export SECRET_KEY="<a-strong-random-secret>"
export PREFERRED_URL_SCHEME="https"
```

If you use a systemd unit, add the `Environment=` lines in `deploy/systemd/piyuguide.service` or reference an EnvironmentFile and reload systemd.

## 3) Install dependency on server

```bash
# In your project directory (venv active)
pip install -r requirements.txt
```

`Flask-Mail` is required for SMTP. If outbound SMTP is filtered by your VPS provider, also set `BREVO_API_KEY` to enable the HTTP API fallback.

## 4) Database migration

We added:
- `users.email_verified`, `users.email_verified_at`, `users.email_verification_sent_at`
- `verification_tokens` table

Run migrations (Flask-Migrate):

```bash
# Export FLASK_APP so the CLI finds your factory
export FLASK_APP="app:create_app"

# Create migration script
flask db migrate -m "email verification: user fields + verification_tokens"

# Apply to the database
flask db upgrade
```

If you’re behind a systemd service, stop the app before `upgrade` and start it after, or ensure zero-downtime if using multiple workers.

## 5) Restart the app

```bash
# If using systemd
sudo systemctl restart piyuguide

# Check logs
sudo journalctl -u piyuguide -f
```

## 6) Testing in production

- Register a new student account.
- You should be redirected to the “Confirm your email” page.
- Check inbox for an email from `PiyuGuide <no-reply@piyuguide.com>`.
- Click the link OR copy the 6-digit code into the app’s code form.
- After success, you should be auto-logged-in to the student dashboard.

## Troubleshooting

- No emails arriving:
  - Verify Brevo SMTP credentials and domain verification (SPF/DKIM/DMARC).
  - Check server logs for SMTP errors.
  - Some campus email systems can block links; try the code path.
- “Module not found: flask_mail”: run `pip install -r requirements.txt` on the server.
- Token expired: resend verification from the Check Email page.

## Notes

- Links and codes expire in 48 hours by default. Attempts for code are limited (5 tries).
- Resend is throttled to 60 seconds between sends.
- Admins can still manually mark users verified in the database if needed (set `email_verified=true`, `email_verified_at=NOW()`).
