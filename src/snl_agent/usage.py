"""Track token usage across sessions.

Append each LLM call to a JSONL file in the user's data directory
(~/.snl-agent/usage.jsonl or $XDG_DATA_HOME/snl-agent/usage.jsonl).
No rotation — at individual scale the file stays small enough to ignore.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass
class TokenUsage:
    """A single LLM call's token accounting."""

    timestamp: str
    task: str
    model: str
    prompt_tokens: int
    response_tokens: int
    total_tokens: int
    success: bool
    attempts: int


class UsageTracker:
    """Append token usage to a JSONL file and compute aggregates."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or self._default_path()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_path() -> Path:
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / "snl-agent" / "usage.jsonl"
        return Path.home() / ".snl-agent" / "usage.jsonl"

    def log(self, usage: TokenUsage) -> None:
        """Append one entry to the log file."""
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(usage)) + "\n")

    def daily_totals(self, target_date: date | None = None) -> dict[str, int]:
        """Return {task: total_tokens} for a given date."""
        target_date = target_date or date.today()
        prefix = target_date.isoformat()
        totals: dict[str, int] = {}
        if not self.log_path.exists():
            return totals
        with open(self.log_path) as f:
            for line in f:
                entry = json.loads(line)
                if entry["timestamp"].startswith(prefix):
                    task = entry["task"]
                    totals[task] = totals.get(task, 0) + entry["total_tokens"]
        return totals

    def weekly_totals(self, weeks_back: int = 4) -> dict[str, int]:
        """Return {task: total_tokens} for the last N weeks."""
        totals: dict[str, int] = {}
        if not self.log_path.exists():
            return totals
        cutoff = date.today()
        with open(self.log_path) as f:
            for line in f:
                entry = json.loads(line)
                entry_date = datetime.fromisoformat(entry["timestamp"]).date()
                if (date.today() - entry_date).days <= weeks_back * 7:
                    task = entry["task"]
                    totals[task] = totals.get(task, 0) + entry["total_tokens"]
        return totals

    def grand_total(self) -> int:
        """Return total tokens across all time."""
        total = 0
        if not self.log_path.exists():
            return total
        with open(self.log_path) as f:
            for line in f:
                entry = json.loads(line)
                total += entry["total_tokens"]
        return total
