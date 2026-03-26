"""
Benchmarking and validation module for Honest Opens (V3).

Provides two modes of error rate estimation:

  1. PROXY MODE (no ground truth needed):
     Uses internal heuristics — e.g., human clicks with low probability as FP
     proxies, bot opens with human clicks as FN proxies. This is what you get
     if you don't have raw ESP is_real/NHI flags.

  2. GROUND TRUTH MODE (requires ESP is_real flag):
     Builds a proper confusion matrix using your ESP's real/NHI classification
     as ground truth. This is how V3 was validated against Sailthru data.

     IMPORTANT CAVEAT: ESP ground truth is imperfect. Sailthru's is_real flag
     misclassifies Apple Mail Privacy Protection users as NHI (non-human
     interaction). Our pattern rules (apple_mail_double, multi_open,
     reopen_long_span) are designed to catch these users. So the "FP rate"
     measured against ESP ground truth overstates the true FP rate for opens.
     For clicks, ESP ground truth is much more reliable.

V3 measured performance (Sailthru ground truth, 90-day window, 700K+ click sends):
  Clicks: FP ~5.6%, FN ~8.6% (with ESP real flag available)
  Clicks: FP ~6.4%, FN ~10.6% (without ESP real flag)
  Opens:  FP ~0.5% (ESP-confirmed rules only), FN ~7%
  Opens:  FP ~3% (estimated, including pattern rules for Apple Mail)
"""

from collections import defaultdict
from typing import List, Dict, Optional
from honest_opens.models import SendResult, CampaignReport


class BenchmarkReport:
    """Diagnostic report comparing Honest Opens output to raw ESP signals."""

    def __init__(self):
        self.total_sends: int = 0

        # Opens
        self.raw_opens: int = 0
        self.human_opens: int = 0
        self.estimated_opens: int = 0
        self.bot_opens: int = 0

        # Clicks
        self.raw_clicks: int = 0
        self.human_clicks: int = 0
        self.bot_clicks: int = 0

        # Classification distribution
        self.open_labels: Dict[str, int] = defaultdict(int)
        self.click_labels: Dict[str, int] = defaultdict(int)
        self.open_confidence: Dict[str, int] = defaultdict(int)
        self.click_confidence: Dict[str, int] = defaultdict(int)

        # FP/FN proxies (proxy mode)
        self.open_fp_proxy: int = 0
        self.open_fn_proxy: int = 0
        self.click_fp_proxy: int = 0
        self.click_fn_proxy: int = 0

    @property
    def open_rate_raw(self) -> float:
        return self.raw_opens / self.total_sends if self.total_sends else 0.0

    @property
    def open_rate_filtered(self) -> float:
        return self.human_opens / self.total_sends if self.total_sends else 0.0

    @property
    def open_rate_estimated(self) -> float:
        return self.estimated_opens / self.total_sends if self.total_sends else 0.0

    @property
    def click_rate_raw(self) -> float:
        return self.raw_clicks / self.total_sends if self.total_sends else 0.0

    @property
    def click_rate_filtered(self) -> float:
        return self.human_clicks / self.total_sends if self.total_sends else 0.0

    @property
    def open_fp_rate(self) -> float:
        return self.open_fp_proxy / self.human_opens if self.human_opens else 0.0

    @property
    def open_fn_rate(self) -> float:
        return self.open_fn_proxy / self.bot_opens if self.bot_opens else 0.0

    @property
    def click_fp_rate(self) -> float:
        return self.click_fp_proxy / self.human_clicks if self.human_clicks else 0.0

    @property
    def click_fn_rate(self) -> float:
        return self.click_fn_proxy / self.bot_clicks if self.bot_clicks else 0.0

    @property
    def bot_open_pct(self) -> float:
        return self.bot_opens / self.raw_opens if self.raw_opens else 0.0

    @property
    def bot_click_pct(self) -> float:
        return self.bot_clicks / self.raw_clicks if self.raw_clicks else 0.0

    def summary(self) -> str:
        """Return a human-readable summary of the benchmark."""
        lines = [
            "=" * 70,
            "HONEST OPENS V3 — BENCHMARK REPORT",
            "=" * 70,
            "",
            f"Total sends analyzed: {self.total_sends:,}",
            "",
            "── OPENS ──",
            f"  Raw opens (any signal):     {self.raw_opens:,}  ({self.open_rate_raw:.1%})",
            f"  Human opens (strict):       {self.human_opens:,}  ({self.open_rate_filtered:.1%})",
            f"  Estimated opens (generous):  {self.estimated_opens:,}  ({self.open_rate_estimated:.1%})",
            f"  Bot opens filtered:         {self.bot_opens:,}  ({self.bot_open_pct:.1%} of raw)",
            "",
            "── CLICKS ──",
            f"  Raw clicks (any signal):    {self.raw_clicks:,}  ({self.click_rate_raw:.1%})",
            f"  Human clicks (strict):      {self.human_clicks:,}  ({self.click_rate_filtered:.1%})",
            f"  Bot clicks filtered:        {self.bot_clicks:,}  ({self.bot_click_pct:.1%} of raw)",
            "",
            "── ERROR RATE ESTIMATES (proxy-based) ──",
            f"  Open FP rate (bot counted as human):   ~{self.open_fp_rate:.1%}",
            f"  Open FN rate (human counted as bot):   ~{self.open_fn_rate:.1%}",
            f"  Click FP rate (bot counted as human):  ~{self.click_fp_rate:.1%}",
            f"  Click FN rate (human counted as bot):  ~{self.click_fn_rate:.1%}",
            "",
            "  Note: These are proxy estimates. For ground-truth measurement,",
            "  use confusion_matrix() with your ESP's is_real/NHI flags.",
            "",
            "── OPEN CLASSIFICATION DISTRIBUTION ──",
        ]
        for label, count in sorted(
            self.open_labels.items(), key=lambda x: -x[1]
        ):
            pct = count / self.total_sends if self.total_sends else 0
            lines.append(f"  {label:40s} {count:>8,}  ({pct:.1%})")

        lines.append("")
        lines.append("── CLICK CLASSIFICATION DISTRIBUTION ──")
        for label, count in sorted(
            self.click_labels.items(), key=lambda x: -x[1]
        ):
            pct = count / self.raw_clicks if self.raw_clicks else 0
            lines.append(f"  {label:40s} {count:>8,}  ({pct:.1%})")

        lines.extend(["", "=" * 70])
        return "\n".join(lines)


class ConfusionMatrix:
    """Proper confusion matrix for opens or clicks.

    Compares Honest Opens classification to ESP ground truth (is_real flag).
    """

    def __init__(self, metric_type: str = "clicks"):
        self.metric_type = metric_type
        self.tp: int = 0  # Honest says human, ESP says real
        self.fp: int = 0  # Honest says human, ESP says NHI
        self.fn: int = 0  # Honest says bot, ESP says real
        self.tn: int = 0  # Honest says bot, ESP says NHI

        # Per-rule breakdown
        self.fp_by_rule: Dict[str, int] = defaultdict(int)
        self.fn_by_rule: Dict[str, int] = defaultdict(int)
        self.tp_by_rule: Dict[str, int] = defaultdict(int)
        self.tn_by_rule: Dict[str, int] = defaultdict(int)

    @property
    def total(self) -> int:
        return self.tp + self.fp + self.fn + self.tn

    @property
    def fp_rate(self) -> float:
        """FP / (TP + FP) — what % of human classifications are wrong."""
        denom = self.tp + self.fp
        return self.fp / denom if denom else 0.0

    @property
    def fn_rate(self) -> float:
        """FN / (TP + FN) — what % of real signals did we miss."""
        denom = self.tp + self.fn
        return self.fn / denom if denom else 0.0

    @property
    def precision(self) -> float:
        """TP / (TP + FP)"""
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        """TP / (TP + FN)"""
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    @property
    def accuracy(self) -> float:
        return (self.tp + self.tn) / self.total if self.total else 0.0

    def summary(self) -> str:
        lines = [
            f"── CONFUSION MATRIX: {self.metric_type.upper()} ──",
            f"  (Honest Opens vs ESP ground truth)",
            "",
            f"                    ESP says REAL    ESP says NHI",
            f"  Honest: HUMAN     TP: {self.tp:>8,}     FP: {self.fp:>8,}",
            f"  Honest: BOT       FN: {self.fn:>8,}     TN: {self.tn:>8,}",
            "",
            f"  FP rate (bot counted as human):  {self.fp_rate:.1%}",
            f"  FN rate (human counted as bot):  {self.fn_rate:.1%}",
            f"  Precision:                       {self.precision:.1%}",
            f"  Recall:                          {self.recall:.1%}",
            f"  F1 Score:                        {self.f1:.3f}",
            f"  Accuracy:                        {self.accuracy:.1%}",
            "",
        ]

        if self.fp_by_rule:
            lines.append("  Top FP sources (rules letting bots through):")
            for rule, count in sorted(self.fp_by_rule.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"    {rule:40s} {count:>6,}")

        if self.fn_by_rule:
            lines.append("")
            lines.append("  Top FN sources (rules blocking humans):")
            for rule, count in sorted(self.fn_by_rule.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"    {rule:40s} {count:>6,}")

        return "\n".join(lines)


def benchmark(results: List[SendResult]) -> BenchmarkReport:
    """Generate a benchmark report from classification results (proxy mode).

    Args:
        results: List of SendResult from HonestFilter.classify().

    Returns:
        BenchmarkReport with aggregate metrics and proxy error rate estimates.
    """
    report = BenchmarkReport()
    report.total_sends = len(results)

    for r in results:
        # Opens
        if r.raw_open_events > 0:
            report.raw_opens += 1
        if r.unique_open:
            report.human_opens += 1
        elif r.raw_open_events > 0:
            report.bot_opens += 1
        if r.estimated_open:
            report.estimated_opens += 1

        # Clicks
        if r.raw_click_events > 0:
            report.raw_clicks += 1
        if r.unique_click:
            report.human_clicks += 1
        elif r.raw_click_events > 0:
            report.bot_clicks += 1

        # Classification labels
        if r.raw_open_events > 0:
            report.open_labels[r.open_classification.label] += 1
            report.open_confidence[r.open_classification.confidence] += 1
        if r.raw_click_events > 0:
            report.click_labels[r.click_classification.label] += 1
            report.click_confidence[r.click_classification.confidence] += 1

        # FP proxy: human open but probability is low
        if r.unique_open and r.open_classification.probability < 60:
            report.open_fp_proxy += 1

        # FN proxy: bot open but had a human click
        if (
            not r.unique_open
            and r.raw_open_events > 0
            and r.unique_click
        ):
            report.open_fn_proxy += 1

        # Click FP proxy: human click with low probability
        if r.unique_click and r.click_classification.probability < 60:
            report.click_fp_proxy += 1

        # Click FN proxy: bot click but probability > 20 (borderline)
        if (
            not r.unique_click
            and r.raw_click_events > 0
            and r.click_classification.probability > 20
        ):
            report.click_fn_proxy += 1

    return report


def confusion_matrix(
    results: List[SendResult],
    esp_is_real: Dict[str, bool],
    metric: str = "clicks",
) -> ConfusionMatrix:
    """Build a proper confusion matrix using ESP ground truth.

    This is the gold-standard validation method. It compares Honest Opens'
    classification to your ESP's is_real/NHI flag for each send.

    Args:
        results: List of SendResult from HonestFilter.classify().
        esp_is_real: Dict of {f"{subscriber_id}:{campaign_id}": bool}
                     where True = ESP says at least one event was "real"
                     (non-bot). Build this from your raw event data by
                     checking if any open/click event has is_nhi=False.
        metric: "clicks" or "opens" — which metric to evaluate.

    Returns:
        ConfusionMatrix with TP/FP/FN/TN counts and per-rule breakdown.

    Example:
        # Build esp_is_real from raw events
        esp_real = {}
        for event in raw_click_events:
            key = f"{event.subscriber_id}:{event.campaign_id}"
            if event.is_nhi is False:
                esp_real[key] = True
            elif key not in esp_real:
                esp_real[key] = False

        cm = confusion_matrix(results, esp_real, metric="clicks")
        print(cm.summary())

    IMPORTANT CAVEAT FOR OPENS:
        ESP is_real flags are unreliable for opens because Apple Mail Privacy
        Protection masks the signals ESPs use to detect real opens. Our
        pattern rules (apple_mail_double, multi_open, reopen_long_span) are
        designed to catch these users. The "FP rate" for opens measured
        against ESP ground truth will appear very high (~76%) but this is
        because the ESP is wrong, not our algorithm.

        For opens, the confusion matrix is most useful for measuring FN rate
        (real opens we missed) and for validating ESP-confirmed rules.
        For FP rate on opens, use the proxy-based benchmark() instead.
    """
    cm = ConfusionMatrix(metric_type=metric)

    for r in results:
        key = f"{r.subscriber_id}:{r.campaign_id}"

        if metric == "clicks":
            if r.raw_click_events == 0:
                continue
            honest_human = r.unique_click
            label = r.click_classification.label
        else:
            if r.raw_open_events == 0:
                continue
            honest_human = r.unique_open
            label = r.open_classification.label

        esp_real = esp_is_real.get(key, False)

        if honest_human and esp_real:
            cm.tp += 1
            cm.tp_by_rule[label] += 1
        elif honest_human and not esp_real:
            cm.fp += 1
            cm.fp_by_rule[label] += 1
        elif not honest_human and esp_real:
            cm.fn += 1
            cm.fn_by_rule[label] += 1
        else:
            cm.tn += 1
            cm.tn_by_rule[label] += 1

    return cm


def compare_to_esp(
    results: List[SendResult],
    esp_unique_opens: Dict[str, bool],
    esp_unique_clicks: Dict[str, bool],
) -> Dict[str, dict]:
    """Compare Honest Opens classifications to your ESP's built-in metrics.

    This shows where Honest Opens agrees and disagrees with your ESP's
    own unique open/click counts. Useful for understanding the delta.

    Args:
        results: List of SendResult from HonestFilter.classify().
        esp_unique_opens: Dict of {f"{subscriber_id}:{campaign_id}": bool}
                          where True = ESP says unique open.
        esp_unique_clicks: Same format for clicks.

    Returns:
        Dict with agreement/disagreement counts for opens and clicks.
    """
    open_agree = open_disagree = 0
    open_honest_only = open_esp_only = 0
    click_agree = click_disagree = 0
    click_honest_only = click_esp_only = 0

    for r in results:
        key = f"{r.subscriber_id}:{r.campaign_id}"

        # Opens
        esp_open = esp_unique_opens.get(key, False)
        if r.unique_open and esp_open:
            open_agree += 1
        elif r.unique_open and not esp_open:
            open_honest_only += 1
        elif not r.unique_open and esp_open:
            open_esp_only += 1
        elif r.raw_open_events > 0:
            open_agree += 1  # Both say no

        # Clicks
        esp_click = esp_unique_clicks.get(key, False)
        if r.unique_click and esp_click:
            click_agree += 1
        elif r.unique_click and not esp_click:
            click_honest_only += 1
        elif not r.unique_click and esp_click:
            click_esp_only += 1
        elif r.raw_click_events > 0:
            click_agree += 1

    return {
        "opens": {
            "agree": open_agree,
            "honest_opens_only": open_honest_only,
            "esp_only": open_esp_only,
            "agreement_rate": (
                open_agree / (open_agree + open_honest_only + open_esp_only)
                if (open_agree + open_honest_only + open_esp_only) else 0.0
            ),
        },
        "clicks": {
            "agree": click_agree,
            "honest_opens_only": click_honest_only,
            "esp_only": click_esp_only,
            "agreement_rate": (
                click_agree / (click_agree + click_honest_only + click_esp_only)
                if (click_agree + click_honest_only + click_esp_only) else 0.0
            ),
        },
    }
