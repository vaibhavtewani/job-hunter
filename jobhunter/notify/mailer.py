"""Sends the digest through SMTP (Gmail with an app password by default)."""
from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import List

REQUIRED_ENV = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")


def email_missing_env() -> List[str]:
    return [var for var in REQUIRED_ENV if not os.environ.get(var)]


def send_email(subject: str, html: str, text: str, cfg: dict) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    recipients = [a.strip() for a in (os.environ.get("DIGEST_TO") or sender).split(",") if a.strip()]
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(text)
    message.add_alternative(html, subtype="html")
    host = cfg.get("smtp_host", "smtp.gmail.com")
    port = int(cfg.get("smtp_port", 465))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
        smtp.login(sender, os.environ["GMAIL_APP_PASSWORD"])
        smtp.send_message(message, to_addrs=recipients)
