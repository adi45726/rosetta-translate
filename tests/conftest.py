import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Run every test as if no Groq key existed.

    `web/app.py` loads the developer's real `.env` at import time, which would
    otherwise make the suite's behaviour depend on whether the machine running
    it happens to have a key -- different max_text_length, different provider.
    Tests that want the Groq path set the variable themselves. Safe to do
    per-test because every read of the key goes through `groq_client.api_key()`
    at call time rather than being captured at import.
    """
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
