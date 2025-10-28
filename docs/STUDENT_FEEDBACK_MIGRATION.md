# Student Feedback feature: safe migration and rollout

This guide covers the safe, structured migration required for the new `Feedback` table and how to test locally before deploying to production on DigitalOcean.

## What’s changing
- Adds a new table `feedback` to store student feedback for a counseling session
- Enforces one feedback per session (unique on session_id)
- Relationships:
  - `Student.feedbacks` (one-to-many)
  - `CounselingSession.feedback` (one-to-one)

## Prerequisites
- Python virtual environment activated
- Database connection configured via `DATABASE_URL` in environment (PostgreSQL recommended in prod)

## 1) Install migration tooling
Flask-Migrate is now included in `requirements.txt`. Ensure your environment is up-to-date.

```powershell
# Windows PowerShell
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
pip install -r requirements.txt
```

## 2) Set FLASK_APP so CLI can locate the app
Flask CLI needs to know how to create the app. We use the app factory in `app/__init__.py`.

```powershell
$env:FLASK_APP = "app:create_app"
```

Optionally enable debug locally:
```powershell
$env:FLASK_DEBUG = "1"
```

## 3) Initialize migrations (first time only)
If your project doesn’t yet have a `migrations/` folder, initialize it once:

```powershell
flask db init
```

This creates the Alembic migration scaffolding at `./migrations`.

## 4) Generate migration for Feedback table
Create a migration script capturing the new model:

```powershell
flask db migrate -m "add feedback table"
```

Review the generated migration file under `migrations/versions/`. Confirm it includes a `feedback` table with:
- id (PK)
- session_id (FK -> counseling_sessions.id, unique)
- student_id (FK -> students.id)
- message (Text, not null)
- created_at, updated_at
- Unique constraint on session_id

## 5) Apply migration locally
Run the migration against your local database:

```powershell
flask db upgrade
```

Smoke test by starting the app and creating/submitting a feedback on a completed session.

## 6) Backup production database (DigitalOcean)
Before applying any schema updates in production, create a full backup.

If using DigitalOcean Managed PostgreSQL:
- Use the DO control panel snapshot/backup tools, or
- Run `pg_dump` from an admin/bastion host. Example:

```bash
# Example; run on a secure machine with network access to the DB
PGPASSWORD="<password>" pg_dump \
  --host <host> \
  --port <port> \
  --username <user> \
  --format=custom \
  --file backup_$(date +%Y%m%d_%H%M)_piyuguide.pgcustom \
  <database_name>
```

Store the dump securely and verify its size and contents quickly with `pg_restore -l`.

## 7) Apply migration in production
Deploy updated code, install dependencies, set env vars (`FLASK_APP=app:create_app`), then run:

```bash
flask db upgrade
```

Run this on the app host (e.g., the Droplet) with access to the production database.

## 8) Rollback (if needed)
If you must roll back the last migration:

```bash
flask db downgrade -1
```

Validate app behavior immediately after.

## Notes
- The app initializes Flask-Migrate in `app/extensions.py` and `app/__init__.py`.
- If your production process uses Gunicorn/Systemd, migrations should be run as a one-off administrative step, not during app boot.
- Always test locally first and keep a verified backup before any schema change in production.
