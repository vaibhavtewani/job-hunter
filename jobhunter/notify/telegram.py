"""Instant Telegram alerts for high-scoring jobs."""
from __future__ import annotations

import os
from html import escape
from typing import List

import httpx

from ..models import Job

REQUIRED_ENV = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
_MAX_MESSAGE = 3800  # Telegram's hard limit is 4096


def telegram_missing_env() -> List[str]:
    return [var for var in REQUIRED_ENV if not os.environ.get(var)]


def send_telegram(client: httpx.Client, jobs: List[Job]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    chunks, current = [], "<b>High-match jobs</b>"
    for job in jobs:
        where = ", ".join(part for part in (job.company, job.location) if part)
        line = '<b>%d</b> <a href="%s">%s</a>\n%s' % (job.score, escape(job.url, quote=True), escape(job.title), escape(where))
        if len(current) + len(line) + 2 > _MAX_MESSAGE:
            chunks.append(current)
            current = line
        else:
            current += "\n\n" + line
    chunks.append(current)
    for text in chunks:
        response = client.post(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        )
        response.raise_for_status()
