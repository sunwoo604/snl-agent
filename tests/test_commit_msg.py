import pytest

from snl_agent.tasks.commit_msg import clean, generate_commit_msg, validate_message

DIFF = """\
diff --git a/src/cache.py b/src/cache.py
@@ -1,3 +1,7 @@
+def get(key):
+    return _store.get(key)
"""


@pytest.mark.parametrize(
    "message",
    [
        "feat: add caching",
        "fix(auth): reject expired tokens",
        "refactor(api/v2): split the router",
        "feat(db)!: drop the legacy column",
        "chore: bump deps\n\nThe pinned version had a CVE.",
    ],
)
def test_validate_accepts_conventional_messages(message):
    ok, reason = validate_message(message)
    assert ok, reason


@pytest.mark.parametrize(
    "message, expected_reason",
    [
        ("", "empty"),
        ("added caching", "does not match"),
        ("feature: add caching", "does not match"),
        ("feat add caching", "does not match"),
        ("feat:", "does not match"),
        ("feat: add caching.", "period"),
        ("feat: " + "x" * 80, "limit"),
        ("feat: add caching\nno blank line", "blank line"),
    ],
)
def test_validate_rejects_bad_messages(message, expected_reason):
    ok, reason = validate_message(message)
    assert not ok
    assert expected_reason in reason


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("feat: add caching", "feat: add caching"),
        ("```\nfeat: add caching\n```", "feat: add caching"),
        ("```text\nfeat: add caching\n```", "feat: add caching"),
        ('"feat: add caching"', "feat: add caching"),
        ("Message: feat: add caching", "feat: add caching"),
        ("Message:\n\nfeat: add caching", "feat: add caching"),
        ("  feat: add caching  \n", "feat: add caching"),
    ],
)
def test_clean_strips_model_wrappers(raw, expected):
    assert clean(raw) == expected


def test_clean_keeps_a_body_intact():
    assert clean("```\nfix: x\n\nbecause y\n```") == "fix: x\n\nbecause y"


def test_returns_first_valid_message(fake_llm):
    fake = fake_llm("feat(cache): add key lookup")
    result = generate_commit_msg(DIFF)

    assert result.ok
    assert result.attempts == 1
    assert result.value == "feat(cache): add key lookup"
    assert fake.call_count == 1


def test_retries_until_valid_and_feeds_back_the_reason(fake_llm):
    fake = fake_llm("added a getter", "feat(cache): add key lookup")
    result = generate_commit_msg(DIFF)

    assert result.ok
    assert result.attempts == 2
    assert result.value == "feat(cache): add key lookup"
    assert fake.call_count == 2
    # The second prompt must tell the model why the first was rejected.
    assert "rejected" in fake.prompts[1]
    assert "does not match" in fake.prompts[1]


def test_returns_best_effort_after_exhausting_attempts(fake_llm):
    fake = fake_llm("nope, not a commit message")
    result = generate_commit_msg(DIFF, attempts=3)

    assert not result.ok
    assert result.attempts == 3
    assert fake.call_count == 3
    assert result.value == "nope, not a commit message"
    assert "does not match" in result.error


def test_attempt_budget_is_respected(fake_llm):
    fake = fake_llm("garbage")
    result = generate_commit_msg(DIFF, attempts=1)

    assert not result.ok
    assert fake.call_count == 1


def test_empty_diff_is_rejected_without_calling_the_model(fake_llm):
    fake = fake_llm("feat: nothing")
    with pytest.raises(ValueError, match="empty"):
        generate_commit_msg("   \n")
    assert fake.call_count == 0


def test_diff_is_included_in_the_prompt(fake_llm):
    fake = fake_llm("feat(cache): add key lookup")
    generate_commit_msg(DIFF)
    assert "src/cache.py" in fake.prompts[0]
