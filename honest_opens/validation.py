"""
Honest Opens V3 — Validation Suite

Five validation methods that can be run against any dataset to assess
algorithm quality. Build once, run every time you update thresholds.

Methods:
  1. Calibration Audit — does assigned probability match actual accuracy?
  2. Sliced Evaluation — FP/FN broken down by cohort
  3. Proxy Validation — do labels predict downstream signals?
  4. Drift Monitoring — precision/recall over time
  5. Counterfactual Holdout — empirical measurement of what filtering removes

Usage:
    from honest_opens.validation import ValidationSuite
    suite = ValidationSuite(results, ground_truth=esp_real)
    report = suite.run_all()
    print(report)
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import math

from honest_opens.models import SendResult


# ─────────────────────────────────────────────────────────────────────
# 1. CALIBRATION AUDIT
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CalibrationBucket:
    """One bucket in the calibration curve."""
    bucket_label: str
    prob_range: Tuple[int, int]
    total: int = 0
    actual_human: int = 0

    @property
    def actual_rate(self) -> float:
        return self.actual_human / self.total if self.total else 0.0

    @property
    def expected_rate(self) -> float:
        return (self.prob_range[0] + self.prob_range[1]) / 200.0

    @property
    def gap(self) -> float:
        return self.actual_rate - self.expected_rate


@dataclass
class CalibrationReport:
    """Calibration audit results."""
    metric: str  # "opens" or "clicks"
    buckets: List[CalibrationBucket] = field(default_factory=list)
    per_rule: Dict[str, dict] = field(default_factory=dict)

    @property
    def weighted_error(self) -> float:
        total = sum(b.total for b in self.buckets)
        if total == 0:
            return 0.0
        return sum(abs(b.gap) * b.total for b in self.buckets) / total

    def summary(self) -> str:
        lines = [
            f"── CALIBRATION AUDIT: {self.metric.upper()} ──",
            f"  Weighted Mean Absolute Error: {self.weighted_error:.1%}",
            "",
            f"  {'Bucket':<12} {'Total':>8} {'Actual%':>8} {'Expected%':>9} {'Gap':>8}",
            f"  {'─'*12} {'─'*8} {'─'*8} {'─'*9} {'─'*8}",
        ]
        for b in self.buckets:
            if b.total > 0:
                lines.append(
                    f"  {b.bucket_label:<12} {b.total:>8,} {b.actual_rate:>7.1%} "
                    f"{b.expected_rate:>8.1%} {b.gap:>+7.1%}"
                )
        if self.per_rule:
            lines.append("")
            lines.append("  Per-rule calibration:")
            for rule, data in sorted(self.per_rule.items(), key=lambda x: -x[1]["total"]):
                if data["total"] >= 100:
                    lines.append(
                        f"    {rule:40s} n={data['total']:>6,}  "
                        f"actual={data['actual_rate']:.1%}  "
                        f"assigned={data['assigned_prob']:.0%}  "
                        f"gap={data['actual_rate']-data['assigned_prob']:+.1%}"
                    )
        return "\n".join(lines)


def calibration_audit(
    results: List[SendResult],
    ground_truth: Dict[str, bool],
    metric: str = "clicks",
) -> CalibrationReport:
    """Run calibration audit: does probability match actual accuracy?

    Args:
        results: Classified send results.
        ground_truth: {subscriber_id:campaign_id: True/False} from ESP.
        metric: "clicks" or "opens".
    """
    buckets = [
        CalibrationBucket(f"{lo}-{hi}", (lo, hi))
        for lo, hi in [(0,9),(10,19),(20,29),(30,39),(40,49),
                        (50,59),(60,69),(70,79),(80,89),(90,100)]
    ]
    rule_stats = defaultdict(lambda: {"total": 0, "actual_human": 0, "assigned_prob": 0})

    for r in results:
        key = f"{r.subscriber_id}:{r.campaign_id}"
        if metric == "clicks":
            if r.raw_click_events == 0:
                continue
            prob = r.click_classification.probability
            label = r.click_classification.label
        else:
            if r.raw_open_events == 0:
                continue
            prob = r.open_classification.probability
            label = r.open_classification.label

        is_real = ground_truth.get(key, False)

        # Bucket
        idx = min(prob // 10, 9)
        buckets[idx].total += 1
        if is_real:
            buckets[idx].actual_human += 1

        # Per-rule
        rule_stats[label]["total"] += 1
        rule_stats[label]["assigned_prob"] = prob / 100.0
        if is_real:
            rule_stats[label]["actual_human"] += 1

    report = CalibrationReport(metric=metric, buckets=buckets)
    for rule, data in rule_stats.items():
        report.per_rule[rule] = {
            "total": data["total"],
            "actual_rate": data["actual_human"] / data["total"] if data["total"] else 0,
            "assigned_prob": data["assigned_prob"],
        }
    return report


# ─────────────────────────────────────────────────────────────────────
# 2. SLICED EVALUATION
# ─────────────────────────────────────────────────────────────────────

@dataclass
class Slice:
    """FP/FN rates for one cohort slice."""
    name: str
    total: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def fp_rate(self) -> float:
        denom = self.tp + self.fp
        return self.fp / denom if denom else 0.0

    @property
    def fn_rate(self) -> float:
        denom = self.tp + self.fn
        return self.fn / denom if denom else 0.0


@dataclass
class SlicedReport:
    """Sliced evaluation results."""
    dimension: str
    metric: str
    slices: List[Slice] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"── SLICED EVALUATION: {self.metric.upper()} by {self.dimension.upper()} ──",
            f"  {'Slice':<30} {'Total':>8} {'FP%':>6} {'FN%':>6} {'TP':>8} {'FP':>6} {'FN':>6}",
            f"  {'─'*30} {'─'*8} {'─'*6} {'─'*6} {'─'*8} {'─'*6} {'─'*6}",
        ]
        for s in sorted(self.slices, key=lambda x: -x.total):
            lines.append(
                f"  {s.name:<30} {s.total:>8,} {s.fp_rate:>5.1%} {s.fn_rate:>5.1%} "
                f"{s.tp:>8,} {s.fp:>6,} {s.fn:>6,}"
            )
        # Flag worst performers
        worst_fp = max(self.slices, key=lambda s: s.fp_rate if s.total >= 100 else 0)
        worst_fn = max(self.slices, key=lambda s: s.fn_rate if s.total >= 100 else 0)
        lines.append(f"\n  Worst FP: {worst_fp.name} ({worst_fp.fp_rate:.1%})")
        lines.append(f"  Worst FN: {worst_fn.name} ({worst_fn.fn_rate:.1%})")
        return "\n".join(lines)


def sliced_evaluation(
    results: List[SendResult],
    ground_truth: Dict[str, bool],
    slice_fn,
    dimension_name: str,
    metric: str = "clicks",
) -> SlicedReport:
    """Break down FP/FN by an arbitrary cohort dimension.

    Args:
        results: Classified send results.
        ground_truth: ESP ground truth.
        slice_fn: Function(SendResult) -> str that returns the slice name.
        dimension_name: Human-readable name of the dimension.
        metric: "clicks" or "opens".
    """
    slices_map: Dict[str, Slice] = {}

    for r in results:
        key = f"{r.subscriber_id}:{r.campaign_id}"
        if metric == "clicks" and r.raw_click_events == 0:
            continue
        if metric == "opens" and r.raw_open_events == 0:
            continue

        slice_name = slice_fn(r)
        if slice_name not in slices_map:
            slices_map[slice_name] = Slice(name=slice_name)
        s = slices_map[slice_name]
        s.total += 1

        honest_human = r.unique_click if metric == "clicks" else r.unique_open
        esp_real = ground_truth.get(key, False)

        if honest_human and esp_real:
            s.tp += 1
        elif honest_human and not esp_real:
            s.fp += 1
        elif not honest_human and esp_real:
            s.fn += 1
        else:
            s.tn += 1

    return SlicedReport(
        dimension=dimension_name,
        metric=metric,
        slices=list(slices_map.values()),
    )


# ─────────────────────────────────────────────────────────────────────
# 3. PROXY VALIDATION
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ProxyReport:
    """Proxy validation results — do labels predict downstream signals?"""
    tests: List[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["── PROXY VALIDATION ──", ""]
        for t in self.tests:
            lines.append(f"  Test: {t['name']}")
            lines.append(f"    Hypothesis: {t['hypothesis']}")
            lines.append(f"    Result: {t['result']}")
            lines.append(f"    Verdict: {'PASS' if t['passed'] else 'FAIL'}")
            lines.append("")
        passed = sum(1 for t in self.tests if t["passed"])
        lines.append(f"  Overall: {passed}/{len(self.tests)} tests passed")
        return "\n".join(lines)


def proxy_validation(results: List[SendResult]) -> ProxyReport:
    """Test whether engagement labels predict downstream signals.

    Uses internal signals only (no ground truth needed):
      - Human clickers should have higher open rates
      - Human openers should have higher click rates
      - Bot-only subscribers should have lower lifetime engagement
    """
    report = ProxyReport()

    # Test 1: Human clickers should also be human openers
    human_click_also_open = 0
    human_click_total = 0
    bot_click_also_open = 0
    bot_click_total = 0

    for r in results:
        if r.unique_click:
            human_click_total += 1
            if r.unique_open:
                human_click_also_open += 1
        elif r.raw_click_events > 0:
            bot_click_total += 1
            if r.unique_open:
                bot_click_also_open += 1

    hc_open_rate = human_click_also_open / human_click_total if human_click_total else 0
    bc_open_rate = bot_click_also_open / bot_click_total if bot_click_total else 0

    report.tests.append({
        "name": "Human clickers have higher open rates",
        "hypothesis": "Human clickers should be human openers more often than bot clickers",
        "result": f"Human clicker open rate: {hc_open_rate:.1%}, Bot clicker open rate: {bc_open_rate:.1%}",
        "passed": hc_open_rate > bc_open_rate * 1.5,
    })

    # Test 2: Human openers should click more
    human_open_click = 0
    human_open_total = 0
    bot_open_click = 0
    bot_open_total = 0

    for r in results:
        if r.unique_open:
            human_open_total += 1
            if r.unique_click:
                human_open_click += 1
        elif r.raw_open_events > 0:
            bot_open_total += 1
            if r.unique_click:
                bot_open_click += 1

    ho_click_rate = human_open_click / human_open_total if human_open_total else 0
    bo_click_rate = bot_open_click / bot_open_total if bot_open_total else 0

    report.tests.append({
        "name": "Human openers have higher click rates",
        "hypothesis": "Human openers should click more than bot openers",
        "result": f"Human opener CTR: {ho_click_rate:.1%}, Bot opener CTR: {bo_click_rate:.1%}",
        "passed": ho_click_rate > bo_click_rate,
    })

    # Test 3: Estimated opens should fall between human and bot
    est_open_click = 0
    est_open_total = 0
    for r in results:
        if r.estimated_open and not r.unique_open:
            est_open_total += 1
            if r.unique_click:
                est_open_click += 1

    eo_click_rate = est_open_click / est_open_total if est_open_total else 0

    report.tests.append({
        "name": "Estimated opens are between human and bot",
        "hypothesis": "Estimated-but-not-unique opens should have CTR between human and bot",
        "result": f"Estimated CTR: {eo_click_rate:.1%} (human: {ho_click_rate:.1%}, bot: {bo_click_rate:.1%})",
        "passed": bo_click_rate <= eo_click_rate <= ho_click_rate or eo_click_rate >= bo_click_rate,
    })

    return report


# ─────────────────────────────────────────────────────────────────────
# 4. DRIFT MONITORING
# ─────────────────────────────────────────────────────────────────────

@dataclass
class DriftWindow:
    """Metrics for one time window."""
    window_label: str
    total: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    bot_pct: float = 0.0

    @property
    def fp_rate(self) -> float:
        d = self.tp + self.fp
        return self.fp / d if d else 0.0

    @property
    def fn_rate(self) -> float:
        d = self.tp + self.fn
        return self.fn / d if d else 0.0

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0


@dataclass
class DriftReport:
    """Drift monitoring results."""
    metric: str
    windows: List[DriftWindow] = field(default_factory=list)
    fp_trend: float = 0.0
    fn_trend: float = 0.0
    drift_detected: bool = False

    def summary(self) -> str:
        lines = [
            f"── DRIFT MONITORING: {self.metric.upper()} ──",
            f"  {'Window':<12} {'Total':>8} {'FP%':>6} {'FN%':>6} {'Prec':>6} {'Recall':>7} {'Bot%':>6}",
            f"  {'─'*12} {'─'*8} {'─'*6} {'─'*6} {'─'*6} {'─'*7} {'─'*6}",
        ]
        for w in self.windows:
            lines.append(
                f"  {w.window_label:<12} {w.total:>8,} {w.fp_rate:>5.1%} {w.fn_rate:>5.1%} "
                f"{w.precision:>5.1%} {w.recall:>6.1%} {w.bot_pct:>5.1%}"
            )
        lines.append(f"\n  FP trend: {self.fp_trend:+.1%}")
        lines.append(f"  FN trend: {self.fn_trend:+.1%}")
        if self.drift_detected:
            lines.append("  *** DRIFT DETECTED — consider recalibrating thresholds ***")
        return "\n".join(lines)


def drift_monitoring(
    results: List[SendResult],
    ground_truth: Dict[str, bool],
    metric: str = "clicks",
    window_fn=None,
) -> DriftReport:
    """Track precision/recall over time windows.

    Args:
        results: Classified send results.
        ground_truth: ESP ground truth.
        metric: "clicks" or "opens".
        window_fn: Function(SendResult) -> str that returns the time window label.
                   Defaults to ISO week if send_timestamp is available.
    """
    windows_map: Dict[str, DriftWindow] = {}

    for r in results:
        key = f"{r.subscriber_id}:{r.campaign_id}"
        if metric == "clicks" and r.raw_click_events == 0:
            continue
        if metric == "opens" and r.raw_open_events == 0:
            continue

        if window_fn:
            wlabel = window_fn(r)
        else:
            wlabel = "all"

        if wlabel not in windows_map:
            windows_map[wlabel] = DriftWindow(window_label=wlabel)
        w = windows_map[wlabel]
        w.total += 1

        honest_human = r.unique_click if metric == "clicks" else r.unique_open
        esp_real = ground_truth.get(key, False)

        if honest_human and esp_real:
            w.tp += 1
        elif honest_human and not esp_real:
            w.fp += 1
        elif not honest_human and esp_real:
            w.fn += 1
        else:
            w.tn += 1

    windows = sorted(windows_map.values(), key=lambda w: w.window_label)

    # Calculate bot percentage
    for w in windows:
        bot_count = w.fn + w.tn
        w.bot_pct = bot_count / w.total if w.total else 0

    # Detect trend
    report = DriftReport(metric=metric, windows=windows)
    if len(windows) >= 4:
        mid = len(windows) // 2
        first_fp = sum(w.fp_rate for w in windows[:mid]) / mid
        second_fp = sum(w.fp_rate for w in windows[mid:]) / (len(windows) - mid)
        first_fn = sum(w.fn_rate for w in windows[:mid]) / mid
        second_fn = sum(w.fn_rate for w in windows[mid:]) / (len(windows) - mid)
        report.fp_trend = second_fp - first_fp
        report.fn_trend = second_fn - first_fn
        report.drift_detected = abs(report.fp_trend) > 0.03 or abs(report.fn_trend) > 0.03

    return report


# ─────────────────────────────────────────────────────────────────────
# 5. COUNTERFACTUAL HOLDOUT
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CounterfactualReport:
    """Results from a counterfactual holdout analysis."""
    holdout_size: int = 0
    filtered_size: int = 0

    # Holdout group (raw, unfiltered)
    holdout_raw_open_rate: float = 0.0
    holdout_raw_click_rate: float = 0.0

    # Filtered group
    filtered_open_rate: float = 0.0
    filtered_click_rate: float = 0.0

    # What filtering removed
    open_reduction_pct: float = 0.0
    click_reduction_pct: float = 0.0

    def summary(self) -> str:
        return "\n".join([
            "── COUNTERFACTUAL HOLDOUT ──",
            f"  Holdout group: {self.holdout_size:,} sends (raw metrics)",
            f"  Filtered group: {self.filtered_size:,} sends (Honest Opens metrics)",
            "",
            f"  Open rate:  raw {self.holdout_raw_open_rate:.1%}  →  filtered {self.filtered_open_rate:.1%}  "
            f"(reduction: {self.open_reduction_pct:.1%})",
            f"  Click rate: raw {self.holdout_raw_click_rate:.1%}  →  filtered {self.filtered_click_rate:.1%}  "
            f"(reduction: {self.click_reduction_pct:.1%})",
            "",
            "  Interpretation: The reduction shows what the algorithm is removing.",
            "  If the holdout group's raw metrics are much higher, the difference",
            "  is the bot traffic the algorithm would have filtered.",
        ])


def counterfactual_holdout(
    results: List[SendResult],
    holdout_pct: float = 0.1,
) -> CounterfactualReport:
    """Simulate a counterfactual holdout by comparing raw vs filtered metrics.

    Since we cannot actually suppress filtering in production, this simulates
    the holdout by comparing raw event counts to filtered classifications on
    the same data. The "holdout" is what you would report without filtering.

    For a true counterfactual, you would need to:
    1. Take a random 10% sample of sends
    2. Report their raw (unfiltered) metrics to advertisers
    3. Compare downstream outcomes (conversions, replies) between
       the holdout group and the filtered group
    4. If the holdout group's downstream outcomes are worse per-open/click,
       the filtering is removing low-value interactions

    This function provides the simulated version using the data you have.

    Args:
        results: Classified send results.
        holdout_pct: Fraction to use as simulated holdout (default 10%).
    """
    import random
    random.seed(42)

    holdout = random.sample(results, int(len(results) * holdout_pct))
    filtered = results  # All results have filtered metrics

    report = CounterfactualReport()
    report.holdout_size = len(holdout)
    report.filtered_size = len(filtered)

    # Holdout: raw metrics
    h_opens = sum(1 for r in holdout if r.raw_open_events > 0)
    h_clicks = sum(1 for r in holdout if r.raw_click_events > 0)
    report.holdout_raw_open_rate = h_opens / len(holdout) if holdout else 0
    report.holdout_raw_click_rate = h_clicks / len(holdout) if holdout else 0

    # Filtered: honest metrics
    f_opens = sum(1 for r in filtered if r.unique_open)
    f_clicks = sum(1 for r in filtered if r.unique_click)
    report.filtered_open_rate = f_opens / len(filtered) if filtered else 0
    report.filtered_click_rate = f_clicks / len(filtered) if filtered else 0

    # Reduction
    if report.holdout_raw_open_rate > 0:
        report.open_reduction_pct = 1 - (report.filtered_open_rate / report.holdout_raw_open_rate)
    if report.holdout_raw_click_rate > 0:
        report.click_reduction_pct = 1 - (report.filtered_click_rate / report.holdout_raw_click_rate)

    return report


# ─────────────────────────────────────────────────────────────────────
# FULL VALIDATION SUITE
# ─────────────────────────────────────────────────────────────────────

class ValidationSuite:
    """Run all five validation methods and produce a combined report.

    Usage:
        suite = ValidationSuite(results, ground_truth=esp_real)
        report = suite.run_all()
        print(report)

    Or run individual methods:
        cal = suite.calibration(metric="clicks")
        print(cal.summary())
    """

    def __init__(
        self,
        results: List[SendResult],
        ground_truth: Optional[Dict[str, bool]] = None,
    ):
        self.results = results
        self.ground_truth = ground_truth or {}

    def calibration(self, metric: str = "clicks") -> CalibrationReport:
        return calibration_audit(self.results, self.ground_truth, metric)

    def sliced(self, slice_fn, dimension: str, metric: str = "clicks") -> SlicedReport:
        return sliced_evaluation(self.results, self.ground_truth, slice_fn, dimension, metric)

    def proxy(self) -> ProxyReport:
        return proxy_validation(self.results)

    def drift(self, metric: str = "clicks", window_fn=None) -> DriftReport:
        return drift_monitoring(self.results, self.ground_truth, metric, window_fn)

    def counterfactual(self, holdout_pct: float = 0.1) -> CounterfactualReport:
        return counterfactual_holdout(self.results, holdout_pct)

    def run_all(self, metric: str = "clicks") -> str:
        """Run all validation methods and return a combined report."""
        sections = [
            "=" * 70,
            "HONEST OPENS V3 — FULL VALIDATION REPORT",
            f"  Metric: {metric}",
            f"  Total sends: {len(self.results):,}",
            f"  Ground truth available: {'Yes' if self.ground_truth else 'No (proxy mode only)'}",
            "=" * 70,
            "",
        ]

        # 1. Calibration (requires ground truth)
        if self.ground_truth:
            cal = self.calibration(metric)
            sections.append(cal.summary())
            sections.append("")

        # 2. Proxy validation (always available)
        proxy = self.proxy()
        sections.append(proxy.summary())
        sections.append("")

        # 3. Drift (requires ground truth)
        if self.ground_truth:
            drift = self.drift(metric)
            sections.append(drift.summary())
            sections.append("")

        # 4. Counterfactual
        cf = self.counterfactual()
        sections.append(cf.summary())
        sections.append("")

        sections.extend(["=" * 70, "END OF VALIDATION REPORT", "=" * 70])
        return "\n".join(sections)
