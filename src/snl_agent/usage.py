"""Local usage log: what the model was asked, and how often it got it right.

Two kinds of line are appended to ``<data dir>/usage.jsonl``:

* ``call`` — one Ollama request (tokens in/out, latency), written by ``llm``.
* ``run``  — one verify-and-retry run (passed or not, attempts), written by
  ``verify.run_with_retry``.

Recording is best-effort and never raises: a full disk must not fail a commit
message. Reading tolerates blank and corrupt lines for the same reason.
"""

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from . import config


def log_path() -> Path:
    return config.DATA_DIR / "usage.jsonl"


def record(kind: str, **fields: Any) -> None:
    """Append one entry. Silently does nothing if disabled or unwritable."""
    if not config.USAGE_ENABLED:
        return
    entry = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), "kind": kind}
    entry.update(fields)
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def read(since: datetime | None = None) -> list[dict]:
    """Return logged entries (oldest first), optionally only those after ``since``."""
    try:
        lines = log_path().read_text().splitlines()
    except OSError:
        return []

    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["ts"])
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(entry, dict):
            continue
        if since is None or ts >= since:
            entries.append(entry)
    return entries


@dataclass
class TaskStats:
    calls: int = 0
    prompt_tokens: int = 0
    response_tokens: int = 0
    seconds: float = 0.0
    runs: int = 0
    passed: int = 0
    attempts: int = 0

    @property
    def pass_rate(self) -> float | None:
        return self.passed / self.runs if self.runs else None

    @property
    def avg_attempts(self) -> float | None:
        return self.attempts / self.runs if self.runs else None

    @property
    def avg_seconds(self) -> float | None:
        return self.seconds / self.calls if self.calls else None


@dataclass
class Summary:
    days: int | None
    tasks: dict[str, TaskStats] = field(default_factory=dict)

    @property
    def total(self) -> TaskStats:
        total = TaskStats()
        for stats in self.tasks.values():
            for name in vars(total):
                setattr(total, name, getattr(total, name) + getattr(stats, name))
        return total


def summarize(days: int | None = None) -> Summary:
    """Aggregate the log per task over the last ``days`` days (all time if None)."""
    since = None
    if days is not None:
        since = datetime.now().astimezone() - timedelta(days=days)

    summary = Summary(days=days)
    for entry in read(since):
        stats = summary.tasks.setdefault(str(entry.get("task") or "unknown"), TaskStats())
        if entry.get("kind") == "call":
            stats.calls += 1
            stats.prompt_tokens += int(entry.get("prompt_tokens") or 0)
            stats.response_tokens += int(entry.get("response_tokens") or 0)
            stats.seconds += float(entry.get("seconds") or 0)
        elif entry.get("kind") == "run":
            stats.runs += 1
            stats.passed += bool(entry.get("ok"))
            stats.attempts += int(entry.get("attempts") or 0)
    return summary


class Timer:
    """Tiny helper so call sites read ``t = Timer(); ...; t.seconds``."""

    def __init__(self) -> None:
        self._start = time.monotonic()

    @property
    def seconds(self) -> float:
        return round(time.monotonic() - self._start, 3)
