"""Configuration: model, endpoint, and defaults, all overridable by env var.

Read these as module attributes (``config.MODEL``) rather than importing the
names directly, so that tests and callers can monkeypatch them.
"""

import os
from pathlib import Path

#: Base URL of the Ollama server.
OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")

#: Ollama model tag used for every task.
MODEL: str = os.environ.get("MODEL", "qwen3.6:35b-a3b-coding-bf16")

#: Seconds to wait on a single generation. Local models on big diffs are slow.
TIMEOUT: float = float(os.environ.get("SNL_AGENT_TIMEOUT", "180"))

#: How many times a task may ask the model again before giving up.
ATTEMPTS: int = int(os.environ.get("SNL_AGENT_ATTEMPTS", "3"))

#: Sampling temperature. Low: these are constrained, checkable tasks.
TEMPERATURE: float = float(os.environ.get("SNL_AGENT_TEMPERATURE", "0.2"))

#: Cap on input text (chars) handed to the model, to stay inside context.
MAX_INPUT_CHARS: int = int(os.environ.get("SNL_AGENT_MAX_INPUT_CHARS", "12000"))

#: Where user data lives. Matches install.sh, so uninstall leaves it alone.
DATA_DIR: Path = Path(
    os.environ.get("SNL_AGENT_DATA")
    or Path(os.environ.get("SNL_AGENT_HOME", "~/.snl-agent")) / "data"
).expanduser()

#: Set SNL_AGENT_USAGE=0 to stop recording usage.
USAGE_ENABLED: bool = os.environ.get("SNL_AGENT_USAGE", "1") != "0"
