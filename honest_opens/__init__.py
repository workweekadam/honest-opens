"""
Honest Opens — Open-source bot filtering for newsletter engagement.

An ESP-agnostic algorithm for separating human opens and clicks from bot traffic.
Built by Workweek. Calibrated on Sailthru event data.

Usage:
    from honest_opens import HonestFilter
    hf = HonestFilter()
    results = hf.classify_sends(sends_df, open_events_df, click_events_df)
"""

__version__ = "1.0.0"

from honest_opens.classifier import HonestFilter
from honest_opens.models import SendResult, CampaignReport

__all__ = ["HonestFilter", "SendResult", "CampaignReport", "__version__"]
