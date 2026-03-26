# Honest Opens

**Open-source bot filtering for newsletter engagement. Measured, not estimated.**

Your open rate is a lie. More than half of all email opens are bots. 85% of clicks are bots. Every ESP filters them differently, and none of them show you how.

Honest Opens is an ESP-agnostic algorithm that takes raw event data from any email platform and tells you which opens and clicks are human. It outputs four numbers: **unique opens, total opens, unique clicks, total clicks** — filtered to exclude bot traffic with documented, measured error rates.

Built by [Workweek](https://workweek.com). Read the full story: *[We're Getting Lied To](https://workweek.com)*.

---

## Measured Error Rates (V3)

We validated V3 against raw Sailthru event data using the ESP's `is_real` flag as ground truth across **700,000+ click sends** and **9 million+ open sends** over a 90-day window.

| Metric | False Positive Rate | False Negative Rate | Notes |
|--------|-------------------|-------------------|-------|
| **Clicks** (with ESP real flag) | **5.6%** | **8.6%** | Best performance — uses ESP's own NHI flag as a rescue signal |
| **Clicks** (without ESP real flag) | **6.4%** | **10.6%** | ESP-agnostic mode — timing and volume only |
| **Opens** (ESP-confirmed rules) | **0.5%** | **7%** | Only counting ESP-confirmed and verified-clicker rules |
| **Opens** (including pattern rules) | **~3% est.** | **~7%** | Pattern rules catch Apple Mail users the ESP misclassifies |

**What "false positive" and "false negative" mean here:**
- **False positive:** A bot that we counted as human (inflates your metrics)
- **False negative:** A real human that we counted as a bot (deflates your metrics)

**Why opens FP is "estimated":** Sailthru's `is_real` flag misclassifies Apple Mail Privacy Protection users as bots. Our pattern rules (apple_mail_double, multi_open, reopen_long_span) are designed to catch these users. The subscribers caught by these rules have an average of 83-132 verified opens in their history and 29-52% core engagement rates — they are clearly real. But we cannot prove it with ESP data alone, so we report the FP rate honestly as an estimate.

See [docs/ALGORITHM.md](docs/ALGORITHM.md) for the full confusion matrix and per-rule breakdown.

---

## Why This Exists

Every ESP has a bot filter. The question is how they calibrate it — and that calibration is shaped by their business model, not yours. High open rates keep customers happy. Happy customers don't churn.

We built our own filtering model at Workweek because we wanted to know what was actually real. Then we open-sourced it because the email industry needs shared standards for what counts as a human open, the same way display advertising standardized viewable impressions 15 years ago.

There is nothing proprietary about pattern matching on timing signatures and click cadences. The only reason these models are black boxes is because transparency would expose how much each platform lets through.

---

## Quick Start

### Install

```bash
pip install honest-opens
```

### From the Command Line

```bash
# See how much of your traffic is bots
python -m honest_opens benchmark \
    --sends sends.csv \
    --opens opens.csv \
    --clicks clicks.csv

# Classify and export results
python -m honest_opens classify \
    --sends sends.csv \
    --opens opens.csv \
    --clicks clicks.csv \
    --output results.csv
```

### From Python

```python
from honest_opens import HonestFilter
from honest_opens.io import load_sends_csv, load_opens_csv, load_clicks_csv
from honest_opens.benchmark import benchmark, confusion_matrix

# Load your data
sends = load_sends_csv("sends.csv")
opens = load_opens_csv("opens.csv")
clicks = load_clicks_csv("clicks.csv")

# Classify
hf = HonestFilter()
results = hf.classify(sends, opens, clicks)

# See the results
for r in results[:5]:
    print(f"{r.subscriber_id}: open={r.unique_open} ({r.open_classification.label}), "
          f"click={r.unique_click} ({r.click_classification.label})")

# Get campaign-level metrics
reports = hf.report(results)
for cid, report in reports.items():
    print(f"Campaign {cid}: {report.open_rate:.1%} open rate, "
          f"{report.click_rate:.1%} CTR "
          f"(raw: {report.raw_open_rate:.1%} / {report.raw_click_rate:.1%})")

# Run the benchmark (proxy mode — no ground truth needed)
report = benchmark(results)
print(report.summary())

# If you have ESP is_real flags, build a proper confusion matrix
# esp_real = {"subscriber:campaign": True/False, ...}
# cm = confusion_matrix(results, esp_real, metric="clicks")
# print(cm.summary())
```

---

## What Data You Need

You need three CSV files with raw event-level data from your ESP. **Not** the pre-filtered metrics from your dashboard — the raw events.

| File | What It Contains | Key Columns |
|------|-----------------|-------------|
| **sends.csv** | One row per subscriber per email sent | `subscriber_id`, `campaign_id`, `send_timestamp` |
| **opens.csv** | Every open-pixel fire (not deduplicated) | `subscriber_id`, `campaign_id`, `open_timestamp` |
| **clicks.csv** | Every click event (not deduplicated) | `subscriber_id`, `campaign_id`, `click_timestamp`, `url` |

**Optional but valuable:** If your ESP provides an `is_nhi` (non-human interaction) or `is_real` flag on individual events, include it. This significantly improves accuracy — our click FN rate drops from 10.6% to 8.6% when the ESP real flag is available.

Most ESPs don't hand you this data in their dashboard. You need to request it via API, webhook, or data export. See **[docs/ESP_DATA_GUIDE.md](docs/ESP_DATA_GUIDE.md)** for platform-specific instructions on how to get this data from Sailthru, Mailchimp, beehiiv, SendGrid, Klaviyo, and others.

---

## How It Works

The algorithm examines the **timing, volume, and behavioral pattern** of events on each subscriber-send pair. It does not use IP addresses, User-Agent strings, or any personally identifiable information.

**For opens**, the key signals are:
- Did the subscriber also click? (strongest signal — "verified clicker")
- Did the ESP flag it as real?
- How fast did the open fire after send?
- Were there multiple opens spread over time? (humans re-read; bots don't)
- Does the subscriber have a history of verified engagement?

**For clicks**, the key signals are:
- How fast was the first click after send? (under 10s = bot)
- How fast were clicks relative to each other? (under 0.5s between clicks = bot)
- How many distinct URLs were clicked? (5+ URLs = scanner bot)
- Total click volume (10+ clicks on one email = bot)
- Does the ESP's own real/NHI flag disagree with the bot classification? (V3 rescue)

Each send gets a classification label, a confidence level (definitive / high / medium / low), and a probability score (0-100). See **[docs/ALGORITHM.md](docs/ALGORITHM.md)** for the full rule-by-rule breakdown and **[docs/VALIDATION.md](docs/VALIDATION.md)** for the five-method validation framework.

### V3 Changes

V3 was validated against raw Sailthru event data and includes these improvements:

- **Removed `thoughtful_multi`** — 100% false positive rate. What looked like "thoughtful multi-clicking" was actually delayed bot re-scans happening days apart.
- **Removed `single_moderate`** — 100% false positive rate. Bots with a 2-minute delay in a narrow 121-131 second timing band.
- **Added ESP-rescue rules** — When a bot rule fires but the ESP's own `is_real` flag disagrees AND the timing is late (5+ minutes), we rescue the send as human. This recovered ~9,000 false negatives while adding only ~200 false positives.
- **Added timing-rescue rules** — For high-volume clicks that arrive 1+ hour after send with moderate click counts, we rescue even without an ESP flag.

---

## Outputs

For each subscriber-send pair, you get:

| Field | Type | Description |
|-------|------|-------------|
| `unique_open` | bool | **Use this for open rate.** TRUE = human open. |
| `total_opens` | int | Count of human open events on this send. |
| `estimated_open` | bool | More generous metric. Includes uncertain-but-likely opens. |
| `unique_click` | bool | **Use this for CTR.** TRUE = human click. |
| `total_clicks` | int | Count of human click events on this send. |
| `open_classification` | object | Label, confidence, probability, and rule details. |
| `click_classification` | object | Label, confidence, probability, and rule details. |

---

## Filtering Profiles

Three pre-built profiles let you choose your tolerance for error:

| Profile | FP Rate (clicks) | Best For |
|---------|-----------------|----------|
| **strict** (default) | ~6% | Ad-supported publishers who need defensible numbers |
| **moderate** | ~10% | General reporting and internal metrics |
| **permissive** | ~20% | Only filtering obvious bots |

```python
from honest_opens import HonestFilter
from honest_opens.thresholds import HonestConfig

# Use a different profile
config = HonestConfig()  # strict by default

# Or generate a config file to customize
# python -m honest_opens init-config --output config.json --profile moderate
config = HonestConfig.load("config.json")
hf = HonestFilter(config=config)
```

---

## Calibration

The default thresholds were calibrated on **Sailthru event data** processing ~10M sends/month across 10 newsletters. Different ESPs have different timestamp granularity, event batching behavior, and pre-processing pipelines that can shift optimal threshold values.

**Key platform-specific considerations:**
- **Timestamp resolution:** Sailthru provides sub-second timestamps. If your ESP rounds to the nearest second or minute, the instant-prefetch and machinegun rules need wider thresholds.
- **Event batching:** Some ESPs batch events before writing them, which can compress inter-click timing. If your machinegun rule catches too many humans, widen the threshold.
- **Pre-filtering:** Some ESPs pre-filter obvious bots before exposing events. If your raw data is already partially filtered, the bot percentages will be lower.
- **NHI/is_real flag:** The ESP-rescue rules depend on this flag. If your ESP doesn't provide it, the algorithm still works but with higher FN rates (~10.6% vs ~8.6% for clicks).

See **[docs/CALIBRATION.md](docs/CALIBRATION.md)** for step-by-step guidance.

---

## False Positive and False Negative Methodology

We measure error rates two ways:

### 1. Ground Truth Mode (recommended)

If your ESP provides an `is_real` or `is_nhi` flag on individual events, you can build a proper confusion matrix:

```python
from honest_opens.benchmark import confusion_matrix

# Build esp_is_real from your raw event data
esp_real = {}
for event in raw_click_events:
    key = f"{event.subscriber_id}:{event.campaign_id}"
    if event.is_nhi is False:
        esp_real[key] = True
    elif key not in esp_real:
        esp_real[key] = False

cm = confusion_matrix(results, esp_real, metric="clicks")
print(cm.summary())
```

This gives you TP, FP, FN, TN, precision, recall, and F1 — plus a per-rule breakdown showing which rules contribute the most error.

**Caveat for opens:** ESP `is_real` flags are unreliable for opens because Apple Mail Privacy Protection masks the signals ESPs use. Our pattern rules are designed to catch these users. The confusion matrix for opens will show a misleadingly high FP rate. Use proxy mode for open FP estimation.

### 2. Proxy Mode (no ground truth needed)

If your ESP doesn't provide `is_real` flags, the benchmark module uses internal heuristics:

```python
from honest_opens.benchmark import benchmark

report = benchmark(results)
print(report.summary())
```

This estimates FP/FN using signals like low-probability human classifications and bot opens with human clicks on the same send.

---

## Share Your Algorithm

We believe the email industry needs shared, transparent standards for engagement measurement. If you are an **ESP**, a **large publisher**, or a **data team** that has built your own bot filtering:

**We invite you to publish your methodology.**

You don't need to open-source your code. Even publishing a document that describes:
- What signals you use (timing, volume, user-agent, IP, etc.)
- What thresholds you apply
- What your measured or estimated FP/FN rates are
- What percentage of raw events you filter out

...would be a meaningful contribution to the industry. The current state — where every platform has a black-box filter and nobody can compare — hurts publishers and advertisers.

**If you have built a filtering algorithm**, we would love to:
- Link to your published methodology from this repo
- Include your thresholds as a named profile in Honest Opens
- Co-publish benchmark comparisons across platforms

Open an issue or email [adam@workweek.com](mailto:adam@workweek.com).

---

## Project Structure

```
honest-opens/
├── honest_opens/
│   ├── __init__.py          # Package entry point
│   ├── classifier.py        # Core classification engine (V3)
│   ├── models.py            # Input/output data models
│   ├── thresholds.py        # Configurable thresholds and profiles
│   ├── benchmark.py         # Confusion matrix + proxy FP/FN estimation
│   ├── validation.py        # Five-method validation suite
│   ├── io.py                # CSV and DataFrame loaders
│   └── cli.py               # Command-line interface
├── docs/
│   ├── ALGORITHM.md          # Full rule-by-rule explanation (V3)
│   ├── VALIDATION.md         # Five-method validation framework
│   ├── ESP_DATA_GUIDE.md     # How to get raw data from your ESP
│   └── CALIBRATION.md        # Tuning thresholds for your platform
├── examples/
│   └── quickstart.py         # End-to-end example
├── tests/
│   └── test_classifier.py    # Unit tests
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## Contributing

We welcome contributions. If you discover a new bot pattern, calibrate thresholds for a new ESP, or improve the algorithm, please open a PR.

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for guidelines.

---

## License

MIT License. See [LICENSE](LICENSE).

---

## About

Built by [Workweek](https://workweek.com). We publish newsletters for HR leaders, marketers, and finance professionals. We built this because we needed honest numbers for our advertisers, and we open-sourced it because the industry needs a shared standard.

Questions? Open an issue or reach out to [adam@workweek.com](mailto:adam@workweek.com).
