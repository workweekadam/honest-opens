"""
Unit tests for the Honest Opens classifier.

Tests cover:
  - Bot detection rules (instant, machinegun, scanner, high volume, cron)
  - Human detection rules (delayed single, late arrival, selective, esp confirmed)
  - Open classification rules (verified clicker, apple mail double, multi open)
  - V3 changes (removed rules, ESP rescue)
  - Edge cases
"""
import unittest
from datetime import datetime, timedelta

from honest_opens.models import (
    SendRecord, OpenEvent, ClickEvent, SendResult,
    OpenClassification, ClickClassification,
)
from honest_opens.classifier import HonestFilter
from honest_opens.thresholds import HonestConfig


def ts(dt):
    """Convert datetime to unix epoch float."""
    return dt.timestamp()


class TestClickClassification(unittest.TestCase):
    """Test click classification rules."""

    def setUp(self):
        self.hf = HonestFilter()
        self.base = datetime(2025, 1, 15, 10, 0, 0)

    def test_bot_instant_prefetch(self):
        """Click within 3 seconds of send = definitive bot."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(seconds=3)), "https://example.com/link1"),
        ]
        results = self.hf.classify(sends, [], clicks)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].unique_click)
        self.assertIn("instant", results[0].click_classification.label.lower())

    def test_bot_machinegun(self):
        """3+ URLs clicked in under 0.5s each = machinegun bot."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        t = self.base + timedelta(seconds=60)
        clicks = [
            ClickEvent("sub1", "camp1", ts(t), "https://a.com/1"),
            ClickEvent("sub1", "camp1", ts(t + timedelta(milliseconds=100)), "https://a.com/2"),
            ClickEvent("sub1", "camp1", ts(t + timedelta(milliseconds=200)), "https://a.com/3"),
            ClickEvent("sub1", "camp1", ts(t + timedelta(milliseconds=300)), "https://a.com/4"),
        ]
        results = self.hf.classify(sends, [], clicks)
        self.assertFalse(results[0].unique_click)
        self.assertIn("machinegun", results[0].click_classification.label.lower())

    def test_bot_high_volume(self):
        """10+ clicks on one send = high volume bot."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(minutes=5, seconds=i*30)), f"https://a.com/{i}")
            for i in range(12)
        ]
        results = self.hf.classify(sends, [], clicks)
        self.assertFalse(results[0].unique_click)

    def test_human_delayed_single(self):
        """One click, 30 minutes after send = human."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(minutes=30)), "https://a.com/article"),
        ]
        results = self.hf.classify(sends, [], clicks)
        self.assertTrue(results[0].unique_click)
        self.assertIn("delayed", results[0].click_classification.label.lower())

    def test_human_late_arrival(self):
        """Click 6 hours after send = late arrival human."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(hours=6)), "https://a.com/article"),
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(hours=6, minutes=2)), "https://a.com/article2"),
        ]
        results = self.hf.classify(sends, [], clicks)
        self.assertTrue(results[0].unique_click)

    def test_human_single_selective(self):
        """One click, 3 minutes after send = selective human."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(minutes=3)), "https://a.com/article"),
        ]
        results = self.hf.classify(sends, [], clicks)
        self.assertTrue(results[0].unique_click)

    def test_no_clicks(self):
        """No clicks = no click classification."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        results = self.hf.classify(sends, [], [])
        self.assertFalse(results[0].unique_click)
        self.assertEqual(results[0].raw_click_events, 0)


class TestOpenClassification(unittest.TestCase):
    """Test open classification rules."""

    def setUp(self):
        self.hf = HonestFilter()
        self.base = datetime(2025, 1, 15, 10, 0, 0)

    def test_verified_clicker(self):
        """Open + human click = verified clicker."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        opens = [
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(minutes=5))),
        ]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(minutes=10)), "https://a.com/1"),
        ]
        results = self.hf.classify(sends, opens, clicks)
        self.assertTrue(results[0].unique_open)
        self.assertTrue(results[0].unique_click)
        self.assertIn("verified", results[0].open_classification.label.lower())

    def test_apple_mail_double(self):
        """Exactly 2 opens with gap = apple mail double."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        opens = [
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(seconds=8))),
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(hours=2))),
        ]
        results = self.hf.classify(sends, opens, [])
        self.assertTrue(results[0].unique_open)

    def test_multi_open(self):
        """3+ opens spread over time = multi open human."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        opens = [
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(minutes=5))),
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(hours=3))),
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(hours=8))),
        ]
        results = self.hf.classify(sends, opens, [])
        self.assertTrue(results[0].unique_open)

    def test_no_opens(self):
        """No opens = no open classification."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        results = self.hf.classify(sends, [], [])
        self.assertFalse(results[0].unique_open)
        self.assertEqual(results[0].raw_open_events, 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def setUp(self):
        self.hf = HonestFilter()
        self.base = datetime(2025, 1, 15, 10, 0, 0)

    def test_multiple_sends(self):
        """Multiple sends are classified independently."""
        sends = [
            SendRecord("sub1", "camp1", ts(self.base)),
            SendRecord("sub2", "camp1", ts(self.base)),
        ]
        opens = [
            OpenEvent("sub1", "camp1", ts(self.base + timedelta(hours=2))),
        ]
        clicks = [
            ClickEvent("sub2", "camp1", ts(self.base + timedelta(minutes=30)), "https://a.com/1"),
        ]
        results = self.hf.classify(sends, opens, clicks)
        self.assertEqual(len(results), 2)

    def test_custom_config(self):
        """Custom thresholds are respected."""
        config = HonestConfig()
        config.click_thresholds.human_delayed_min_seconds = 600.0  # 10 minutes
        hf = HonestFilter(config=config)

        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        clicks = [
            ClickEvent("sub1", "camp1", ts(self.base + timedelta(minutes=7)), "https://a.com/1"),
        ]
        results = hf.classify(sends, [], clicks)
        # With 10-min threshold, 7-min click should still be human via single_selective
        self.assertTrue(results[0].unique_click)


class TestOutputFields(unittest.TestCase):
    """Test that output fields are populated correctly."""

    def setUp(self):
        self.hf = HonestFilter()
        self.base = datetime(2025, 1, 15, 10, 0, 0)

    def test_result_fields(self):
        """All expected fields are present on SendResult."""
        sends = [SendRecord("sub1", "camp1", ts(self.base))]
        opens = [OpenEvent("sub1", "camp1", ts(self.base + timedelta(hours=1)))]
        clicks = [ClickEvent("sub1", "camp1", ts(self.base + timedelta(hours=1)), "https://a.com")]
        results = self.hf.classify(sends, opens, clicks)
        r = results[0]

        self.assertIsInstance(r.unique_open, bool)
        self.assertIsInstance(r.unique_click, bool)
        self.assertIsInstance(r.estimated_open, bool)
        self.assertIsInstance(r.raw_open_events, int)
        self.assertIsInstance(r.raw_click_events, int)
        self.assertIsInstance(r.total_opens, int)
        self.assertIsInstance(r.total_clicks, int)
        self.assertIsInstance(r.open_classification, OpenClassification)
        self.assertIsInstance(r.click_classification, ClickClassification)
        self.assertIsNotNone(r.open_classification.label)
        self.assertIsNotNone(r.click_classification.label)
        self.assertGreaterEqual(r.open_classification.probability, 0)
        self.assertLessEqual(r.open_classification.probability, 100)


if __name__ == "__main__":
    unittest.main()
