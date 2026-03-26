# How to Get the Data You Need From Your ESP

Honest Opens requires **raw event-level data** — not the pre-filtered "unique open" or "unique click" numbers your ESP shows you in its dashboard. Those numbers have already been through the ESP's own bot filter, which is the black box this project exists to replace.

Here is exactly what you need, how to ask for it, and platform-specific guidance for the major ESPs.

---

## The Three Files You Need

You need three datasets, exported as CSV or queried via API. Every ESP tracks this data internally — the question is whether they expose it to you.

### 1. Sends

One row per subscriber per email sent. This is your baseline.

| Column | Description | Example |
|--------|-------------|---------|
| `subscriber_id` | Your ESP's unique subscriber identifier | `user_abc123` |
| `campaign_id` | The email send / blast / campaign ID | `blast_98765` |
| `send_timestamp` | When the email was sent (ISO 8601 or Unix epoch) | `2025-07-15T14:30:00Z` |

### 2. Open Events

One row per open-pixel fire. You need **every** open event, not just the first one per subscriber. Multiple opens per send are critical for the algorithm.

| Column | Description | Example |
|--------|-------------|---------|
| `subscriber_id` | Must match the sends file | `user_abc123` |
| `campaign_id` | Must match the sends file | `blast_98765` |
| `open_timestamp` | When the open pixel fired | `2025-07-15T15:02:33Z` |
| `is_nhi` | *(Optional)* ESP's bot/NHI flag if available | `true` or `false` |
| `user_agent` | *(Optional)* Raw User-Agent string | `Mozilla/5.0...` |

### 3. Click Events

One row per click. You need **every** click event, including repeat clicks on the same URL. Include the URL so the algorithm can count distinct links clicked.

| Column | Description | Example |
|--------|-------------|---------|
| `subscriber_id` | Must match the sends file | `user_abc123` |
| `campaign_id` | Must match the sends file | `blast_98765` |
| `click_timestamp` | When the click occurred | `2025-07-15T15:04:12Z` |
| `url` | *(Optional but recommended)* The clicked URL | `https://example.com/article` |
| `is_nhi` | *(Optional)* ESP's bot/NHI flag if available | `true` or `false` |

---

## What to Say to Your ESP

If your ESP doesn't expose raw event data in their UI, here is a template you can send to your account manager or support team:

> We are implementing an independent bot-filtering model for our email engagement data. To do this, we need access to raw, event-level data for opens and clicks — not deduplicated or pre-filtered metrics.
>
> Specifically, we need:
>
> 1. **Send-level data**: One row per subscriber per campaign, with subscriber ID, campaign ID, and send timestamp.
>
> 2. **Raw open events**: Every open-pixel fire (not deduplicated), with subscriber ID, campaign ID, and event timestamp. If your platform flags non-human interaction (NHI) or bot opens, please include that flag as well.
>
> 3. **Raw click events**: Every click event (not deduplicated), with subscriber ID, campaign ID, event timestamp, and the clicked URL. If your platform flags NHI/bot clicks, please include that flag.
>
> We need this data via API, webhook, or CSV export. We are happy to sign any necessary data agreements.

---

## Platform-Specific Guidance

### Sailthru (Marigold)

Sailthru provides the richest raw data of any major ESP. This algorithm was originally calibrated on Sailthru event data.

**How to get the data:**
- **Job API**: Use the `export_blast` job type to get send-level data per campaign.
- **User API**: The `get` endpoint returns per-user engagement history.
- **Event Stream**: Sailthru's real-time event stream (if enabled) provides individual open and click events with timestamps.
- **Data Feed**: Request a raw data feed export from your account manager. Ask for "raw opens and clicks with NHI flags and timestamps."

**Available signals:**
- `real_opens` vs `nhi_opens` — Sailthru separates human from non-human opens
- `real_clicks` vs `nhi_clicks` — Same for clicks
- Timestamps are in Unix epoch seconds (UTC)

**Timestamp note:** Sailthru timestamps are generally reliable with second-level granularity. The default thresholds in Honest Opens were calibrated on this data.

### Mailchimp (Intuit)

**How to get the data:**
- **Reports API**: `/reports/{campaign_id}/open-details` and `/reports/{campaign_id}/click-details` provide individual events.
- **Export API**: Bulk export of subscriber activity.
- **Webhooks**: Configure open and click webhooks for real-time event capture.

**Limitations:**
- Mailchimp does not expose an NHI/bot flag. You will rely entirely on timing-based rules.
- Timestamp granularity varies. Test with a small batch first.
- Free and Essentials plans have limited API access.

### beehiiv

**How to get the data:**
- **API**: beehiiv's API provides subscriber-level engagement data.
- **Webhooks**: Open and click webhooks are available on Growth and Enterprise plans.
- **CSV Export**: Available from the dashboard, but may only include deduplicated metrics.

**Limitations:**
- As of early 2026, beehiiv's API does not expose individual open/click event timestamps at the granularity needed. You may need to request raw data from your account manager.
- No NHI flag is exposed.

**What to ask for:** Request access to raw webhook events or a data export that includes every open and click event with timestamps, not just unique flags.

### Omeda

**How to get the data:**
- **Engagement API**: Omeda provides detailed engagement data through their API.
- **Data Warehouse**: If you have Omeda's data warehouse product, query the raw events table directly.
- **CSV Export**: Request a custom export from your account team.

**Available signals:**
- Omeda tracks "confirmed opens" separately from pixel fires.
- Click data includes URLs and timestamps.

### ConvertKit (Kit)

**How to get the data:**
- **API**: The subscribers API provides engagement data, but individual event timestamps may be limited.
- **Webhooks**: Configure subscriber activity webhooks.

**Limitations:**
- ConvertKit's API is subscriber-centric, not event-centric. You may need to reconstruct event timelines from subscriber activity logs.

### SendGrid (Twilio)

**How to get the data:**
- **Event Webhook**: The most reliable method. Configure the event webhook to capture `open`, `click`, and `delivered` events in real time. Each event includes a timestamp and metadata.
- **Email Activity API**: Provides 3 days of event history (30 days on paid plans).

**Available signals:**
- SendGrid's event webhook includes `useragent`, `ip`, and `url` fields.
- No built-in NHI flag, but the User-Agent string can be used for supplementary analysis.

**Timestamp note:** SendGrid timestamps are Unix epoch integers. Reliable granularity.

### ActiveCampaign

**How to get the data:**
- **API**: The contacts API provides engagement history. The events API can provide individual open/click events.
- **Webhooks**: Available for open and click events.

**Limitations:**
- Event-level data access depends on your plan tier.

### HubSpot

**How to get the data:**
- **Marketing Events API**: Provides open and click events with timestamps.
- **CRM Export**: Export email engagement data from the CRM.

**Limitations:**
- HubSpot aggregates some engagement data. Ensure you are getting individual events, not roll-ups.

### Klaviyo

**How to get the data:**
- **Events API**: Klaviyo's event-driven architecture makes this straightforward. Query the `Opened Email` and `Clicked Email` events.
- **Data Export**: Available from the dashboard.

**Available signals:**
- Klaviyo provides `$is_bot_traffic` flag on some events.
- Timestamps are ISO 8601 with millisecond precision.

---

## Timestamp Considerations

Different ESPs handle timestamps differently. This matters because the algorithm relies heavily on time-to-event calculations.

| Factor | Impact | What to Check |
|--------|--------|---------------|
| **Granularity** | Some ESPs round to the nearest minute. The algorithm needs second-level precision. | Send yourself a test email and check the raw event timestamps. |
| **Timezone** | Timestamps should be in UTC. If your ESP uses local time, convert before processing. | Check your ESP's documentation or API response headers. |
| **Batching** | Some ESPs batch-process events and assign the batch timestamp, not the actual event time. This can compress timing signals. | Compare the timestamp of an open you trigger manually against the actual time. |
| **Pre-processing** | Some ESPs deduplicate or filter events before exposing them via API. You need the unfiltered stream. | Ask your ESP explicitly: "Does this include all open/click events, or only unique/filtered events?" |

**If your ESP batches timestamps or rounds to the minute**, the default thresholds in Honest Opens may not work well. You will likely need to widen the bot detection windows. See [CALIBRATION.md](CALIBRATION.md) for guidance on adjusting thresholds.

---

## Minimum Data Requirements

To get meaningful results from Honest Opens, you need:

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Sends | 1,000+ | 10,000+ |
| Time period | 1 week | 30+ days |
| Open events | All raw events (not deduplicated) | — |
| Click events | All raw events with URLs | — |
| Timestamp precision | Seconds | Seconds |

The algorithm works best with more data. User history (has this subscriber ever had a verified open?) improves accuracy over time, so processing 30+ days of data in chronological order gives the best results.

---

## Quick Start After Getting Your Data

Once you have your three CSV files:

```bash
# Install
pip install honest-opens

# Run the benchmark to see your bot rates
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

If your column names differ from the defaults, use the `--subscriber-col`, `--campaign-col`, `--nhi-col`, and `--url-col` flags. See the main [README](../README.md) for full usage.
