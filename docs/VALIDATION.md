# Validation Framework

Honest Opens ships with a five-method validation suite. The goal is not just to ask "how often is the algorithm right?" but to stress-test it from every angle that matters: calibration, cohort fairness, predictive validity, temporal stability, and empirical holdout.

Every time you update thresholds or add a new rule, run the full suite. If any method degrades, you have a regression.

---

## Method 1: Calibration Audit

**Question:** Does the algorithm's confidence match its accuracy?

A well-calibrated model that assigns 70% probability to a send should be right roughly 70% of the time. Calibration curves expose where the model over- or under-trusts itself, which is where false positives tend to cluster.

**What we found (V3, Sailthru data):**

The weighted mean absolute calibration error for clicks is **5.2 percentage points**. Most rules are well-calibrated, with a few notable exceptions that V3 directly addressed.

| Rule | Assigned Prob | Actual Human % | Gap | Status |
|------|-------------|---------------|-----|--------|
| delayed_single | 95% | 93.7% | -1.3pp | Well-calibrated |
| late_arrival | 90% | 94.1% | +4.1pp | Well-calibrated |
| single_selective | 85% | 94.7% | +9.7pp | Slightly under-confident |
| instant_likely (bot) | 3% | 3.1% | +0.1pp | Well-calibrated |
| machinegun (bot) | 1% | 0.3% | -0.7pp | Well-calibrated |
| thoughtful_multi | 78% | 0.0% | -78pp | **Removed in V3** |
| single_moderate | 72% | 0.0% | -72pp | **Removed in V3** |
| high_volume (bot) | 8% | 45.5% | +37.5pp | **V3 adds ESP rescue** |

The two worst-calibrated rules (`thoughtful_multi` and `single_moderate`) were removed in V3 because they had 0% actual human rates despite being assigned 72-78% probability. The `high_volume` rule was addressed with ESP-rescue logic that recovers the 45.5% of sends that are actually human.

**How to run it:**

```python
from honest_opens.validation import calibration_audit

cal = calibration_audit(results, esp_ground_truth, metric="clicks")
print(cal.summary())
```

---

## Method 2: Sliced Evaluation

**Question:** Does the algorithm perform equally well across all cohorts?

An algorithm that performs well on aggregate but has a 40% false positive rate for one newsletter or one subscriber segment is hiding its failure modes. Slicing forces the failure to surface.

**What we found (V3, Sailthru data):**

| Dimension | Best Cohort | Worst Cohort | Insight |
|-----------|------------|-------------|---------|
| Newsletter | 4.2% FP / 5.1% FN | 22.2% FP / 25.0% FN | Massive variance by list. Some newsletters attract more sophisticated bots. |
| Day of week | Saturday: 4.2% FP / 7.1% FN | Thursday: 10.8% FP / 24.1% FN | Weekend sends have dramatically lower bot rates. Enterprise security scanners are less active on weekends. |
| Engagement tier | Low engagement: 6.0% FP | High engagement: 8.3% FP | Counter-intuitive: higher-engagement subscribers have MORE false positives. Their bots look more "human" because they have real engagement history mixed in. |
| Click volume | 1 click: 7.1% FP / 1.5% FN | 10-25 clicks: 0% FP / 100% FN | The high_volume rule (10+ clicks = bot) is the biggest FN driver. V3 ESP-rescue partially addresses this. |

The click volume slice is the most revealing. Single-click sends are nearly perfectly classified (7.1% FP, 1.5% FN). The algorithm struggles most with 4-9 click sends (15.6% FP, 49.3% FN) and 10+ click sends (100% FN). This is the fundamental tension: high click volume is the strongest bot signal, but some real humans do click multiple links.

**How to run it:**

```python
from honest_opens.validation import sliced_evaluation

# Slice by any dimension you want
def slice_by_volume(r):
    if r.raw_click_events == 1: return "1 click"
    elif r.raw_click_events <= 3: return "2-3 clicks"
    elif r.raw_click_events <= 9: return "4-9 clicks"
    else: return "10+ clicks"

report = sliced_evaluation(results, esp_ground_truth, slice_by_volume, "click_volume")
print(report.summary())
```

---

## Method 3: Proxy Validation

**Question:** Do the engagement labels predict something real downstream?

If the algorithm labels someone as "engaged" (opened, clicked), that classification should predict something beyond its own internal logic. If it does not, your "true positives" may be phantom engagement.

**What we found (V3, Sailthru data):**

| Test | Human Group | Bot Group | Ratio | Verdict |
|------|------------|----------|-------|---------|
| Core open rate by click class | 62.4% | 34.6% | 1.8x | **PASS** |
| Human open rate by click class | 100% | 16.7% | 6.0x | **PASS** |
| Click-through by open class | 2.36% | 0.00% | Infinite | **PASS** |
| Core rate: active clickers vs bot clickers | 63.5% | 26.9% | 2.4x | **PASS** |
| Raw click rate: bot clickers | 0% human clicks | 82.3% raw clicks | — | **PASS** (bots confirmed) |

Every proxy test passed. Human-classified subscribers are genuinely more engaged by every independent metric. Bot clickers have 82.3% raw click rates but 0% human click rates and only 26.9% core engagement, confirming they are automated.

**How to run it:**

```python
from honest_opens.validation import proxy_validation

proxy = proxy_validation(results)
print(proxy.summary())
```

---

## Method 4: Drift Monitoring

**Question:** Is the algorithm degrading over time?

Concept drift is real in email. The ratio of bot clicks to human clicks changes as spam infrastructure evolves. A static confusion matrix validated once will miss the moment the algorithm starts classifying differently against a shifting reality.

**What we found (V3, Sailthru data, 180 days):**

**Clicks:** Relatively stable. FP rate ranges from 4.4% to 11.9% week-to-week (volatile but no clear trend). FN rate ranges from 8.3% to 24.2% with a slight upward trend of +2.5 percentage points over 6 months. No significant drift detected.

**Opens: DRIFT DETECTED.** Human open rate dropped from 50.4% (February 1) to 38.5% (March 15). Pattern rules (apple_mail_double, multi_open, reopen_long_span) declined by 50% in volume over 6 weeks. This could indicate a change in Apple Mail Privacy Protection behavior, new bot patterns, or a Sailthru event reporting change.

This finding validates the need for rolling drift monitoring. The algorithm IS degrading on opens in the most recent 6 weeks and needs investigation.

**How to run it:**

```python
from honest_opens.validation import drift_monitoring

# Define your time window function
def by_week(r):
    # Return ISO week label from your send timestamp
    return r.send_timestamp[:10]  # or however you bucket time

drift = drift_monitoring(results, esp_ground_truth, metric="clicks", window_fn=by_week)
print(drift.summary())
```

**Recommended monitoring schedule:** Run drift analysis weekly. Alert if FP or FN rate shifts more than 3 percentage points from baseline over a 4-week rolling window.

---

## Method 5: Counterfactual Holdout

**Question:** What would happen if we turned off filtering entirely?

This is the gold standard. Take a random sample, suppress algorithmic filtering, and observe raw behavior. Compare against algorithm-filtered groups. This lets you empirically measure what the algorithm is actually removing and whether those removals correspond to genuinely low-value interactions.

**How to implement a true counterfactual:**

1. **Select a holdout group.** Randomly assign 10% of sends to a holdout cohort.
2. **Report raw metrics for the holdout.** For these sends, report the unfiltered open and click counts to your internal dashboard (or a shadow dashboard).
3. **Compare downstream outcomes.** For both groups, measure harder signals: reply rate, conversion rate, revenue per subscriber, unsubscribe rate.
4. **Evaluate the delta.** If the holdout group's downstream outcomes are worse per-open/click, the filtering is removing low-value interactions. If they are the same, the filtering may be too aggressive.

**Simulated counterfactual (from existing data):**

Without a true holdout, you can simulate by comparing raw vs. filtered metrics on the same data:

```python
from honest_opens.validation import counterfactual_holdout

cf = counterfactual_holdout(results, holdout_pct=0.1)
print(cf.summary())
```

This shows the magnitude of what filtering removes but cannot measure downstream impact without a real holdout.

**Why this matters for advertisers:** If you sell ads based on engagement metrics, a counterfactual holdout lets you prove that your filtered metrics correspond to real attention. An advertiser paying for 10,000 "engaged opens" wants to know those opens led to actual reading, not just pixel fires.

---

## Running the Full Suite

```python
from honest_opens.validation import ValidationSuite

suite = ValidationSuite(results, ground_truth=esp_real)

# Run everything
report = suite.run_all(metric="clicks")
print(report)

# Or run individual methods
cal = suite.calibration(metric="clicks")
proxy = suite.proxy()
drift = suite.drift(metric="clicks", window_fn=by_week)
```

---

## When to Re-validate

Run the full validation suite:

- **After every threshold change.** Even small adjustments can shift FP/FN in unexpected cohorts.
- **After adding or removing a rule.** New rules interact with existing ones.
- **Monthly, as a drift check.** Bot infrastructure evolves. Apple, Google, and Microsoft update their email clients. Enterprise security tools change their scanning behavior.
- **After an ESP platform change.** If your ESP updates their event pipeline, timestamp format, or NHI classification, your thresholds may need recalibration.
- **After a major email client update.** Apple Mail Privacy Protection launched in September 2021 and fundamentally changed open tracking. The next such event will require re-validation.

---

## Sharing Your Results

If you run this validation suite on your own data, we encourage you to share your findings. Aggregate results (FP/FN rates, calibration errors, drift patterns) help the entire industry understand how bot filtering performs across different platforms and audiences.

Open an issue or PR with your validation report. No raw data needed — just the summary metrics.
