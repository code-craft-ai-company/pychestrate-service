
import secrets
import smtplib

from email.message import EmailMessage

from flask import session, url_for

from automojo.pychestrate.core.storage.orm import User
from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS


def csrf_token_generate() -> str:
    """Return a CSRF token stored in the session, creating one if necessary."""
    token = session.get("csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_token_validate(token: str) -> bool:
    """Validate *token* against the session."""
    if not token:
        return False
    session_token = session.get("csrf_token")
    return session_token is not None and secrets.compare_digest(session_token, token)


def send_password_reset_email(user: User, reset_token: str, reset_endpoint: str):
    """Send a password reset email to *user* containing the reset link."""

    reset_link = url_for(
        reset_endpoint,
        username=user.username,
        token=reset_token,
        _external=True
    )

    msg = EmailMessage()
    msg["Subject"] = "Automation Mojo Password Reset"

    sender_addr = (
        f"no-reply@{SITE_SHARED_GLOBALS.HOST}"
    )

    msg["From"] = sender_addr
    msg["To"] = user.email

    msg.set_content(
        (
            f"Hello {user.display_name},\n\n"
            f"A request was made to reset your Automation Mojo password. "
            f"Please follow the link below to choose a new password:\n"
            f"{reset_link}\n\n"
            "If you did not request this change, you can safely ignore this email."
        )
    )

    with smtplib.SMTP(SITE_SHARED_GLOBALS.SMTP_HOST, SITE_SHARED_GLOBALS.SMTP_PORT) as smtp:
        cred = SITE_SHARED_GLOBALS.SMTP_CREDENTIAL
        if cred is not None and cred.password is not None:
            smtp.starttls()
            smtp.login(cred.username, cred.password)
        smtp.send_message(msg)
