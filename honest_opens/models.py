"""
Data models for Honest Opens.

Defines the input schema (what publishers need from their ESP) and
output schema (what the classifier produces).
"""

from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────
# INPUT MODELS — What you feed in
# ─────────────────────────────────────────────────────────────────────

@dataclass
class SendRecord:
    """One row per subscriber per email send.

    This is the minimum data you need from your ESP. Every ESP tracks this.
    """
    subscriber_id: str          # Your ESP's unique subscriber identifier
    campaign_id: str            # The email send / blast / campaign ID
    send_timestamp: float       # Unix epoch seconds when the email was sent


@dataclass
class OpenEvent:
    """One row per open-pixel fire.

    Most ESPs record multiple open events per send. You need ALL of them,
    not just the deduplicated "unique open" flag your ESP shows you.
    """
    subscriber_id: str          # Must match SendRecord.subscriber_id
    campaign_id: str            # Must match SendRecord.campaign_id
    open_timestamp: float       # Unix epoch seconds when the open was recorded
    is_nhi: Optional[bool] = None  # If your ESP flags non-human interaction (e.g., Sailthru)
    user_agent: Optional[str] = None  # Raw User-Agent string if available


@dataclass
class ClickEvent:
    """One row per click event.

    You need every individual click, not just unique clicks. Include the URL
    so the algorithm can count distinct URLs clicked per send.
    """
    subscriber_id: str          # Must match SendRecord.subscriber_id
    campaign_id: str            # Must match SendRecord.campaign_id
    click_timestamp: float      # Unix epoch seconds when the click was recorded
    url: Optional[str] = None   # The clicked URL (used for distinct-URL counting)
    is_nhi: Optional[bool] = None  # If your ESP flags non-human interaction


# ─────────────────────────────────────────────────────────────────────
# OUTPUT MODELS — What you get back
# ─────────────────────────────────────────────────────────────────────

@dataclass
class OpenClassification:
    """Classification result for opens on a single send."""
    label: str                  # e.g., "HUMAN:verified_clicker", "BOT:instant_prefetch"
    confidence: str             # "definitive", "high", "medium", "low"
    is_human: bool              # The binary verdict
    probability: int            # 0-100 score
    rule_details: dict = field(default_factory=dict)  # Which rules fired


@dataclass
class ClickClassification:
    """Classification result for clicks on a single send."""
    label: str                  # e.g., "HUMAN:delayed_single", "BOT:machinegun"
    confidence: str             # "definitive", "high", "medium", "low"
    is_human: bool              # The binary verdict
    probability: int            # 0-100 score
    rule_details: dict = field(default_factory=dict)  # Which rules fired


@dataclass
class SendResult:
    """Complete classification for one subscriber + one campaign send.

    This is the primary output. One SendResult per (subscriber_id, campaign_id) pair.
    """
    subscriber_id: str
    campaign_id: str

    # Opens
    unique_open: bool           # TRUE = human open (use for open rate)
    total_opens: int            # Count of open events classified as human
    estimated_open: bool        # More generous — includes uncertain-but-likely opens
    open_classification: OpenClassification

    # Clicks
    unique_click: bool          # TRUE = human click (use for CTR)
    total_clicks: int           # Count of click events classified as human
    click_classification: ClickClassification

    # Raw counts (for comparison)
    raw_open_events: int        # Total open-pixel fires before filtering
    raw_click_events: int       # Total click events before filtering


@dataclass
class CampaignReport:
    """Aggregate metrics for a single campaign / email send.

    Roll up SendResults to get campaign-level open and click rates.
    """
    campaign_id: str
    total_sends: int
    unique_opens: int           # Count of sends with unique_open = True
    total_open_events: int      # Sum of human open events
    unique_clicks: int          # Count of sends with unique_click = True
    total_click_events: int     # Sum of human click events
    open_rate: float            # unique_opens / total_sends
    click_rate: float           # unique_clicks / total_sends
    click_to_open_rate: float   # unique_clicks / unique_opens

    # Raw comparison
    raw_unique_opens: int       # Sends with any open signal
    raw_unique_clicks: int      # Sends with any click signal
    raw_open_rate: float
    raw_click_rate: float
    bot_open_pct: float         # % of raw opens filtered as bot
    bot_click_pct: float        # % of raw clicks filtered as bot
