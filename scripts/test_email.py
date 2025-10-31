import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask_mail import Message
from app import create_app
from app.extensions import mail

"""
Quick SMTP send test.
Usage (PowerShell):
  $env:MAIL_SERVER="smtp-relay.brevo.com"
  $env:MAIL_PORT="587"
  $env:MAIL_USE_TLS="true"
    $env:MAIL_USERNAME="9a7cb0001@smtp-brevo.com"
    $env:MAIL_PASSWORD="<your-brevo-smtp-password>"
  $env:MAIL_DEFAULT_SENDER="PiyuGuide <no-reply@piyuguide.live>"
  $env:MAIL_SUPPRESS_SEND="false"
  python scripts/test_email.py you@domain.tld
"""

def main():
    if len(sys.argv) < 2:
        print("Provide recipient email as argument, e.g., python scripts/test_email.py you@example.com")
        sys.exit(2)
    recipient = sys.argv[1]

    app = create_app()
    with app.app_context():
        print("SMTP config:")
        print(f"  MAIL_SERVER={app.config.get('MAIL_SERVER')}")
        print(f"  MAIL_PORT={app.config.get('MAIL_PORT')}")
        print(f"  MAIL_USE_TLS={app.config.get('MAIL_USE_TLS')}")
        print(f"  MAIL_USE_SSL={app.config.get('MAIL_USE_SSL')}")
        print(f"  MAIL_DEFAULT_SENDER={app.config.get('MAIL_DEFAULT_SENDER')}")
        print(f"  MAIL_SUPPRESS_SEND={app.config.get('MAIL_SUPPRESS_SEND')}")
        user = app.config.get('MAIL_USERNAME')
        if user:
            hint = (user[:2] + "…" + user[-2:]) if len(user) > 4 else "(short)"
            print(f"  MAIL_USERNAME set: yes ({hint}, len={len(user)})")
        else:
            print("  MAIL_USERNAME set: no")
        print(f"  MAIL_PASSWORD set: {'yes' if bool(app.config.get('MAIL_PASSWORD')) else 'no'}")
        msg = Message(
            subject="PiyuGuide SMTP test",
            recipients=[recipient],
            body="This is a test email from your local PiyuGuide app. If you received this, SMTP is working."
        )
        try:
            mail.send(msg)
            print("Email sent successfully.")
        except Exception as e:
            print("Failed to send email:", e)
            sys.exit(1)

if __name__ == "__main__":
    main()
