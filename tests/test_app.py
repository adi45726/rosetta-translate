import app as web_app
import pytest

from translator.exceptions import ProviderError, ProviderUnavailableError


@pytest.fixture
def client():
    web_app.app.config["TESTING"] = True
    with web_app.app.test_client() as c:
        yield c


def test_index_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Rosetta" in resp.data


def test_translate_explicit_languages(client, monkeypatch):
    monkeypatch.setattr(web_app, "translate_text", lambda text, source, target: "Hola mundo")
    resp = client.post("/api/translate", json={"text": "Hello world", "source": "en", "target": "es"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["translated_text"] == "Hola mundo"
    assert data["detected_source"] is None


def test_translate_auto_detect_uses_real_detection(client, monkeypatch):
    captured = {}

    def fake_translate(text, source, target):
        captured["source"] = source
        return "Bonjour"

    monkeypatch.setattr(web_app, "translate_text", fake_translate)
    resp = client.post(
        "/api/translate",
        json={"text": "This is a clear and unambiguous sentence written in English.", "source": "auto", "target": "fr"},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["detected_source"] == "en"
    assert data["detected_source_name"] == "English"
    assert captured["source"] == "en"


def test_translate_same_language_skips_provider_call(client, monkeypatch):
    called = False

    def fake_translate(text, source, target):
        nonlocal called
        called = True
        return "should not be used"

    monkeypatch.setattr(web_app, "translate_text", fake_translate)
    resp = client.post("/api/translate", json={"text": "hello", "source": "en", "target": "en"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["translated_text"] == "hello"
    assert called is False


def test_translate_auto_detect_matching_target_skips_provider_call(client, monkeypatch):
    called = False

    def fake_translate(text, source, target):
        nonlocal called
        called = True
        return "should not be used"

    monkeypatch.setattr(web_app, "translate_text", fake_translate)
    resp = client.post(
        "/api/translate",
        json={"text": "This is a clear and unambiguous sentence written in English.", "source": "auto", "target": "en"},
    )
    assert resp.status_code == 200
    assert called is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": "", "source": "en", "target": "es"},
        {"text": "   ", "source": "en", "target": "es"},
        {"text": "hi", "source": "en"},  # missing target
        {"text": "hi", "target": "es"},  # missing source
        {"text": "hi", "source": "en", "target": "xx"},  # unsupported target
        {"text": "hi", "source": "xx", "target": "es"},  # unsupported source
        {"text": "x" * 501, "source": "en", "target": "es"},  # too long
    ],
)
def test_translate_rejects_invalid_requests(client, payload):
    resp = client.post("/api/translate", json=payload)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_translate_rejects_non_json_body(client):
    resp = client.post("/api/translate", data="not json", content_type="text/plain")
    assert resp.status_code == 400


def test_translate_detection_failure_returns_400(client):
    # Digits-only text has no linguistic features for langdetect to key off of.
    resp = client.post("/api/translate", json={"text": "12345", "source": "auto", "target": "es"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_translate_provider_error_returns_502(client, monkeypatch):
    def raise_provider_error(text, source, target):
        raise ProviderError("PLEASE SELECT TWO DISTINCT LANGUAGES")

    monkeypatch.setattr(web_app, "translate_text", raise_provider_error)
    resp = client.post("/api/translate", json={"text": "hi", "source": "en", "target": "fr"})
    assert resp.status_code == 502
    assert "error" in resp.get_json()


def test_translate_provider_unavailable_returns_503(client, monkeypatch):
    def raise_unavailable(text, source, target):
        raise ProviderUnavailableError("could not reach the translation service")

    monkeypatch.setattr(web_app, "translate_text", raise_unavailable)
    resp = client.post("/api/translate", json={"text": "hi", "source": "en", "target": "fr"})
    assert resp.status_code == 503
    assert "error" in resp.get_json()
