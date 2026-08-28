import pytest

from snl_agent.verify import (
    Invalid,
    run_with_retry,
    strip_code_fence,
    strip_wrapping_quotes,
)


def test_returns_on_the_first_valid_result():
    calls = []
    result = run_with_retry(lambda fb: calls.append(fb) or "good", lambda v: True)

    assert result.ok
    assert result.attempts == 1
    assert result.value == "good"
    assert calls == [None]


def test_feeds_the_failure_reason_into_the_next_attempt():
    seen = []

    def fn(feedback):
        seen.append(feedback)
        return "bad" if feedback is None else "good"

    result = run_with_retry(fn, lambda v: (v == "good", "wanted good"))

    assert result.ok
    assert result.attempts == 2
    assert seen == [None, "wanted good"]


def test_returns_best_effort_after_the_budget():
    result = run_with_retry(lambda fb: "bad", lambda v: (False, "nope"), attempts=3)

    assert not result.ok
    assert result.attempts == 3
    assert result.value == "bad"
    assert result.errors == ["nope", "nope", "nope"]
    assert result.error == "nope"


def test_error_is_none_on_success():
    assert run_with_retry(lambda fb: 1, lambda v: True).error is None


@pytest.mark.parametrize("outcome", [True, None])
def test_validators_may_signal_success_as_true_or_none(outcome):
    assert run_with_retry(lambda fb: 1, lambda v: outcome).ok


def test_validators_may_raise_invalid():
    def validate(value):
        raise Invalid("bad shape")

    result = run_with_retry(lambda fb: 1, validate, attempts=1)
    assert not result.ok
    assert result.error == "bad shape"


def test_bare_false_gets_a_default_message():
    result = run_with_retry(lambda fb: 1, lambda v: False, attempts=1)
    assert result.error == "output failed validation"


def test_unsupported_validator_return_is_a_type_error():
    with pytest.raises(TypeError):
        run_with_retry(lambda fb: 1, lambda v: "maybe")


def test_attempts_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        run_with_retry(lambda fb: 1, lambda v: True, attempts=0)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("```\nbody\n```", "body"),
        ("```python\nbody\n```", "body"),
        ("  ```json\n{}\n```  ", "{}"),
        ("```\nline one\nline two\n```", "line one\nline two"),
        ("no fence", "no fence"),
        ("text with ``` inside", "text with ``` inside"),
    ],
)
def test_strip_code_fence(raw, expected):
    assert strip_code_fence(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [('"x"', "x"), ("'x'", "x"), ("`x`", "x"), ('"x', '"x'), ("x", "x"), ('""', "")],
)
def test_strip_wrapping_quotes(raw, expected):
    assert strip_wrapping_quotes(raw) == expected
