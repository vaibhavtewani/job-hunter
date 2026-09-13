"""Source adapters. The order of SOURCE_CLASSES is the dedup priority: direct employer systems win."""
from .ashby import AshbySource
from .base import Source, SourceContext
from .gmail_alerts import GmailAlertsSource
from .greenhouse import GreenhouseSource
from .lever import LeverSource
from .serpapi import SerpApiSource
from .smartrecruiters import SmartRecruitersSource
from .workday import WorkdaySource

SOURCE_CLASSES = [
    GreenhouseSource,
    LeverSource,
    AshbySource,
    SmartRecruitersSource,
    WorkdaySource,
    SerpApiSource,
    GmailAlertsSource,
]
REGISTRY = {cls.name: cls for cls in SOURCE_CLASSES}
SOURCE_PRIORITY = {cls.name: rank for rank, cls in enumerate(SOURCE_CLASSES)}

__all__ = ["REGISTRY", "SOURCE_CLASSES", "SOURCE_PRIORITY", "Source", "SourceContext"]
