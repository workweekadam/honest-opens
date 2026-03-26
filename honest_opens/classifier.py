"""
Honest Opens — Core Classification Engine (V3).

This is the main algorithm. It takes raw send, open, and click event data
from any ESP and classifies each subscriber-send pair as human or bot.

The algorithm was designed at Workweek and calibrated on Sailthru event data.
Thresholds may need adjustment for other ESPs — see docs/CALIBRATION.md.

V3 changes (measured against raw Sailthru is_real ground truth):
  - Removed HUMAN:thoughtful_multi (100% FP rate — delayed bot re-scans)
  - Removed HUMAN:single_moderate (100% FP rate — bots with slight delays)
  - Added ESP-rescue rules for BOT:high_volume, BOT:url_scanner, and
    UNCLASSIFIED:ambiguous when the ESP's own real/NHI flag disagrees
  - Added subscriber-history corroboration for borderline open rules
"""

from collections import defaultdict
from typing import List, Dict, Optional, Tuple
import statistics

from honest_opens.models import (
    SendRecord, OpenEvent, ClickEvent,
    SendResult, CampaignReport,
    OpenClassification, ClickClassification,
)
from honest_opens.thresholds import HonestConfig


class HonestFilter:
    """The main classifier. Instantiate once, feed it data, get honest metrics.

    Usage:
        hf = HonestFilter()  # Uses default strict thresholds
        results = hf.classify(sends, open_events, click_events)

    Or with a custom config:
        config = HonestConfig.load("my_thresholds.json")
        hf = HonestFilter(config=config)
    """

    def __init__(self, config: Optional[HonestConfig] = None):
        self.config = config or HonestConfig()
        self._user_history: Dict[str, dict] = {}

    # ─────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────

    def classify(
        self,
        sends: List[SendRecord],
        open_events: List[OpenEvent],
        click_events: List[ClickEvent],
        user_history: Optional[Dict[str, dict]] = None,
    ) -> List[SendResult]:
        """Classify all sends and return per-send results.

        Args:
            sends: List of SendRecord (one per subscriber per campaign).
            open_events: List of OpenEvent (all raw open-pixel fires).
            click_events: List of ClickEvent (all raw click events).
            user_history: Optional dict of {subscriber_id: {"verified_opens": int,
                          "total_sends": int}} for user-level history. If not
                          provided, history is built from the input data only.

        Returns:
            List of SendResult, one per input send.
        """
        if user_history:
            self._user_history = user_history

        # Index events by (subscriber_id, campaign_id)
        open_index = self._index_events(open_events, "open")
        click_index = self._index_events(click_events, "click")

        results = []
        for send in sends:
            key = (send.subscriber_id, send.campaign_id)
            send_opens = open_index.get(key, [])
            send_clicks = click_index.get(key, [])
            result = self._classify_send(send, send_opens, send_clicks)
            results.append(result)

        # Build user history from results for future calls
        self._update_user_history(results)

        return results

    def report(self, results: List[SendResult]) -> Dict[str, CampaignReport]:
        """Aggregate SendResults into per-campaign reports.

        Args:
            results: List of SendResult from classify().

        Returns:
            Dict of {campaign_id: CampaignReport}.
        """
        campaigns: Dict[str, list] = defaultdict(list)
        for r in results:
            campaigns[r.campaign_id].append(r)

        reports = {}
        for cid, send_results in campaigns.items():
            total = len(send_results)
            u_opens = sum(1 for r in send_results if r.unique_open)
            t_opens = sum(r.total_opens for r in send_results)
            u_clicks = sum(1 for r in send_results if r.unique_click)
            t_clicks = sum(r.total_clicks for r in send_results)
            raw_u_opens = sum(1 for r in send_results if r.raw_open_events > 0)
            raw_u_clicks = sum(1 for r in send_results if r.raw_click_events > 0)

            reports[cid] = CampaignReport(
                campaign_id=cid,
                total_sends=total,
                unique_opens=u_opens,
                total_open_events=t_opens,
                unique_clicks=u_clicks,
                total_click_events=t_clicks,
                open_rate=u_opens / total if total else 0.0,
                click_rate=u_clicks / total if total else 0.0,
                click_to_open_rate=u_clicks / u_opens if u_opens else 0.0,
                raw_unique_opens=raw_u_opens,
                raw_unique_clicks=raw_u_clicks,
                raw_open_rate=raw_u_opens / total if total else 0.0,
                raw_click_rate=raw_u_clicks / total if total else 0.0,
                bot_open_pct=(
                    (raw_u_opens - u_opens) / raw_u_opens if raw_u_opens else 0.0
                ),
                bot_click_pct=(
                    (raw_u_clicks - u_clicks) / raw_u_clicks if raw_u_clicks else 0.0
                ),
            )
        return reports

    # ─────────────────────────────────────────────────────────────────
    # INTERNAL: Per-send classification
    # ─────────────────────────────────────────────────────────────────

    def _classify_send(
        self,
        send: SendRecord,
        opens: List[OpenEvent],
        clicks: List[ClickEvent],
    ) -> SendResult:
        """Classify a single subscriber-send pair."""

        # Classify clicks first (open classification can use click result)
        click_cls = self._classify_clicks(send, clicks)

        # Classify opens (may reference click classification)
        open_cls = self._classify_opens(send, opens, click_cls)

        # Count human events
        human_opens = self._count_human_opens(send, opens, open_cls)
        human_clicks = self._count_human_clicks(send, clicks, click_cls)

        return SendResult(
            subscriber_id=send.subscriber_id,
            campaign_id=send.campaign_id,
            unique_open=open_cls.is_human,
            total_opens=human_opens,
            estimated_open=(
                open_cls.is_human
                or (
                    self.config.estimated_open_includes_uncertain
                    and open_cls.label == "UNCERTAIN:no_evidence"
                )
            ),
            open_classification=open_cls,
            unique_click=click_cls.is_human,
            total_clicks=human_clicks,
            click_classification=click_cls,
            raw_open_events=len(opens),
            raw_click_events=len(clicks),
        )

    # ─────────────────────────────────────────────────────────────────
    # OPEN CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────

    def _classify_opens(
        self,
        send: SendRecord,
        opens: List[OpenEvent],
        click_cls: ClickClassification,
    ) -> OpenClassification:
        """Classify opens for a single send. Rules fire in priority order."""

        if not opens:
            return OpenClassification(
                label="NONE:no_opens", confidence="definitive",
                is_human=False, probability=0,
            )

        ot = self.config.open_thresholds

        # Compute open features
        times = sorted(o.open_timestamp - send.send_timestamp for o in opens)
        first_open_sec = times[0] if times else None
        open_span_sec = times[-1] - times[0] if len(times) >= 2 else 0.0
        num_opens = len(opens)
        nhi_count = sum(1 for o in opens if o.is_nhi is True)
        real_count = sum(1 for o in opens if o.is_nhi is False)
        user_hist = self._user_history.get(send.subscriber_id, {})
        verified_history = user_hist.get("verified_opens", 0)
        rules = {}

        # ── RULE 1: Verified Clicker (definitive human) ──
        # If clicks on this send were classified as human, the open is real.
        if click_cls.is_human:
            rules["verified_clicker"] = True
            return OpenClassification(
                label="HUMAN:verified_clicker", confidence="definitive",
                is_human=True, probability=99, rule_details=rules,
            )

        # ── RULE 2: ESP Real Flag (high confidence human) ──
        # If the ESP explicitly flagged any open as "real" / non-bot.
        if real_count > 0:
            rules["esp_real_flag"] = True
            return OpenClassification(
                label="HUMAN:esp_confirmed", confidence="high",
                is_human=True, probability=85, rule_details=rules,
            )

        # ── RULE 3: Bot Instant Prefetch (high confidence bot) ──
        # All opens fired within seconds of send. Classic pre-fetch.
        if first_open_sec is not None and first_open_sec <= ot.bot_instant_max_seconds:
            if open_span_sec < 5.0 and num_opens <= 2:
                rules["bot_instant"] = True
                return OpenClassification(
                    label="BOT:instant_prefetch", confidence="high",
                    is_human=False, probability=5, rule_details=rules,
                )

        # ── RULE 4: Bot Click Session (medium confidence bot) ──
        # Open occurred during a session where clicks were classified as bot.
        if not click_cls.is_human and click_cls.label.startswith("BOT:"):
            if first_open_sec is not None and first_open_sec <= ot.bot_session_window_seconds:
                rules["bot_click_session"] = True
                return OpenClassification(
                    label="BOT:bot_click_session", confidence="medium",
                    is_human=False, probability=10, rule_details=rules,
                )

        # ── RULE 5: Apple Mail Double-Open (medium confidence human) ──
        # Exactly 2 opens with a gap. Apple MPP fires one, user fires one.
        if num_opens == ot.apple_double_exact_opens:
            if open_span_sec >= ot.apple_double_min_span_seconds:
                rules["apple_mail_double"] = True
                return OpenClassification(
                    label="HUMAN:apple_mail_double", confidence="medium",
                    is_human=True, probability=70, rule_details=rules,
                )

        # ── RULE 6: Multi-Open (medium confidence human) ──
        # 3+ opens spread over meaningful time. Bots don't re-read.
        if num_opens >= ot.multi_open_min_events:
            if open_span_sec >= ot.multi_open_min_span_seconds:
                rules["multi_open"] = True
                return OpenClassification(
                    label="HUMAN:multi_open", confidence="medium",
                    is_human=True, probability=75, rule_details=rules,
                )

        # ── RULE 7: Reopen Long Span (medium confidence human) ──
        # 2+ opens with a very long time span between first and last.
        if num_opens >= 2 and open_span_sec >= ot.reopen_min_span_seconds:
            rules["reopen_long_span"] = True
            return OpenClassification(
                label="HUMAN:reopen_long_span", confidence="medium",
                is_human=True, probability=72, rule_details=rules,
            )

        # ── RULE 8: Never Verified + Fast (medium confidence bot) ──
        # User has never had a verified open and this open is fast.
        total_hist = user_hist.get("total_sends", 0)
        if (
            total_hist >= ot.bot_never_verified_min_history
            and verified_history == 0
            and first_open_sec is not None
            and first_open_sec <= ot.bot_never_verified_max_seconds
        ):
            rules["never_verified_fast"] = True
            return OpenClassification(
                label="BOT:never_verified_fast", confidence="medium",
                is_human=False, probability=15, rule_details=rules,
            )

        # ── FALLBACK: Uncertain / No Evidence ──
        # Single open, no corroborating signals. The Apple Mail gray zone.
        rules["no_evidence"] = True
        return OpenClassification(
            label="UNCERTAIN:no_evidence", confidence="low",
            is_human=False, probability=40, rule_details=rules,
        )

    # ─────────────────────────────────────────────────────────────────
    # CLICK CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────

    def _classify_clicks(
        self,
        send: SendRecord,
        clicks: List[ClickEvent],
    ) -> ClickClassification:
        """Classify clicks for a single send. Rules fire in priority order.

        V3 changes:
          - Removed HUMAN:thoughtful_multi (100% FP vs Sailthru ground truth)
          - Removed HUMAN:single_moderate (100% FP vs Sailthru ground truth)
          - Added ESP-rescue rules after bot rules for high_volume, url_scanner,
            and ambiguous sends where the ESP's real/NHI flag disagrees
        """

        if not clicks:
            return ClickClassification(
                label="NONE:no_clicks", confidence="definitive",
                is_human=False, probability=0,
            )

        ct = self.config.click_thresholds

        # Compute click features
        times = sorted(c.click_timestamp - send.send_timestamp for c in clicks)
        first_click_sec = times[0] if times else None
        click_span_sec = times[-1] - times[0] if len(times) >= 2 else 0.0
        num_clicks = len(clicks)
        unique_urls = len(set(c.url for c in clicks if c.url)) or num_clicks
        real_count = sum(1 for c in clicks if c.is_nhi is False)
        nhi_count = sum(1 for c in clicks if c.is_nhi is True)

        # Inter-click timing
        inter_clicks = []
        if len(times) >= 2:
            inter_clicks = [times[i+1] - times[i] for i in range(len(times) - 1)]
        avg_inter_click = (
            statistics.mean(inter_clicks) if inter_clicks else None
        )

        rules = {}

        # ── BOT RULES (checked first — reject bots before accepting humans) ──

        # ── RULE 1: Instant Prefetch (definitive bot) ──
        if first_click_sec is not None and first_click_sec <= ct.bot_instant_definitive_max_seconds:
            rules["bot_instant_definitive"] = True
            return ClickClassification(
                label="BOT:instant_prefetch", confidence="definitive",
                is_human=False, probability=1, rule_details=rules,
            )

        # ── RULE 2: Instant Likely (high confidence bot) ──
        if first_click_sec is not None and first_click_sec <= ct.bot_instant_likely_max_seconds:
            rules["bot_instant_likely"] = True
            return ClickClassification(
                label="BOT:instant_likely", confidence="high",
                is_human=False, probability=3, rule_details=rules,
            )

        # ── RULE 3: Machinegun Definitive (definitive bot) ──
        if (
            avg_inter_click is not None
            and avg_inter_click <= ct.bot_machinegun_definitive_max_inter_click
            and unique_urls >= ct.bot_machinegun_min_urls
        ):
            rules["bot_machinegun_definitive"] = True
            return ClickClassification(
                label="BOT:machinegun", confidence="definitive",
                is_human=False, probability=1, rule_details=rules,
            )

        # ── RULE 4: Machinegun Likely (high confidence bot) ──
        if (
            avg_inter_click is not None
            and avg_inter_click <= ct.bot_machinegun_likely_max_inter_click
            and unique_urls >= ct.bot_machinegun_min_urls
        ):
            # V3 ESP rescue: if ESP says real AND late timing AND few URLs,
            # this might be a human who clicked quickly between 2 links.
            if (
                real_count > 0
                and first_click_sec is not None
                and first_click_sec >= ct.esp_rescue_min_seconds
                and unique_urls <= 2
            ):
                rules["esp_rescue_machinegun_likely"] = True
                return ClickClassification(
                    label="HUMAN:esp_rescued", confidence="medium",
                    is_human=True, probability=65, rule_details=rules,
                )
            rules["bot_machinegun_likely"] = True
            return ClickClassification(
                label="BOT:machinegun_likely", confidence="high",
                is_human=False, probability=5, rule_details=rules,
            )

        # ── RULE 5: URL Scanner (high confidence bot) ──
        if (
            unique_urls >= ct.bot_scanner_min_urls
            and num_clicks >= ct.bot_scanner_min_total_clicks
        ):
            # V3 ESP rescue: if ESP says some clicks are real AND late timing
            # AND slower inter-click, this is a real human whose clicks were
            # mixed with bot scanner clicks.
            if (
                real_count > 0
                and first_click_sec is not None
                and first_click_sec >= ct.esp_rescue_min_seconds
                and avg_inter_click is not None
                and avg_inter_click >= ct.esp_rescue_scanner_min_inter_click
            ):
                rules["esp_rescue_url_scanner"] = True
                return ClickClassification(
                    label="HUMAN:esp_rescued", confidence="medium",
                    is_human=True, probability=68, rule_details=rules,
                )
            rules["bot_url_scanner"] = True
            return ClickClassification(
                label="BOT:url_scanner", confidence="high",
                is_human=False, probability=5, rule_details=rules,
            )

        # ── RULE 6: High Volume (high confidence bot) ──
        if num_clicks >= ct.bot_volume_min_total_clicks:
            # V3 ESP rescue: if ESP says real AND late timing, this is a
            # real human who clicked many links in a long newsletter.
            if (
                real_count > 0
                and first_click_sec is not None
                and first_click_sec >= ct.esp_rescue_min_seconds
            ):
                rules["esp_rescue_high_volume"] = True
                return ClickClassification(
                    label="HUMAN:esp_rescued", confidence="medium",
                    is_human=True, probability=70, rule_details=rules,
                )
            # V3 timing-only rescue: very late + moderate click count
            # (no ESP flag needed). Calibrated on Sailthru data where
            # high_volume sends with >1hr delay and <=15 clicks had
            # 45.5% human rate per ESP ground truth.
            if (
                first_click_sec is not None
                and first_click_sec >= ct.esp_rescue_high_volume_late_seconds
                and num_clicks <= ct.esp_rescue_high_volume_max_clicks
            ):
                rules["timing_rescue_high_volume"] = True
                return ClickClassification(
                    label="HUMAN:timing_rescued", confidence="low",
                    is_human=True, probability=55, rule_details=rules,
                )
            rules["bot_high_volume"] = True
            return ClickClassification(
                label="BOT:high_volume", confidence="high",
                is_human=False, probability=8, rule_details=rules,
            )

        # ── RULE 7: Cron Burst (high confidence bot) ──
        if (
            avg_inter_click is not None
            and avg_inter_click <= ct.bot_cron_max_inter_click
            and first_click_sec is not None
            and first_click_sec <= ct.bot_cron_max_time_after_send
            and unique_urls >= ct.bot_cron_min_urls
        ):
            # V3 ESP rescue: if ESP says real AND very late timing
            if (
                real_count > 0
                and first_click_sec >= ct.esp_rescue_high_volume_late_seconds
            ):
                rules["esp_rescue_cron_burst"] = True
                return ClickClassification(
                    label="HUMAN:esp_rescued", confidence="low",
                    is_human=True, probability=60, rule_details=rules,
                )
            rules["bot_cron_burst"] = True
            return ClickClassification(
                label="BOT:cron_burst", confidence="high",
                is_human=False, probability=8, rule_details=rules,
            )

        # ── HUMAN RULES ──

        # ── RULE 8: ESP Confirmed Human ──
        if real_count > 0:
            rules["esp_confirmed"] = True
            return ClickClassification(
                label="HUMAN:esp_confirmed", confidence="high",
                is_human=True, probability=88, rule_details=rules,
            )

        # ── RULE 9: Delayed Single (definitive human) ──
        # One link clicked, significant delay. The classic reader pattern.
        if (
            unique_urls <= ct.human_delayed_max_urls
            and first_click_sec is not None
            and first_click_sec >= ct.human_delayed_min_seconds
        ):
            rules["human_delayed_single"] = True
            return ClickClassification(
                label="HUMAN:delayed_single", confidence="definitive",
                is_human=True, probability=95, rule_details=rules,
            )

        # ── RULE 10: Late Arrival (high confidence human) ──
        # Click many hours after send.
        if first_click_sec is not None and first_click_sec >= ct.human_late_min_seconds:
            rules["human_late_arrival"] = True
            return ClickClassification(
                label="HUMAN:late_arrival", confidence="high",
                is_human=True, probability=90, rule_details=rules,
            )

        # ── RULE 11: Single Selective (high confidence human) ──
        # One link, moderate timing.
        if (
            unique_urls <= ct.human_selective_max_urls
            and first_click_sec is not None
            and ct.human_selective_min_seconds <= first_click_sec <= ct.human_selective_max_seconds
        ):
            rules["human_single_selective"] = True
            return ClickClassification(
                label="HUMAN:single_selective", confidence="high",
                is_human=True, probability=85, rule_details=rules,
            )

        # ── RULE 12 (V3): Ambiguous with ESP rescue ──
        # If nothing matched above and ESP says real + late timing,
        # rescue as human.
        if (
            real_count > 0
            and first_click_sec is not None
            and first_click_sec >= ct.esp_rescue_min_seconds
        ):
            rules["esp_rescue_ambiguous"] = True
            return ClickClassification(
                label="HUMAN:esp_rescued", confidence="low",
                is_human=True, probability=55, rule_details=rules,
            )

        # ── RULE 13 (V3): Ambiguous with very late timing ──
        # Single URL click, very late, no ESP flag. Probably human.
        if (
            first_click_sec is not None
            and first_click_sec >= ct.esp_rescue_high_volume_late_seconds
            and unique_urls == 1
        ):
            rules["timing_rescue_ambiguous"] = True
            return ClickClassification(
                label="HUMAN:timing_rescued", confidence="low",
                is_human=True, probability=55, rule_details=rules,
            )

        # ── FALLBACK: Ambiguous ──
        # V3: Previously this was the catch-all. Now fewer sends reach here
        # because the ESP-rescue and timing-rescue rules above capture
        # borderline cases.
        rules["ambiguous"] = True
        return ClickClassification(
            label="UNCLASSIFIED:ambiguous", confidence="low",
            is_human=False, probability=30, rule_details=rules,
        )

    # ─────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _count_human_opens(
        self, send: SendRecord, opens: List[OpenEvent],
        cls: OpenClassification,
    ) -> int:
        """Count open events that pass human filters."""
        if not cls.is_human:
            return 0
        # For human-classified sends, count opens that aren't instant prefetches
        ot = self.config.open_thresholds
        count = 0
        for o in opens:
            delta = o.open_timestamp - send.send_timestamp
            if delta > ot.bot_instant_max_seconds:
                count += 1
            elif o.is_nhi is False:  # ESP says it's real
                count += 1
        return max(count, 1) if cls.is_human else 0

    def _count_human_clicks(
        self, send: SendRecord, clicks: List[ClickEvent],
        cls: ClickClassification,
    ) -> int:
        """Count click events that pass human filters."""
        if not cls.is_human:
            return 0
        ct = self.config.click_thresholds
        count = 0
        for c in clicks:
            delta = c.click_timestamp - send.send_timestamp
            if delta > ct.bot_instant_likely_max_seconds:
                count += 1
            elif c.is_nhi is False:
                count += 1
        return max(count, 1) if cls.is_human else 0

    def _index_events(self, events, event_type: str) -> dict:
        """Index events by (subscriber_id, campaign_id)."""
        index = defaultdict(list)
        for e in events:
            key = (e.subscriber_id, e.campaign_id)
            index[key].append(e)
        return dict(index)

    def _update_user_history(self, results: List[SendResult]) -> None:
        """Update internal user history from classification results."""
        for r in results:
            uid = r.subscriber_id
            if uid not in self._user_history:
                self._user_history[uid] = {"verified_opens": 0, "total_sends": 0}
            self._user_history[uid]["total_sends"] += 1
            if r.open_classification.is_human:
                self._user_history[uid]["verified_opens"] += 1
