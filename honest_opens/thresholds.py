"""
Default thresholds for the Honest Opens classifier (V3).

These thresholds were calibrated on Sailthru event data processing ~10M sends/month
across 10 newsletters. V3 was validated against raw Sailthru is_real ground truth
across 700K+ click sends and 9M+ open sends.

Measured performance (V3, Sailthru ground truth):
  Clicks: FP ~5.6%, FN ~8.6% (with ESP real flag)
  Clicks: FP ~6.4%, FN ~10.6% (without ESP real flag)
  Opens:  FP ~3% (estimated), FN ~7%

IMPORTANT: These thresholds may need adjustment for your ESP. Different platforms
have different timestamp granularity, event batching behavior, and pre-processing
pipelines that can shift optimal values. See docs/CALIBRATION.md for guidance.

All time values are in seconds unless otherwise noted.
"""

from dataclasses import dataclass, field
from typing import Optional
import json
import os


@dataclass
class OpenThresholds:
    """Thresholds for open classification rules."""

    # BOT: instant_prefetch — open fires within seconds of send
    # Sailthru bots cluster at 7-9s. Conservative threshold catches most.
    bot_instant_max_seconds: float = 10.0

    # BOT: bot_click_session — open during a session with bot clicks
    # No timing threshold; this rule fires when click_classification is BOT
    # and an open occurred in the same session window.
    bot_session_window_seconds: float = 120.0

    # BOT: never_verified_fast — no lifetime verified opens + fast open
    # Users who have NEVER had a corroborated open and open quickly.
    bot_never_verified_max_seconds: float = 30.0
    bot_never_verified_min_history: int = 5  # Min sends before applying this rule

    # HUMAN: apple_mail_double — exactly 2 opens, specific pattern
    # Apple Mail Privacy fires 1 NHI open, then user fires 1 real open.
    apple_double_exact_opens: int = 2
    apple_double_min_span_seconds: float = 5.0  # Min gap between the two opens

    # HUMAN: multi_open — 3+ opens with meaningful time gaps
    multi_open_min_events: int = 3
    multi_open_min_span_seconds: float = 300.0  # 5 minutes between first and last

    # HUMAN: reopen_long_span — 2+ opens with very long span
    # Median span for this rule is ~25 hours. Threshold at 4 hours.
    reopen_min_span_seconds: float = 14400.0  # 4 hours


@dataclass
class ClickThresholds:
    """Thresholds for click classification rules."""

    # BOT: instant_prefetch — click within seconds of send
    # Enterprise security tools (Barracuda, Mimecast, Proofpoint) pre-click.
    bot_instant_definitive_max_seconds: float = 5.0
    bot_instant_likely_max_seconds: float = 10.0

    # BOT: machinegun — all links clicked in rapid succession
    # Security scanners click every link. Median inter-click: 0.125s.
    bot_machinegun_definitive_max_inter_click: float = 0.5
    bot_machinegun_likely_max_inter_click: float = 1.0
    bot_machinegun_min_urls: int = 3  # Must click 3+ distinct URLs

    # BOT: url_scanner — many URLs clicked, high total volume
    bot_scanner_min_urls: int = 5
    bot_scanner_min_total_clicks: int = 10

    # BOT: high_volume — abnormally high click count
    bot_volume_min_total_clicks: int = 10

    # BOT: cron_burst — clicks in a tight, regular burst
    bot_cron_max_inter_click: float = 10.0
    bot_cron_max_time_after_send: float = 120.0
    bot_cron_min_urls: int = 2

    # HUMAN: delayed_single — one click, significant delay
    human_delayed_min_seconds: float = 300.0  # 5 minutes
    human_delayed_max_urls: int = 1

    # HUMAN: late_arrival — click many hours after send
    human_late_min_seconds: float = 14400.0  # 4 hours

    # HUMAN: single_selective — one click, moderate timing
    human_selective_min_seconds: float = 120.0  # 2 minutes
    human_selective_max_seconds: float = 3600.0  # 1 hour
    human_selective_max_urls: int = 1

    # V3 ESP-rescue thresholds
    # When a bot rule fires but the ESP's own real/NHI flag disagrees,
    # these thresholds determine whether to rescue the send as human.
    # Calibrated on Sailthru data: rescuing with ESP real + late timing
    # recovered ~9K false negatives while adding only ~200 false positives.
    esp_rescue_min_seconds: float = 300.0  # 5 min — minimum delay for rescue
    esp_rescue_scanner_min_inter_click: float = 20.0  # For url_scanner rescue
    esp_rescue_high_volume_late_seconds: float = 3600.0  # 1 hour for timing-only rescue
    esp_rescue_high_volume_max_clicks: int = 15  # Max clicks for timing-only rescue


@dataclass
class HonestConfig:
    """Complete configuration for the Honest Opens classifier.

    You can use the defaults (calibrated on Sailthru data) or customize
    thresholds for your ESP. Save/load configs as JSON.

    V3 measured performance (Sailthru ground truth):
      Clicks: FP ~5.6%, FN ~8.6% (with ESP real flag)
      Opens:  FP ~3% (estimated), FN ~7%
    """
    open_thresholds: OpenThresholds = field(default_factory=OpenThresholds)
    click_thresholds: ClickThresholds = field(default_factory=ClickThresholds)

    # Global settings
    min_sends_for_user_history: int = 3  # Min sends before using user history
    estimated_open_includes_uncertain: bool = True  # Include gray-zone opens

    def save(self, path: str) -> None:
        """Save configuration to a JSON file."""
        data = {
            "open_thresholds": self.open_thresholds.__dict__,
            "click_thresholds": self.click_thresholds.__dict__,
            "min_sends_for_user_history": self.min_sends_for_user_history,
            "estimated_open_includes_uncertain": self.estimated_open_includes_uncertain,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "HonestConfig":
        """Load configuration from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        config = cls()
        if "open_thresholds" in data:
            for k, v in data["open_thresholds"].items():
                setattr(config.open_thresholds, k, v)
        if "click_thresholds" in data:
            for k, v in data["click_thresholds"].items():
                setattr(config.click_thresholds, k, v)
        if "min_sends_for_user_history" in data:
            config.min_sends_for_user_history = data["min_sends_for_user_history"]
        if "estimated_open_includes_uncertain" in data:
            config.estimated_open_includes_uncertain = data["estimated_open_includes_uncertain"]
        return config


# Pre-built profiles for common use cases
PROFILES = {
    "strict": {
        "description": "Strict filtering. ~3-6% FP rate. Best for ad-supported publishers who need defensible numbers.",
        "config": HonestConfig,  # Default thresholds
    },
    "moderate": {
        "description": "Moderate filtering. ~10% FP rate. Balanced for general reporting.",
        "config": lambda: _moderate_config(),
    },
    "permissive": {
        "description": "Permissive filtering. ~20% FP rate. Only filters obvious bots.",
        "config": lambda: _permissive_config(),
    },
}


def _moderate_config() -> HonestConfig:
    config = HonestConfig()
    config.open_thresholds.bot_instant_max_seconds = 5.0
    config.open_thresholds.reopen_min_span_seconds = 7200.0  # 2 hours
    config.click_thresholds.bot_instant_likely_max_seconds = 5.0
    config.click_thresholds.bot_machinegun_likely_max_inter_click = 0.5
    config.click_thresholds.human_delayed_min_seconds = 120.0
    return config


def _permissive_config() -> HonestConfig:
    config = HonestConfig()
    config.open_thresholds.bot_instant_max_seconds = 3.0
    config.open_thresholds.reopen_min_span_seconds = 3600.0  # 1 hour
    config.click_thresholds.bot_instant_definitive_max_seconds = 2.0
    config.click_thresholds.bot_instant_likely_max_seconds = 3.0
    config.click_thresholds.bot_machinegun_definitive_max_inter_click = 0.25
    config.click_thresholds.bot_machinegun_likely_max_inter_click = 0.5
    config.click_thresholds.bot_machinegun_min_urls = 5
    config.click_thresholds.human_delayed_min_seconds = 60.0
    return config
