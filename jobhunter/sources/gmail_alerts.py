"""Job-alert emails from LinkedIn, Bayt, GulfTalent, Naukrigulf, Indeed... read from your inbox over IMAP.

The boards do the searching (under your own logged-in alert settings); we only read the emails, read-only.
"""
from __future__ import annotations

import email
import imaplib
import os
from datetime import datetime, timedelta
from email import policy
from typing import List, Optional

from ..dates import parse_datetime
from ..models import Job
from .base import Source
from .email_parsers import parse_alert_html

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def imap_date(dt: datetime) -> str:
    return "%02d-%s-%d" % (dt.day, _MONTHS[dt.month - 1], dt.year)  # locale-independent


def _html_body(message) -> Optional[str]:
    part = message.get_body(preferencelist=("html",))
    return part.get_content() if part is not None else None


class GmailAlertsSource(Source):
    name = "gmail_alerts"
    required_env = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD")
    default_trust_location = True

    def fetch(self) -> List[Job]:
        since = imap_date(self.ctx.now - timedelta(days=int(self.cfg.get("lookback_days", 3))))
        limit = int(self.cfg.get("max_messages_per_sender", 30))
        jobs: List[Job] = []
        imap = imaplib.IMAP4_SSL(self.cfg.get("imap_host", "imap.gmail.com"))
        try:
            imap.login(os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"])
            imap.select(self.cfg.get("mailbox", "INBOX"), readonly=True)
            for sender in self.cfg.get("senders") or []:
                try:
                    jobs.extend(self._jobs_from_sender(imap, sender, since, limit))
                except Exception as exc:
                    self.fail(sender, exc)
        finally:
            try:
                imap.logout()
            except Exception:
                pass
        return jobs

    def _jobs_from_sender(self, imap, sender: str, since: str, limit: int) -> List[Job]:
        status, data = imap.search(None, "FROM", '"%s"' % sender, "SINCE", since)
        if status != "OK":
            raise RuntimeError("IMAP search returned %s" % status)
        jobs = []
        for msg_id in (data[0] or b"").split()[-limit:]:
            status, parts = imap.fetch(msg_id, "(BODY.PEEK[])")  # PEEK: don't mark as read
            raw = next((p[1] for p in parts or [] if isinstance(p, tuple)), None)
            if status != "OK" or raw is None:
                continue
            message = email.message_from_bytes(raw, policy=policy.default)
            html = _html_body(message)
            if not html:
                continue
            received = parse_datetime(str(message.get("Date") or ""))
            for item in parse_alert_html(html):
                jobs.append(
                    Job(
                        title=item["title"],
                        company=item["company"],
                        url=item["url"],
                        source="gmail_alerts:" + item["board"],
                        location=item["location"],
                        posted_at=received,
                        extra={"email_subject": str(message.get("Subject") or "")},
                    )
                )
        return jobs
