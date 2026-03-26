"""
I/O helpers for loading data from CSVs or DataFrames.

Most publishers will export data from their ESP as CSV. These helpers
convert that into the SendRecord / OpenEvent / ClickEvent objects
the classifier expects.
"""

import csv
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from honest_opens.models import SendRecord, OpenEvent, ClickEvent


# ─────────────────────────────────────────────────────────────────────
# TIMESTAMP PARSING
# ─────────────────────────────────────────────────────────────────────

def parse_timestamp(value: str) -> float:
    """Parse a timestamp string into Unix epoch seconds.

    Handles common ESP timestamp formats:
      - ISO 8601: "2025-07-15T14:30:00Z"
      - ISO with offset: "2025-07-15T14:30:00+00:00"
      - Date + time: "2025-07-15 14:30:00"
      - Unix epoch (numeric string): "1752587400"
    """
    if not value or not value.strip():
        raise ValueError(f"Empty timestamp: {value!r}")

    value = value.strip()

    # Already a numeric epoch
    try:
        epoch = float(value)
        if epoch > 1e12:  # Milliseconds
            epoch /= 1000.0
        return epoch
    except ValueError:
        pass

    # ISO 8601 variants
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue

    raise ValueError(
        f"Could not parse timestamp: {value!r}. "
        "Supported formats: ISO 8601, 'YYYY-MM-DD HH:MM:SS', or Unix epoch."
    )


# ─────────────────────────────────────────────────────────────────────
# CSV LOADERS
# ─────────────────────────────────────────────────────────────────────

def load_sends_csv(
    path: str,
    subscriber_col: str = "subscriber_id",
    campaign_col: str = "campaign_id",
    timestamp_col: str = "send_timestamp",
) -> List[SendRecord]:
    """Load send records from a CSV file.

    Args:
        path: Path to CSV file.
        subscriber_col: Column name for subscriber ID.
        campaign_col: Column name for campaign/blast ID.
        timestamp_col: Column name for send timestamp.

    Returns:
        List of SendRecord.
    """
    records = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(SendRecord(
                subscriber_id=row[subscriber_col].strip(),
                campaign_id=row[campaign_col].strip(),
                send_timestamp=parse_timestamp(row[timestamp_col]),
            ))
    return records


def load_opens_csv(
    path: str,
    subscriber_col: str = "subscriber_id",
    campaign_col: str = "campaign_id",
    timestamp_col: str = "open_timestamp",
    nhi_col: Optional[str] = None,
    user_agent_col: Optional[str] = None,
) -> List[OpenEvent]:
    """Load open events from a CSV file.

    Args:
        path: Path to CSV file.
        subscriber_col: Column name for subscriber ID.
        campaign_col: Column name for campaign/blast ID.
        timestamp_col: Column name for open event timestamp.
        nhi_col: Optional column for NHI/bot flag (True/False/"1"/"0").
        user_agent_col: Optional column for User-Agent string.

    Returns:
        List of OpenEvent.
    """
    events = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            is_nhi = None
            if nhi_col and nhi_col in row:
                val = row[nhi_col].strip().lower()
                is_nhi = val in ("true", "1", "yes", "nhi")

            ua = None
            if user_agent_col and user_agent_col in row:
                ua = row[user_agent_col].strip() or None

            events.append(OpenEvent(
                subscriber_id=row[subscriber_col].strip(),
                campaign_id=row[campaign_col].strip(),
                open_timestamp=parse_timestamp(row[timestamp_col]),
                is_nhi=is_nhi,
                user_agent=ua,
            ))
    return events


def load_clicks_csv(
    path: str,
    subscriber_col: str = "subscriber_id",
    campaign_col: str = "campaign_id",
    timestamp_col: str = "click_timestamp",
    url_col: Optional[str] = None,
    nhi_col: Optional[str] = None,
) -> List[ClickEvent]:
    """Load click events from a CSV file.

    Args:
        path: Path to CSV file.
        subscriber_col: Column name for subscriber ID.
        campaign_col: Column name for campaign/blast ID.
        timestamp_col: Column name for click event timestamp.
        url_col: Optional column for the clicked URL.
        nhi_col: Optional column for NHI/bot flag.

    Returns:
        List of ClickEvent.
    """
    events = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            is_nhi = None
            if nhi_col and nhi_col in row:
                val = row[nhi_col].strip().lower()
                is_nhi = val in ("true", "1", "yes", "nhi")

            url = None
            if url_col and url_col in row:
                url = row[url_col].strip() or None

            events.append(ClickEvent(
                subscriber_id=row[subscriber_col].strip(),
                campaign_id=row[campaign_col].strip(),
                click_timestamp=parse_timestamp(row[timestamp_col]),
                url=url,
                is_nhi=is_nhi,
            ))
    return events


# ─────────────────────────────────────────────────────────────────────
# PANDAS LOADERS (optional dependency)
# ─────────────────────────────────────────────────────────────────────

def from_dataframes(
    sends_df,
    opens_df,
    clicks_df,
    subscriber_col: str = "subscriber_id",
    campaign_col: str = "campaign_id",
    send_ts_col: str = "send_timestamp",
    open_ts_col: str = "open_timestamp",
    click_ts_col: str = "click_timestamp",
    nhi_col: Optional[str] = None,
    url_col: Optional[str] = None,
    user_agent_col: Optional[str] = None,
) -> Tuple[List[SendRecord], List[OpenEvent], List[ClickEvent]]:
    """Convert pandas DataFrames to Honest Opens input objects.

    This is a convenience wrapper for publishers who already have their
    data in DataFrames (e.g., from a SQL query or ESP API).
    """
    sends = []
    for _, row in sends_df.iterrows():
        ts = row[send_ts_col]
        if hasattr(ts, "timestamp"):
            ts = ts.timestamp()
        else:
            ts = parse_timestamp(str(ts))
        sends.append(SendRecord(
            subscriber_id=str(row[subscriber_col]),
            campaign_id=str(row[campaign_col]),
            send_timestamp=ts,
        ))

    open_events = []
    for _, row in opens_df.iterrows():
        ts = row[open_ts_col]
        if hasattr(ts, "timestamp"):
            ts = ts.timestamp()
        else:
            ts = parse_timestamp(str(ts))
        is_nhi = None
        if nhi_col and nhi_col in opens_df.columns:
            val = row[nhi_col]
            is_nhi = bool(val) if val is not None else None
        ua = None
        if user_agent_col and user_agent_col in opens_df.columns:
            ua = str(row[user_agent_col]) if row[user_agent_col] else None
        open_events.append(OpenEvent(
            subscriber_id=str(row[subscriber_col]),
            campaign_id=str(row[campaign_col]),
            open_timestamp=ts,
            is_nhi=is_nhi,
            user_agent=ua,
        ))

    click_events = []
    for _, row in clicks_df.iterrows():
        ts = row[click_ts_col]
        if hasattr(ts, "timestamp"):
            ts = ts.timestamp()
        else:
            ts = parse_timestamp(str(ts))
        is_nhi = None
        if nhi_col and nhi_col in clicks_df.columns:
            val = row[nhi_col]
            is_nhi = bool(val) if val is not None else None
        url = None
        if url_col and url_col in clicks_df.columns:
            url = str(row[url_col]) if row[url_col] else None
        click_events.append(ClickEvent(
            subscriber_id=str(row[subscriber_col]),
            campaign_id=str(row[campaign_col]),
            click_timestamp=ts,
            url=url,
            is_nhi=is_nhi,
        ))

    return sends, open_events, click_events
