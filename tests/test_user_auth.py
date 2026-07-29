import app as web_app
import pytest
import user_auth


@pytest.fixture
def gated(monkeypatch):
    """Drive the app with the gate live, as production runs it."""
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "rosetta-test")
    user_auth.reset_state()
    web_app.app.config["TESTING"] = True
    web_app.app.config["SKIP_USER_AUTH"] = False
    web_app.reset_state()
    with web_app.app.test_client() as c:
        yield c
    web_app.app.config["SKIP_USER_AUTH"] = True
    user_auth.reset_state()


PAID = ["/api/translate", "/api/chat", "/api/write", "/api/practice", "/api/expression"]


@pytest.mark.parametrize("path", PAID)
def test_paid_endpoints_reject_anonymous_calls(gated, path):
    # Each of these spends Groq quota, and each answered a plain curl before.
    resp = gated.post(path, json={"text": "hi", "message": "hi", "language": "es"})
    assert resp.status_code == 401
    assert "sign in" in resp.get_json()["error"]


@pytest.mark.parametrize("path", PAID)
def test_forged_token_is_rejected(gated, path):
    resp = gated.post(
        path,
        json={"text": "hi", "message": "hi", "language": "es"},
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert resp.status_code == 401


def test_config_stays_open(gated):
    # The client cannot hold a token before it has read the config.
    assert gated.get("/api/config").status_code == 200


def test_scenarios_stay_open(gated):
    assert gated.get("/api/practice/scenarios").status_code == 200


def test_page_stays_open(gated):
    assert gated.get("/").status_code == 200


def test_admin_paths_are_not_covered_by_this_gate(gated):
    # They have their own, stricter one; this must not shadow it.
    assert web_app._requires_user("/api/admin/analytics") is False


def test_gate_fails_open_without_firebase(monkeypatch):
    # A deployment with no Firebase cannot verify anyone. Failing closed there
    # would brick the whole app rather than protect it -- the opposite trade to
    # admin_auth, where the risk is data access rather than a broken app.
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    assert user_auth.is_enforceable() is False
    web_app.app.config["TESTING"] = True
    web_app.app.config["SKIP_USER_AUTH"] = False
    web_app.reset_state()
    try:
        with web_app.app.test_client() as c:
            # Reaches the handler rather than being turned away at the gate.
            assert c.post("/api/translate", json={}).status_code != 401
    finally:
        web_app.app.config["SKIP_USER_AUTH"] = True


# ─── Token verification ─────────────────────────────────────────────────────


def test_verify_rejects_junk(monkeypatch):
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "rosetta-test")
    user_auth.reset_state()
    assert user_auth.verify("not.a.token") is None
    assert user_auth.verify("") is None
    assert user_auth.verify(None) is None


def test_verify_is_disabled_without_a_project_id(monkeypatch):
    monkeypatch.delenv("FIREBASE_PROJECT_ID", raising=False)
    user_auth.reset_state()
    assert user_auth.verify("anything") is None


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc", "abc"),
        ("Bearer  abc  ", "abc"),
        ("Bearer ", None),
        ("Basic abc", None),
        ("", None),
    ],
)
def test_bearer_token_parsing(header, expected):
    assert user_auth.bearer_token(header) == expected
