"""
Command-line interface for Honest Opens.

Usage:
    python -m honest_opens classify --sends sends.csv --opens opens.csv --clicks clicks.csv
    python -m honest_opens benchmark --sends sends.csv --opens opens.csv --clicks clicks.csv
    python -m honest_opens init-config --output my_config.json
"""

import argparse
import json
import sys
from pathlib import Path

from honest_opens.classifier import HonestFilter
from honest_opens.thresholds import HonestConfig
from honest_opens.io import load_sends_csv, load_opens_csv, load_clicks_csv
from honest_opens.benchmark import benchmark


def main():
    parser = argparse.ArgumentParser(
        prog="honest-opens",
        description="Open-source bot filtering for newsletter engagement.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # ── classify ──
    cls_parser = subparsers.add_parser(
        "classify",
        help="Classify sends and output results as CSV.",
    )
    cls_parser.add_argument("--sends", required=True, help="Path to sends CSV")
    cls_parser.add_argument("--opens", required=True, help="Path to open events CSV")
    cls_parser.add_argument("--clicks", required=True, help="Path to click events CSV")
    cls_parser.add_argument("--config", help="Path to config JSON (optional)")
    cls_parser.add_argument("--output", default="results.csv", help="Output CSV path")
    cls_parser.add_argument(
        "--subscriber-col", default="subscriber_id",
        help="Column name for subscriber ID",
    )
    cls_parser.add_argument(
        "--campaign-col", default="campaign_id",
        help="Column name for campaign ID",
    )
    cls_parser.add_argument("--nhi-col", help="Column name for NHI/bot flag (optional)")
    cls_parser.add_argument("--url-col", help="Column name for clicked URL (optional)")

    # ── benchmark ──
    bench_parser = subparsers.add_parser(
        "benchmark",
        help="Run benchmark and print diagnostic report.",
    )
    bench_parser.add_argument("--sends", required=True, help="Path to sends CSV")
    bench_parser.add_argument("--opens", required=True, help="Path to open events CSV")
    bench_parser.add_argument("--clicks", required=True, help="Path to click events CSV")
    bench_parser.add_argument("--config", help="Path to config JSON (optional)")
    bench_parser.add_argument("--subscriber-col", default="subscriber_id")
    bench_parser.add_argument("--campaign-col", default="campaign_id")
    bench_parser.add_argument("--nhi-col", help="Column name for NHI/bot flag")
    bench_parser.add_argument("--url-col", help="Column name for clicked URL")

    # ── init-config ──
    cfg_parser = subparsers.add_parser(
        "init-config",
        help="Generate a default config JSON file you can customize.",
    )
    cfg_parser.add_argument(
        "--output", default="honest_opens_config.json",
        help="Output path for config file",
    )
    cfg_parser.add_argument(
        "--profile", default="strict",
        choices=["strict", "moderate", "permissive"],
        help="Starting profile (strict=~3%% FP, moderate=~10%%, permissive=~20%%)",
    )

    args = parser.parse_args()

    if args.command == "classify":
        _run_classify(args)
    elif args.command == "benchmark":
        _run_benchmark(args)
    elif args.command == "init-config":
        _run_init_config(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_classify(args):
    config = HonestConfig.load(args.config) if args.config else HonestConfig()
    hf = HonestFilter(config=config)

    print(f"Loading sends from {args.sends}...")
    sends = load_sends_csv(args.sends, args.subscriber_col, args.campaign_col)
    print(f"Loading opens from {args.opens}...")
    opens = load_opens_csv(
        args.opens, args.subscriber_col, args.campaign_col,
        nhi_col=args.nhi_col,
    )
    print(f"Loading clicks from {args.clicks}...")
    clicks = load_clicks_csv(
        args.clicks, args.subscriber_col, args.campaign_col,
        nhi_col=args.nhi_col, url_col=args.url_col,
    )

    print(f"Classifying {len(sends):,} sends...")
    results = hf.classify(sends, opens, clicks)

    # Write results CSV
    import csv
    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "subscriber_id", "campaign_id",
            "unique_open", "total_opens", "estimated_open",
            "open_classification", "open_confidence", "open_probability",
            "unique_click", "total_clicks",
            "click_classification", "click_confidence", "click_probability",
            "raw_open_events", "raw_click_events",
        ])
        for r in results:
            writer.writerow([
                r.subscriber_id, r.campaign_id,
                r.unique_open, r.total_opens, r.estimated_open,
                r.open_classification.label, r.open_classification.confidence,
                r.open_classification.probability,
                r.unique_click, r.total_clicks,
                r.click_classification.label, r.click_classification.confidence,
                r.click_classification.probability,
                r.raw_open_events, r.raw_click_events,
            ])

    print(f"Results written to {args.output}")
    print(f"  {sum(1 for r in results if r.unique_open):,} human opens "
          f"/ {sum(1 for r in results if r.raw_open_events > 0):,} raw opens")
    print(f"  {sum(1 for r in results if r.unique_click):,} human clicks "
          f"/ {sum(1 for r in results if r.raw_click_events > 0):,} raw clicks")


def _run_benchmark(args):
    config = HonestConfig.load(args.config) if args.config else HonestConfig()
    hf = HonestFilter(config=config)

    print(f"Loading data...")
    sends = load_sends_csv(args.sends, args.subscriber_col, args.campaign_col)
    opens = load_opens_csv(
        args.opens, args.subscriber_col, args.campaign_col,
        nhi_col=args.nhi_col,
    )
    clicks = load_clicks_csv(
        args.clicks, args.subscriber_col, args.campaign_col,
        nhi_col=args.nhi_col, url_col=args.url_col,
    )

    print(f"Classifying {len(sends):,} sends...")
    results = hf.classify(sends, opens, clicks)

    report = benchmark(results)
    print(report.summary())


def _run_init_config(args):
    from honest_opens.thresholds import PROFILES
    profile = PROFILES.get(args.profile, PROFILES["strict"])
    config = profile["config"]() if callable(profile["config"]) else profile["config"]()
    config.save(args.output)
    print(f"Config written to {args.output} (profile: {args.profile})")
    print(f"Edit the JSON to customize thresholds for your ESP.")


if __name__ == "__main__":
    main()
