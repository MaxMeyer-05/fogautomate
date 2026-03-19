import smtplib
from email.message import EmailMessage
import sys
from pathlib import Path

root_path = Path(__file__).resolve().parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.append(str(root_path))

from config.config import SMTP_HOST, SENDER_EMAIL, ADMIN_EMAILS, logging

def _send_email(subject: str, body: str, priority: str = "normal"):
    """
    Send an email with the specified subject and body.
    Args:
        subject (str): The email subject.
        body (str): The email body.
        priority (str): The priority of the email ("low", "normal", "high").
    """
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = ", ".join(ADMIN_EMAILS)

    if priority.lower() == "high":
        msg['X-Priority'] = '1'
    if priority.lower() == "normal":
        msg['X-Priority'] = '2'
    if priority.lower() == "low":
        msg['X-Priority'] = '3'

    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, 25) as server:
            server.send_message(msg)
    except Exception as e:
        logging.error(f"Failed to send email '{subject}': {e}", exc_info=True)