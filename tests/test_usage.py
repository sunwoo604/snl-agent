"""Usage log: recording from llm/verify, tolerant reading, and the stats command."""

import json
from datetime import datetime, timedelta

import pytest
from typer.testing import CliRunner

from snl_agent import config, llm, usage
from snl_agent.cli import app
from snl_agent.verify import run_with_retry

runner = CliRunner()


class FakeResponse:
    status_code = 200
    text = ""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


def test_llm_generate_records_tokens_and_task(monkeypatch):
    body = {"response": "hi", "prompt_eval_count": 120, "eval_count": 7}
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: FakeResponse(body))

    assert llm.generate("p", task="commit-msg") == "hi"

    (entry,) = usage.read()
    assert entry["kind"] == "call"
    assert entry["task"] == "commit-msg"
    assert (entry["prompt_tokens"], entry["response_tokens"]) == (120, 7)


def test_missing_token_counts_record_as_zero(monkeypatch):
    monkeypatch.setattr(
        llm.requests, "post", lambda *a, **k: FakeResponse({"response": "hi"})
    )
    llm.generate("p", task="convert")
    assert usage.read()[0]["prompt_tokens"] == 0


def test_run_with_retry_records_outcome_only_when_named():
    run_with_retry(lambda fb: "x", lambda v: True)
    assert usage.read() == []

    run_with_retry(lambda fb: "x", lambda v: False, attempts=2, task="convert")
    (entry,) = usage.read()
    assert (entry["kind"], entry["ok"], entry["attempts"]) == ("run", False, 2)


def test_disabled_records_nothing(monkeypatch):
    monkeypatch.setattr(config, "USAGE_ENABLED", False)
    usage.record("run", task="convert", ok=True, attempts=1)
    assert not usage.log_path().exists()


def test_unwritable_log_never_raises(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setattr(config, "DATA_DIR", blocker / "sub")
    usage.record("run", task="convert", ok=True, attempts=1)  # must not raise


def test_read_skips_corrupt_lines():
    usage.record("run", task="convert", ok=True, attempts=1)
    with open(usage.log_path(), "a") as f:
        f.write("not json\n\n[1, 2]\n{\"kind\": \"run\"}\n")
    assert len(usage.read()) == 1


def test_summarize_aggregates_per_task_and_honours_window():
    old = (datetime.now().astimezone() - timedelta(days=30)).isoformat()
    usage.log_path().parent.mkdir(parents=True)
    usage.log_path().write_text(
        json.dumps({"ts": old, "kind": "run", "task": "convert", "ok": True, "attempts": 1})
        + "\n"
    )
    usage.record("call", task="convert", prompt_tokens=100, response_tokens=10, seconds=2)
    usage.record("call", task="convert", prompt_tokens=50, response_tokens=5, seconds=4)
    usage.record("run", task="convert", ok=False, attempts=3)
    usage.record("run", task="convert", ok=True, attempts=1)

    week = usage.summarize(7).tasks["convert"]
    assert (week.calls, week.prompt_tokens, week.response_tokens) == (2, 150, 15)
    assert week.pass_rate == 0.5 and week.avg_attempts == 2 and week.avg_seconds == 3

    assert usage.summarize(None).tasks["convert"].runs == 3


def test_stats_on_empty_log_says_so():
    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0
    assert "No local-model usage" in result.stdout


def test_stats_table_and_json():
    usage.record("call", task="commit-msg", prompt_tokens=1234, response_tokens=20, seconds=1)
    usage.record("run", task="commit-msg", ok=True, attempts=1)

    table = runner.invoke(app, ["stats"])
    assert table.exit_code == 0
    assert "commit-msg" in table.stdout and "1,234" in table.stdout and "100%" in table.stdout

    data = json.loads(runner.invoke(app, ["stats", "--json"]).stdout)
    assert data["tasks"]["commit-msg"]["prompt_tokens"] == 1234
    assert data["total"]["pass_rate"] == 1.0


def test_a_real_task_run_shows_up_in_stats(fake_llm):
    fake_llm("feat(a): add x")
    runner.invoke(app, ["commit-msg"], input="diff --git a/a b/a\n+x\n")
    data = json.loads(runner.invoke(app, ["stats", "--json"]).stdout)
    assert data["tasks"]["commit-msg"]["runs"] == 1  # FakeLLM bypasses call records
    assert data["tasks"]["commit-msg"]["calls"] == 0
