import admin_auth
import app as web_app
import pytest
from werkzeug.security import generate_password_hash

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", generate_password_hash(PASSPHRASE))
    monkeypatch.setenv("SECRET_KEY", "unit-test-secret")
    admin_auth.reset_state()
    yield
    admin_auth.reset_state()


@pytest.fixture
def client(configured):
    web_app.app.config["TESTING"] = True
    web_app.reset_state()
    with web_app.app.test_client() as c:
        yield c


@pytest.fixture
def unconfigured_client(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    admin_auth.reset_state()
    web_app.app.config["TESTING"] = True
    with web_app.app.test_client() as c:
        yield c


def _login(client, passphrase=PASSPHRASE):
    return client.post("/api/admin/login", json={"passphrase": passphrase})


# ─── Fail closed ────────────────────────────────────────────────────────────


def test_unconfigured_disables_the_dashboard_rather_than_opening_it(unconfigured_client):
    # A missing environment variable must never be the only thing between an
    # attacker and the data.
    assert unconfigured_client.get("/admin").status_code == 503
    assert _login(unconfigured_client).status_code == 503
    assert unconfigured_client.get("/api/admin/analytics").status_code == 503


def test_half_configured_is_still_closed(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", generate_password_hash(PASSPHRASE))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert admin_auth.is_configured() is False


# ─── The gate ───────────────────────────────────────────────────────────────


def test_dashboard_requires_the_passphrase(client):
    assert client.get("/admin").status_code == 401
    assert client.get("/api/admin/analytics").status_code == 401


def test_correct_passphrase_opens_the_dashboard(client):
    assert _login(client).status_code == 200
    assert client.get("/admin").status_code == 200


def test_wrong_passphrase_is_refused(client):
    assert _login(client, "not it").status_code == 401
    assert client.get("/admin").status_code == 401


def test_failure_message_does_not_distinguish_cases(client):
    # Telling an attacker which half they got right is free information.
    assert _login(client, "").get_json()["error"] == "incorrect passphrase"
    assert _login(client, "wrong").get_json()["error"] == "incorrect passphrase"


def test_session_cookie_is_httponly_and_samesite(client):
    header = _login(client).headers["Set-Cookie"]
    assert "HttpOnly" in header            # unreadable from JS, so XSS can't lift it
    assert "SameSite=Strict" in header     # never sent cross-site
    assert admin_auth.COOKIE_NAME in header


def test_forged_cookie_is_rejected(client):
    client.set_cookie(admin_auth.COOKIE_NAME, "not.a.real.token")
    assert client.get("/admin").status_code == 401


def test_cookie_signed_with_another_key_is_rejected(client, monkeypatch):
    _login(client)
    # Rotating SECRET_KEY must invalidate every outstanding session.
    monkeypatch.setenv("SECRET_KEY", "a-different-secret")
    assert client.get("/admin").status_code == 401


def test_logout_clears_the_session(client):
    _login(client)
    assert client.get("/admin").status_code == 200
    client.post("/api/admin/logout")
    assert client.get("/admin").status_code == 401


# ─── Brute force ────────────────────────────────────────────────────────────


def test_repeated_failures_lock_the_ip_out(client):
    for _ in range(admin_auth.MAX_ATTEMPTS):
        assert _login(client, "wrong").status_code == 401
    locked = _login(client, "wrong")
    assert locked.status_code == 429
    assert "Retry-After" in locked.headers


def test_lockout_also_refuses_the_correct_passphrase(client):
    # Otherwise the limit is trivially bypassed by guessing right on attempt six.
    for _ in range(admin_auth.MAX_ATTEMPTS):
        _login(client, "wrong")
    assert _login(client).status_code == 429


def test_a_success_clears_the_attempt_counter(client):
    for _ in range(admin_auth.MAX_ATTEMPTS - 1):
        _login(client, "wrong")
    assert _login(client).status_code == 200
    assert admin_auth.locked_out("127.0.0.1") == 0


# ─── Separation from user auth ──────────────────────────────────────────────


def test_a_firebase_token_does_not_open_the_dashboard(client):
    # The whole point: no user account, however privileged, is a way in.
    resp = client.get("/api/admin/analytics", headers={"Authorization": "Bearer any.id.token"})
    assert resp.status_code == 401


def test_verify_passphrase_is_false_when_unconfigured(monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert admin_auth.verify_passphrase("anything", "1.2.3.4") is False
    assert admin_auth.valid_session("anything") is False
