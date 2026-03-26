"""
Honest Opens — Quick Start Example

This example generates synthetic email engagement data and runs it through
the classifier to demonstrate how the algorithm works.

In production, you would replace the synthetic data with real event exports
from your ESP. See docs/ESP_DATA_GUIDE.md for instructions.
"""

import random
import time
from honest_opens import HonestFilter
from honest_opens.models import SendRecord, OpenEvent, ClickEvent
from honest_opens.benchmark import benchmark


def generate_synthetic_data(num_subscribers=100, num_campaigns=5):
    """Generate realistic synthetic email engagement data.

    This creates a mix of:
    - Human readers who open and occasionally click
    - Bot scanners that instant-click everything
    - Apple Mail Privacy users with double-open patterns
    - Inactive subscribers with no engagement
    """
    sends = []
    opens = []
    clicks = []

    base_time = time.time() - 86400 * 7  # 1 week ago

    for camp_idx in range(num_campaigns):
        campaign_id = f"campaign_{camp_idx + 1}"
        send_time = base_time + camp_idx * 86400  # One campaign per day

        for sub_idx in range(num_subscribers):
            subscriber_id = f"sub_{sub_idx + 1}"
            sends.append(SendRecord(
                subscriber_id=subscriber_id,
                campaign_id=campaign_id,
                send_timestamp=send_time,
            ))

            roll = random.random()

            # 30% — Human reader, opens and maybe clicks
            if roll < 0.30:
                # Human open: delayed, sometimes multiple
                open_delay = random.uniform(300, 86400)  # 5min to 24hrs
                opens.append(OpenEvent(
                    subscriber_id=subscriber_id,
                    campaign_id=campaign_id,
                    open_timestamp=send_time + open_delay,
                ))
                # 40% chance of a re-open hours later
                if random.random() < 0.4:
                    opens.append(OpenEvent(
                        subscriber_id=subscriber_id,
                        campaign_id=campaign_id,
                        open_timestamp=send_time + open_delay + random.uniform(3600, 43200),
                    ))
                # 30% chance of a human click
                if random.random() < 0.3:
                    clicks.append(ClickEvent(
                        subscriber_id=subscriber_id,
                        campaign_id=campaign_id,
                        click_timestamp=send_time + open_delay + random.uniform(10, 300),
                        url=f"https://example.com/article-{random.randint(1, 3)}",
                    ))

            # 25% — Apple Mail Privacy (auto-open, no click)
            elif roll < 0.55:
                # Instant NHI open
                opens.append(OpenEvent(
                    subscriber_id=subscriber_id,
                    campaign_id=campaign_id,
                    open_timestamp=send_time + random.uniform(2, 10),
                    is_nhi=True,
                ))

            # 20% — Bot scanner (instant clicks on everything)
            elif roll < 0.75:
                # Bot open
                opens.append(OpenEvent(
                    subscriber_id=subscriber_id,
                    campaign_id=campaign_id,
                    open_timestamp=send_time + random.uniform(1, 5),
                ))
                # Machinegun clicks on all links
                click_start = send_time + random.uniform(2, 8)
                for url_idx in range(random.randint(4, 8)):
                    clicks.append(ClickEvent(
                        subscriber_id=subscriber_id,
                        campaign_id=campaign_id,
                        click_timestamp=click_start + url_idx * random.uniform(0.05, 0.3),
                        url=f"https://example.com/link-{url_idx + 1}",
                    ))

            # 25% — No engagement (didn't open)
            # No events generated

    return sends, opens, clicks


def main():
    print("=" * 60)
    print("HONEST OPENS — QUICK START EXAMPLE")
    print("=" * 60)
    print()

    # Generate synthetic data
    print("Generating synthetic data (100 subscribers, 5 campaigns)...")
    sends, opens, clicks = generate_synthetic_data()
    print(f"  {len(sends):,} sends")
    print(f"  {len(opens):,} open events")
    print(f"  {len(clicks):,} click events")
    print()

    # Classify
    print("Running classification...")
    hf = HonestFilter()
    results = hf.classify(sends, opens, clicks)

    # Summary
    human_opens = sum(1 for r in results if r.unique_open)
    raw_opens = sum(1 for r in results if r.raw_open_events > 0)
    human_clicks = sum(1 for r in results if r.unique_click)
    raw_clicks = sum(1 for r in results if r.raw_click_events > 0)

    print(f"  Human opens:  {human_opens:,} / {raw_opens:,} raw "
          f"({human_opens / len(sends):.1%} open rate)")
    print(f"  Human clicks: {human_clicks:,} / {raw_clicks:,} raw "
          f"({human_clicks / len(sends):.1%} CTR)")
    print(f"  Bot opens filtered:  {raw_opens - human_opens:,} "
          f"({(raw_opens - human_opens) / max(raw_opens, 1):.0%})")
    print(f"  Bot clicks filtered: {raw_clicks - human_clicks:,} "
          f"({(raw_clicks - human_clicks) / max(raw_clicks, 1):.0%})")
    print()

    # Show some individual results
    print("Sample classifications:")
    for r in results[:10]:
        if r.raw_open_events > 0 or r.raw_click_events > 0:
            print(f"  {r.subscriber_id} / {r.campaign_id}:")
            print(f"    Open:  {r.open_classification.label} "
                  f"(human={r.unique_open}, prob={r.open_classification.probability})")
            print(f"    Click: {r.click_classification.label} "
                  f"(human={r.unique_click}, prob={r.click_classification.probability})")
    print()

    # Campaign reports
    print("Campaign reports:")
    reports = hf.report(results)
    for cid, report in sorted(reports.items()):
        print(f"  {cid}: {report.open_rate:.1%} open rate, "
              f"{report.click_rate:.1%} CTR "
              f"(raw: {report.raw_open_rate:.1%} / {report.raw_click_rate:.1%})")
    print()

    # Benchmark
    print("Running benchmark...")
    bench = benchmark(results)
    print(bench.summary())


if __name__ == "__main__":
    main()
