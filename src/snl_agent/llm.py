"""The single call site for Ollama. Nothing else in this package may talk HTTP.

Keeping one choke point means retries, timeouts, thinking-token stripping and
error messages are handled once, and tests only ever need to patch
``snl_agent.llm.generate``.
"""

import re

import requests

from . import config, usage


class LLMError(RuntimeError):
    """Raised when the model could not be reached or returned an error."""


# Qwen3-family models emit reasoning in <think>...</think>. We ask Ollama to
# disable thinking, but strip it defensively in case the server ignores us or
# the model leaks the tags into the body.
_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_DANGLING_THINK = re.compile(r"^.*?</think\s*>", re.DOTALL | re.IGNORECASE)


def strip_thinking(text: str) -> str:
    """Remove reasoning blocks a thinking model may prepend to its answer."""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text.lower():
        # An unclosed opening tag was truncated away; drop everything up to
        # the closing tag and keep the real answer that follows.
        text = _DANGLING_THINK.sub("", text)
    return text.strip()


def generate(
    prompt: str,
    model: str | None = None,
    *,
    system: str | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
    task: str | None = None,
) -> str:
    """Send one non-streaming completion request to Ollama and return the text.

    Raises :class:`LLMError` on connection failure, HTTP error, or a malformed
    response body.
    """
    model = model or config.MODEL
    url = f"{config.OLLAMA_URL}/api/generate"
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {
            "temperature": config.TEMPERATURE if temperature is None else temperature,
        },
    }
    if system:
        payload["system"] = system

    timer = usage.Timer()
    text, body = _post(url, payload, timeout)
    usage.record(
        "call",
        task=task,
        model=model,
        prompt_tokens=body.get("prompt_eval_count") or 0,
        response_tokens=body.get("eval_count") or 0,
        seconds=timer.seconds,
    )
    return strip_thinking(text)


def _post(url: str, payload: dict, timeout: float | None) -> tuple[str, dict]:
    timeout = config.TIMEOUT if timeout is None else timeout
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise LLMError(
            f"Cannot reach Ollama at {config.OLLAMA_URL}. "
            "Is it running? Try: ollama serve"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise LLMError(
            f"Ollama did not respond within {timeout:.0f}s. "
            "Raise SNL_AGENT_TIMEOUT or use a smaller input."
        ) from exc

    if resp.status_code == 400 and "think" in resp.text.lower() and "think" in payload:
        # Model or server build does not accept the `think` parameter.
        payload = {k: v for k, v in payload.items() if k != "think"}
        return _post(url, payload, timeout)

    if resp.status_code >= 400:
        detail = resp.text.strip()[:500]
        if resp.status_code == 404:
            detail += (
                f"\nIs the model pulled? Try: ollama pull {payload.get('model')}"
            )
        raise LLMError(f"Ollama returned HTTP {resp.status_code}: {detail}")

    try:
        body = resp.json()
    except ValueError as exc:
        raise LLMError(f"Ollama returned a non-JSON body: {resp.text[:200]}") from exc

    response = body.get("response")
    if not isinstance(response, str):
        raise LLMError(f"Ollama response had no 'response' field: {body!r}")
    return response, body
