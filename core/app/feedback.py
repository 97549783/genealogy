"""Storage helpers for application feedback messages."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEEDBACK_COLUMNS = ["timestamp", "name", "email", "message"]


def resolve_feedback_file() -> Path:
    """Return the feedback CSV path.

    If FEEDBACK_FILE_PATH is set, use it.

    Otherwise, fall back to:
        <project-root>/data-nonsynchronized/feedback.csv
    """
    configured = os.environ.get("FEEDBACK_FILE_PATH")
    if configured:
        return Path(configured).expanduser()

    return PROJECT_ROOT / "data-nonsynchronized" / "feedback.csv"


FEEDBACK_FILE = resolve_feedback_file()


def normalize_feedback_message(message: str) -> str:
    """Normalize line endings before writing the message to CSV."""
    return message.replace("\r\n", "\n").replace("\r", "\n")


def append_feedback(name: str, email: str, message: str) -> None:
    """Append a feedback message to the feedback CSV file."""
    FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

    file_exists = FEEDBACK_FILE.exists()
    record = [
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        name.strip(),
        email.strip(),
        normalize_feedback_message(message),
    ]

    with FEEDBACK_FILE.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        if not file_exists:
            writer.writerow(FEEDBACK_COLUMNS)
        writer.writerow(record)


def feedback_exists() -> bool:
    """Return True if the feedback CSV file exists."""
    return FEEDBACK_FILE.exists()


def load_feedback() -> pd.DataFrame:
    """Load feedback messages as a DataFrame."""
    if not FEEDBACK_FILE.exists():
        return pd.DataFrame(columns=FEEDBACK_COLUMNS)

    return pd.read_csv(FEEDBACK_FILE)
