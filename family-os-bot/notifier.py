"""
notifier.py — Send HTML emails via Gmail SMTP over SSL.

Reads credentials from environment variables:
  GMAIL_USER         — the sending Gmail address
  GMAIL_APP_PASSWORD — a Gmail App Password (not your account password)
  NOTIFY_EMAIL       — recipient address (your iCloud address)

Uses SSL on port 465, which does not require STARTTLS negotiation.
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 465


def send_email(subject: str, html_body: str) -> bool:
    """Send an HTML email via Gmail SMTP SSL.

    Args:
        subject: Email subject line.
        html_body: Full HTML string for the email body.

    Returns:
        True if the email was sent successfully, False otherwise.
        Errors are logged but not raised, so the caller can decide
        how to handle failure.
    """
    gmail_user = os.environ.get("GMAIL_USER", "").strip()
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    notify_email = os.environ.get("NOTIFY_EMAIL", "").strip()

    if not gmail_user:
        logger.error("GMAIL_USER environment variable is not set.")
        return False
    if not gmail_password:
        logger.error("GMAIL_APP_PASSWORD environment variable is not set.")
        return False
    if not notify_email:
        logger.error("NOTIFY_EMAIL environment variable is not set.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Family OS Bot <{gmail_user}>"
    msg["To"] = notify_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        logger.info(f"Connecting to {GMAIL_HOST}:{GMAIL_PORT} ...")
        with smtplib.SMTP_SSL(GMAIL_HOST, GMAIL_PORT) as server:
            server.login(gmail_user, gmail_password)
            server.sendmail(gmail_user, notify_email, msg.as_string())
        logger.info(f"Email sent: '{subject}' → {notify_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail authentication failed. "
            "Verify GMAIL_USER and GMAIL_APP_PASSWORD. "
            "Make sure you're using an App Password, not your account password."
        )
        return False
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient refused by server: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error while sending email: {e}")
        return False
    except OSError as e:
        logger.error(f"Network error connecting to Gmail: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        return False
