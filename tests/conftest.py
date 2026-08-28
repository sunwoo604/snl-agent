"""Shared test fixtures. The LLM is always mocked — the suite never needs Ollama."""

import pytest

from snl_agent import llm


class FakeLLM:
    """Stands in for ``llm.generate``, returning canned replies in order.

    The last reply is repeated indefinitely, so a single-reply fake is an
    "always answers the same thing" model.
    """

    def __init__(self, *replies: str):
        if not replies:
            raise ValueError("FakeLLM needs at least one reply")
        self.replies = list(replies)
        self.prompts: list[str] = []

    def __call__(self, prompt: str, model=None, **kwargs) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    @property
    def call_count(self) -> int:
        return len(self.prompts)


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a :class:`FakeLLM` in place of ``llm.generate``."""

    def install(*replies: str) -> FakeLLM:
        fake = FakeLLM(*replies)
        monkeypatch.setattr(llm, "generate", fake)
        return fake

    return install
