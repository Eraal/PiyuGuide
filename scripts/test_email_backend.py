import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app

"""
Test email sending via the application's email backend, which tries SMTP first
and falls back to Brevo HTTP API if configured.

Usage (PowerShell):
  # Set your env vars as used in production
  # $env:MAIL_SERVER="smtp-relay.brevo.com"
  # $env:MAIL_PORT="587"
  # $env:MAIL_USE_TLS="true"
  # $env:MAIL_USERNAME="<brevo-smtp-login>"
  # $env:MAIL_PASSWORD="<brevo-smtp-password>"
  # $env:MAIL_DEFAULT_SENDER="PiyuGuide <no-reply@piyuguide.live>"
  # Optional API fallback:
  # $env:BREVO_API_KEY="<brevo-v3-api-key>"

  python scripts/test_email_backend.py you@example.com
"""

def main():
    if len(sys.argv) < 2:
        print("Provide recipient email as argument, e.g., python scripts/test_email_backend.py you@example.com")
        sys.exit(2)
    to = sys.argv[1]

    app = create_app()
    with app.app_context():
        cfg = app.config
        print("Active email config:")
        for k in ("MAIL_SERVER","MAIL_PORT","MAIL_USE_TLS","MAIL_USE_SSL","MAIL_DEFAULT_SENDER","MAIL_SUPPRESS_SEND"):
            print(f"  {k}={cfg.get(k)}")
        print(f"  MAIL_USERNAME set: {'yes' if bool(cfg.get('MAIL_USERNAME')) else 'no'}")
        print(f"  MAIL_PASSWORD set: {'yes' if bool(cfg.get('MAIL_PASSWORD')) else 'no'}")
        print(f"  BREVO_API_KEY set: {'yes' if bool(cfg.get('BREVO_API_KEY')) else 'no'}")

        from app.utils.email_backend import send_email_with_fallback
        try:
            send_email_with_fallback(
                subject="PiyuGuide backend test",
                recipients=[to],
                body="This is a backend test. If you received this, at least one path (SMTP or API) worked."
            )
            print("Email sent successfully (SMTP or API).")
        except Exception as e:
            print("Email send failed:", e)
            sys.exit(1)

if __name__ == "__main__":
    main()
