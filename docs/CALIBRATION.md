# Calibrating Honest Opens for Your ESP

The default thresholds in Honest Opens were calibrated on **Sailthru event data** processing approximately 10 million sends per month across 10 newsletters. Sailthru provides second-level timestamp granularity and separates "real" from "non-human interaction" (NHI) events natively.

Your ESP may behave differently. This guide explains how to tune the thresholds for your platform.

---

## Why Thresholds May Need Adjustment

Different ESPs introduce different artifacts into event data:

**Timestamp batching.** Some ESPs process events in batches and assign the batch timestamp rather than the actual event time. This compresses the time-to-event signal, making bot clicks look slower and human clicks look faster than they actually are. If your ESP batches events, you may need to widen the bot detection windows.

**Timestamp rounding.** Some ESPs round timestamps to the nearest minute or even 5-minute interval. This destroys the sub-second inter-click timing that the machinegun rule depends on. If your timestamps are rounded, the machinegun rules will underfire and you will need to rely more heavily on URL-count and volume rules.

**Pre-filtering.** Some ESPs filter out obvious bots before exposing events via API. If your ESP already removes the most egregious bots, the remaining bot traffic will be harder to detect and your false negative rate will be higher. This is not necessarily a problem — it means the ESP is doing some of the work for you.

**Event deduplication.** Some ESPs deduplicate open events, showing only the first open per subscriber per campaign. This breaks the multi-open and apple-mail-double rules entirely. If your ESP deduplicates opens, those rules will never fire and you should rely on timing and click-based signals instead.

---

## Step 1: Run the Benchmark on Default Thresholds

Start by running the benchmark with default settings:

```bash
python -m honest_opens benchmark \
    --sends sends.csv \
    --opens opens.csv \
    --clicks clicks.csv
```

Look at the classification distribution in the output. Key things to check:

**If `BOT:machinegun` is near zero** but you expect bot traffic, your ESP may be rounding timestamps. Try increasing `bot_machinegun_definitive_max_inter_click` from 0.5s to 2.0s or higher.

**If `UNCERTAIN:no_evidence` dominates opens** (more than 70%), your ESP may be deduplicating open events. Consider setting `estimated_open_includes_uncertain = True` and using `estimated_open` as your primary open metric.

**If `BOT:instant_prefetch` is near zero** for clicks, your ESP may be batching timestamps. Try increasing `bot_instant_definitive_max_seconds` from 5s to 15s or 30s.

**If almost everything is classified as human**, your ESP may already be pre-filtering bots. Compare your raw event counts to what your ESP dashboard shows — if they are similar, the ESP is filtering before you see the data.

---

## Step 2: Generate a Custom Config

```bash
python -m honest_opens init-config --output my_config.json --profile strict
```

This creates a JSON file with all thresholds. Edit the values based on what you observed in Step 1.

---

## Step 3: Key Thresholds to Adjust

### For ESPs with Coarse Timestamps (minute-level)

```json
{
  "open_thresholds": {
    "bot_instant_max_seconds": 60,
    "bot_session_window_seconds": 300,
    "apple_double_min_span_seconds": 60,
    "multi_open_min_span_seconds": 600
  },
  "click_thresholds": {
    "bot_instant_definitive_max_seconds": 30,
    "bot_instant_likely_max_seconds": 60,
    "bot_machinegun_definitive_max_inter_click": 5.0,
    "bot_machinegun_likely_max_inter_click": 10.0,
    "human_delayed_min_seconds": 600,
    "human_moderate_min_seconds": 120,
    "human_moderate_max_seconds": 600
  }
}
```

### For ESPs That Pre-Filter Bots

If your ESP already removes obvious bots, tighten the human thresholds to catch the remaining sophisticated bots:

```json
{
  "click_thresholds": {
    "bot_machinegun_min_urls": 2,
    "bot_scanner_min_urls": 4,
    "bot_volume_min_total_clicks": 8,
    "human_delayed_min_seconds": 600
  }
}
```

### For ESPs That Deduplicate Opens

If you only get one open event per subscriber per campaign, disable the multi-open rules by setting impossible thresholds:

```json
{
  "open_thresholds": {
    "apple_double_exact_opens": 999,
    "multi_open_min_events": 999,
    "reopen_min_span_seconds": 999999
  },
  "estimated_open_includes_uncertain": true
}
```

---

## Step 4: Validate Your Calibration

After adjusting thresholds, run the benchmark again with your custom config:

```bash
python -m honest_opens benchmark \
    --sends sends.csv \
    --opens opens.csv \
    --clicks clicks.csv \
    --config my_config.json
```

Compare the results to your ESP's reported metrics. A well-calibrated model should show:

| Metric | Expected Range |
|--------|---------------|
| Open rate (filtered) | 30-60% lower than ESP's reported rate |
| Click rate (filtered) | 50-90% lower than ESP's reported rate |
| Open FP rate | 1-5% (target: ~3%) |
| Click FP rate | 1-5% (target: ~3%) |
| `BOT:machinegun` clicks | 30-60% of all click events (if ESP doesn't pre-filter) |
| `UNCERTAIN:no_evidence` opens | 40-70% of all open events |

If your filtered rates are suspiciously close to the raw rates, the thresholds are too permissive. If the filtered rates are unrealistically low (under 5% open rate for a healthy list), the thresholds are too strict.

---

## Step 5: Monitor Over Time

Bot patterns evolve. Enterprise security tools update their scanning behavior. Apple changes Mail Privacy Protection. We recommend re-running the benchmark monthly and watching for:

- Sudden shifts in classification distribution (a rule that used to fire frequently stops firing)
- FP rate climbing above 5%
- New bot patterns that don't match any existing rule

If you discover a new bot pattern, consider contributing it back to the project. See [CONTRIBUTING.md](../CONTRIBUTING.md).
