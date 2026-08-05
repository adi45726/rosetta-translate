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


# ─── Guest limits, enforced where they cannot be edited away ────────────────


def _guest_claims():
    return {"sub": "guest-uid", "firebase": {"sign_in_provider": "anonymous"}}


def _member_claims():
    return {"sub": "member-uid", "firebase": {"sign_in_provider": "google.com"}}


@pytest.fixture
def as_guest(gated, monkeypatch):
    monkeypatch.setattr(user_auth, "verify", lambda token: _guest_claims())
    return gated


@pytest.fixture
def as_member(gated, monkeypatch):
    monkeypatch.setattr(user_auth, "verify", lambda token: _member_claims())
    return gated


AUTH = {"Authorization": "Bearer token"}
MEMBER_ONLY = ["/api/chat", "/api/practice", "/api/write", "/api/expression"]


@pytest.mark.parametrize("path", MEMBER_ONLY)
def test_guest_cannot_reach_member_features(as_guest, path):
    # The browser hides these from guests, but an anonymous token is one
    # unauthenticated call away -- confirmed against production.
    resp = as_guest.post(path, json={"message": "hi", "text": "hi", "language": "es"}, headers=AUTH)
    assert resp.status_code == 403
    assert "free account" in resp.get_json()["error"]


@pytest.mark.parametrize("path", MEMBER_ONLY)
def test_member_may_reach_member_features(as_member, path):
    resp = as_member.post(path, json={"message": "hi", "text": "hi", "language": "es"}, headers=AUTH)
    assert resp.status_code != 403


def test_guest_may_translate(as_guest):
    resp = as_guest.post("/api/translate", json={"text": "hi", "source": "en", "target": "es"}, headers=AUTH)
    assert resp.status_code != 403


def test_guest_translation_is_length_capped(as_guest):
    over = "x" * (web_app.GUEST_MAX_TEXT_LENGTH + 1)
    resp = as_guest.post("/api/translate", json={"text": over, "source": "en", "target": "es"}, headers=AUTH)
    assert resp.status_code == 403
    assert str(web_app.GUEST_MAX_TEXT_LENGTH) in resp.get_json()["error"]


def test_member_is_not_length_capped_at_the_guest_limit(as_member):
    over = "x" * (web_app.GUEST_MAX_TEXT_LENGTH + 1)
    resp = as_member.post("/api/translate", json={"text": over, "source": "en", "target": "es"}, headers=AUTH)
    assert resp.status_code != 403


# ─── Paid plan, read from the verified token ────────────────────────────────


def _pro_claims():
    return {"sub": "pro-uid", "firebase": {"sign_in_provider": "google.com"}, "plan": "pro"}


@pytest.fixture
def pro_enforced(monkeypatch):
    monkeypatch.setattr(web_app, "_PRO_ENFORCED", True)


PRO_ONLY = ["/api/chat", "/api/practice", "/api/write", "/api/expression"]


@pytest.mark.parametrize("path", PRO_ONLY)
def test_free_member_is_refused_pro_features_when_enforced(as_member, pro_enforced, path):
    resp = as_member.post(path, json={"message": "hi", "text": "hi", "language": "es"}, headers=AUTH)
    assert resp.status_code == 402
    assert resp.get_json()["upgrade"] is True


@pytest.mark.parametrize("path", PRO_ONLY)
def test_pro_member_may_use_pro_features(gated, pro_enforced, monkeypatch, path):
    monkeypatch.setattr(user_auth, "verify", lambda token: _pro_claims())
    resp = gated.post(path, json={"message": "hi", "text": "hi", "language": "es"}, headers=AUTH)
    assert resp.status_code != 402


def test_plan_comes_from_the_token_not_a_client_field(gated, pro_enforced, monkeypatch):
    # A user must not be able to promote themselves by sending a plan, or by
    # editing the Firestore profile the client can write to.
    monkeypatch.setattr(user_auth, "verify", lambda token: _member_claims())
    resp = gated.post("/api/chat", json={"message": "hi", "plan": "pro"}, headers=AUTH)
    assert resp.status_code == 402


def test_translation_stays_free_for_members(as_member, pro_enforced):
    resp = as_member.post("/api/translate", json={"text": "hi", "source": "en", "target": "es"}, headers=AUTH)
    assert resp.status_code != 402


def test_nothing_is_paywalled_while_enforcement_is_off(as_member):
    # Shipped dormant on purpose: switching it on takes features away from
    # everyone who signed up while they were free.
    for path in PRO_ONLY:
        resp = as_member.post(path, json={"message": "hi", "text": "hi", "language": "es"}, headers=AUTH)
        assert resp.status_code != 402
