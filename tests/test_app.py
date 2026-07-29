from io import BytesIO

import app as web_app
import pytest

from translator import PROVIDER_GROQ, PROVIDER_NONE, TranslationResult
from translator.exceptions import DetectionError, ProviderError, ProviderUnavailableError


@pytest.fixture
def client():
    web_app.app.config["TESTING"] = True
    web_app.reset_state()
    with web_app.app.test_client() as c:
        yield c


def test_index_ok(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Rosetta" in resp.data
    assert b'id="auth-gate"' in resp.data
    assert b'id="auth-google"' in resp.data


def test_index_includes_public_firebase_config(client, monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "public-web-key")
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "rosetta.firebaseapp.com")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "rosetta")
    monkeypatch.setenv("FIREBASE_APP_ID", "web-app-id")
    response = client.get("/")
    assert b"public-web-key" in response.data
    assert b"rosetta.firebaseapp.com" in response.data


def test_admin_dashboard_is_not_reachable_without_its_own_passphrase(client):
    # This used to assert a 200: the console rendered for anyone, gated only by
    # a client-side email check. It now has its own credential (admin_auth),
    # and with none configured in tests it must fail closed rather than open.
    response = client.get("/admin")
    assert response.status_code == 503
    assert b"admin-google" not in response.data


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"


def test_config_reports_keyless_defaults(client):
    data = client.get("/api/config").get_json()
    assert data["provider"] == "mymemory"
    assert data["engine"] == "MyMemory"
    assert data["max_text_length"] == 500


def test_config_reports_groq_when_key_is_set(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    data = client.get("/api/config").get_json()
    assert data["provider"] == "groq"
    assert data["engine"] == "Groq · gpt-oss-120b"
    assert data["max_text_length"] == 2000


def test_translate_returns_full_payload(client, monkeypatch):
    monkeypatch.setattr(
        web_app,
        "translate",
        lambda text, source, target: TranslationResult(
            text="Hola mundo",
            alternates=["Qué tal mundo"],
            detected_source="en",
            romanization=None,
            note="informal register assumed",
            provider=PROVIDER_GROQ,
        ),
    )
    resp = client.post("/api/translate", json={"text": "Hello world", "source": "auto", "target": "es"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["translated_text"] == "Hola mundo"
    assert data["alternates"] == ["Qué tal mundo"]
    assert data["detected_source"] == "en"
    assert data["detected_source_name"] == "English"
    assert data["note"] == "informal register assumed"
    assert data["provider"] == "groq"


def test_translate_passes_arguments_through_untouched(client, monkeypatch):
    captured = {}

    def fake(text, source, target):
        captured.update(text=text, source=source, target=target)
        return TranslationResult(text="Bonjour")

    monkeypatch.setattr(web_app, "translate", fake)
    client.post("/api/translate", json={"text": "Hello", "source": "auto", "target": "fr"})
    assert captured == {"text": "Hello", "source": "auto", "target": "fr"}


def test_translate_omits_detected_name_when_not_detected(client, monkeypatch):
    monkeypatch.setattr(web_app, "translate", lambda text, source, target: TranslationResult(text="Hola"))
    data = client.post("/api/translate", json={"text": "Hi", "source": "en", "target": "es"}).get_json()
    assert data["detected_source"] is None
    assert data["detected_source_name"] is None


def test_translate_same_language_is_echoed_without_a_provider(client):
    # No monkeypatching: this must not make a network call of any kind.
    resp = client.post("/api/translate", json={"text": "hello", "source": "en", "target": "en"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["translated_text"] == "hello"
    assert data["provider"] == PROVIDER_NONE


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
        {"text": "x" * 501, "source": "en", "target": "es"},  # over the MyMemory limit
    ],
)
def test_translate_rejects_invalid_requests(client, payload):
    resp = client.post("/api/translate", json=payload)
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_length_limit_follows_the_active_provider(client, monkeypatch):
    long_text = "x" * 501
    body = {"text": long_text, "source": "en", "target": "es"}
    monkeypatch.setattr(web_app, "translate", lambda text, source, target: TranslationResult(text="ok"))

    assert client.post("/api/translate", json=body).status_code == 400

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert client.post("/api/translate", json=body).status_code == 200


def test_translate_rejects_non_json_body(client):
    resp = client.post("/api/translate", data="not json", content_type="text/plain")
    assert resp.status_code == 400


def test_writing_studio_returns_structured_revision(client, monkeypatch):
    monkeypatch.setattr(
        web_app,
        "rewrite_text",
        lambda text, mode, tone, audience, preserve_terms: {
            "revised": "A clearer sentence.",
            "changes": ["Improved sentence flow"],
            "summary": "Made the writing more natural.",
            "meaning_preserved": True,
            "provider": "groq",
        },
    )
    response = client.post(
        "/api/write",
        json={
            "text": "A sentence that is not flowing.",
            "mode": "humanize",
            "tone": "friendly",
            "audience": "general",
            "preserve_terms": "Rosetta",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["revised"] == "A clearer sentence."


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": "", "mode": "humanize"},
        {"text": "Hello", "mode": "unsupported"},
        {"text": "Hello", "mode": "humanize", "tone": "unsupported"},
        {"text": "Hello", "mode": "humanize", "audience": "unsupported"},
    ],
)
def test_writing_studio_rejects_invalid_requests(client, payload):
    response = client.post("/api/write", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_voice_input_transcribes_uploaded_audio(client, monkeypatch):
    monkeypatch.setattr(
        web_app,
        "transcribe_audio",
        lambda audio, filename, language: "Hello from the microphone",
    )
    response = client.post(
        "/api/transcribe",
        data={
            "audio": (BytesIO(b"fake webm audio"), "recording.webm"),
            "language": "en",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["text"] == "Hello from the microphone"


def test_voice_input_requires_audio(client):
    response = client.post("/api/transcribe", data={}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_camera_translation_returns_visual_regions(client, monkeypatch):
    monkeypatch.setattr(
        web_app,
        "scan_and_translate_image",
        lambda image, mime, target: {
            "detected_language": "Spanish",
            "source_text": "Salida",
            "translated_text": "Exit",
            "regions": [{"source": "Salida", "translation": "Exit", "x": 0.2, "y": 0.3}],
        },
    )
    response = client.post(
        "/api/camera-translate",
        data={
            "image": (BytesIO(b"fake jpeg"), "frame.jpg"),
            "target": "en",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["translated_text"] == "Exit"


def test_camera_translation_requires_image_and_target(client):
    response = client.post("/api/camera-translate", data={}, content_type="multipart/form-data")
    assert response.status_code == 400


def test_translate_detection_failure_returns_400(client, monkeypatch):
    def raise_detection_error(text, source, target):
        raise DetectionError("could not detect the language of the given text")

    monkeypatch.setattr(web_app, "translate", raise_detection_error)
    resp = client.post("/api/translate", json={"text": "12345", "source": "auto", "target": "es"})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_translate_provider_error_returns_502(client, monkeypatch):
    def raise_provider_error(text, source, target):
        raise ProviderError("PLEASE SELECT TWO DISTINCT LANGUAGES")

    monkeypatch.setattr(web_app, "translate", raise_provider_error)
    resp = client.post("/api/translate", json={"text": "hi", "source": "en", "target": "fr"})
    assert resp.status_code == 502
    assert "error" in resp.get_json()


def test_translate_provider_unavailable_returns_503(client, monkeypatch):
    def raise_unavailable(text, source, target):
        raise ProviderUnavailableError("could not reach the translation service")

    monkeypatch.setattr(web_app, "translate", raise_unavailable)
    resp = client.post("/api/translate", json={"text": "hi", "source": "en", "target": "fr"})
    assert resp.status_code == 503
    assert "error" in resp.get_json()


# ─── Cache and rate limiting ────────────────────────────────────────────────
# Both are bypassed under TESTING (they would otherwise make every other test
# order-dependent), so these drive the app with TESTING off.


@pytest.fixture
def live_client():
    web_app.app.config["TESTING"] = False
    web_app.reset_state()
    with web_app.app.test_client() as c:
        yield c
    web_app.app.config["TESTING"] = True
    web_app.reset_state()


def test_identical_request_is_served_from_cache(live_client, monkeypatch):
    calls = []

    def fake(text, source, target):
        calls.append(text)
        return TranslationResult(text="Hola")

    monkeypatch.setattr(web_app, "translate", fake)
    body = {"text": "Hello", "source": "en", "target": "es"}

    first = live_client.post("/api/translate", json=body).get_json()
    second = live_client.post("/api/translate", json=body).get_json()

    assert len(calls) == 1
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["translated_text"] == "Hola"


def test_cache_key_includes_the_language_pair(live_client, monkeypatch):
    monkeypatch.setattr(
        web_app, "translate", lambda text, source, target: TranslationResult(text=f"->{target}")
    )
    es = live_client.post("/api/translate", json={"text": "Hi", "source": "en", "target": "es"}).get_json()
    fr = live_client.post("/api/translate", json={"text": "Hi", "source": "en", "target": "fr"}).get_json()
    assert es["translated_text"] == "->es"
    assert fr["translated_text"] == "->fr"


def test_failures_are_not_cached(live_client, monkeypatch):
    calls = []

    def flaky(text, source, target):
        calls.append(text)
        if len(calls) == 1:
            raise ProviderUnavailableError("down")
        return TranslationResult(text="Hola")

    monkeypatch.setattr(web_app, "translate", flaky)
    body = {"text": "Hello", "source": "en", "target": "es"}

    assert live_client.post("/api/translate", json=body).status_code == 503
    assert live_client.post("/api/translate", json=body).status_code == 200
    assert len(calls) == 2


def test_rate_limit_returns_429_past_the_window_budget(live_client, monkeypatch):
    monkeypatch.setattr(web_app, "translate", lambda text, source, target: TranslationResult(text="Hola"))

    # Distinct text each time so the cache can't absorb the requests.
    codes = [
        live_client.post(
            "/api/translate", json={"text": f"Hello {i}", "source": "en", "target": "es"}
        ).status_code
        for i in range(web_app.RATE_LIMIT_REQUESTS + 3)
    ]
    assert codes[: web_app.RATE_LIMIT_REQUESTS] == [200] * web_app.RATE_LIMIT_REQUESTS
    assert codes[web_app.RATE_LIMIT_REQUESTS :] == [429, 429, 429]
