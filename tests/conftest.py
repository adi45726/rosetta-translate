import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Run every test as if the machine had no credentials of its own.

    `web/app.py` loads the developer's real `.env` at import time, which would
    otherwise make the suite's behaviour depend on what happens to be on the
    machine running it: a Groq key changes max_text_length and the provider, a
    Firebase project id switches on the sign-in gate and turns unrelated tests
    into 401s. Tests that want either path set the variable themselves.

    Safe to do per-test because every read goes through a function called at
    request time -- `groq_client.api_key()`, `user_auth.project_id()` -- rather
    than being captured at import.
    """
    for name in (
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "FIREBASE_PROJECT_ID",
        "ADMIN_PASSWORD_HASH",
        "SECRET_KEY",
        "STRIPE_RESTRICTED_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "APP_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
