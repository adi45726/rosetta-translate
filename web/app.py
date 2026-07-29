"""Flask web app for Rosetta: a browser UI over the translator core in ../src."""

from __future__ import annotations

import hashlib
import os
import sys
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, Response, jsonify, render_template, request  # noqa: E402

from translator import (  # noqa: E402
    AUTO_DETECT,
    LANGUAGES,
    WRITING_AUDIENCES,
    WRITING_MODES,
    WRITING_TONES,
    DetectionError,
    ProviderError,
    ProviderUnavailableError,
    active_provider,
    chat,
    engine_label,
    is_supported,
    language_name,
    max_text_length,
    read_expression,
    rewrite_text,
    scan_and_translate_image,
    transcribe_audio,
    translate,
)


def _load_dotenv() -> None:
    """Read a local .env into the environment. No dependency, no overwriting.

    Deliberately tiny: the only thing that ever goes in this project's .env is
    GROQ_API_KEY / GROQ_MODEL, and pulling in python-dotenv to parse two lines
    would add a dependency to the Vercel bundle for nothing. Real environments
    (Vercel, CI) set actual env vars, which always win over the file.
    """
    env_path = Path(__file__).resolve().parents[1] / ".env"
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Requests per IP per window. Generous for a human typing (the client debounces
# and caches), tight enough that a script can't burn the Groq quota. Best
# effort only: process-local, so on serverless it's per warm instance.
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60

CACHE_MAX_ENTRIES = 256

# One webcam frame. Smaller than the camera-translate ceiling because these
# are downscaled snapshots sent repeatedly, not one deliberate high-res photo.
MAX_FRAME_BYTES = 2 * 1024 * 1024

_cache: OrderedDict[tuple[str, str, str], dict[str, object]] = OrderedDict()
_camera_cache: OrderedDict[tuple[str, str], dict[str, object]] = OrderedDict()
_hits: dict[str, deque[float]] = {}
_lock = threading.Lock()


def _cache_get(key: tuple[str, str, str]) -> dict[str, object] | None:
    with _lock:
        payload = _cache.get(key)
        if payload is not None:
            _cache.move_to_end(key)
        return payload


def _cache_put(key: tuple[str, str, str], payload: dict[str, object]) -> None:
    with _lock:
        _cache[key] = payload
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)


def _rate_limited(ip: str) -> bool:
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    with _lock:
        seen = _hits.setdefault(ip, deque())
        while seen and seen[0] < cutoff:
            seen.popleft()
        if len(seen) >= RATE_LIMIT_REQUESTS:
            return True
        seen.append(now)
        # Keep the table from growing without bound on a long-lived instance.
        if len(_hits) > 1024:
            for stale in [k for k, v in _hits.items() if not v or v[-1] < cutoff]:
                del _hits[stale]
        return False


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "unknown"


def reset_state() -> None:
    """Clear the cache and rate-limit table. For tests."""
    with _lock:
        _cache.clear()
        _camera_cache.clear()
        _hits.clear()


@app.after_request
def _security_headers(response: Response) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.route("/")
def index() -> str:
    return render_template(
        "index.html",
        languages=LANGUAGES,
        max_length=max_text_length(),
        engine=engine_label(),
        provider=active_provider(),
    )


@app.route("/api/config")
def api_config() -> Response:
    """What the client needs to configure itself against the active provider."""
    return jsonify(
        {
            "provider": active_provider(),
            "engine": engine_label(),
            "max_text_length": max_text_length(),
        }
    )


@app.route("/api/translate", methods=["POST"])
def api_translate() -> Response | tuple[Response, int]:
    limit = max_text_length()

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    text = data.get("text")
    source = data.get("source")
    target = data.get("target")

    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text is required"}), 400
    if len(text) > limit:
        return jsonify({"error": f"text must be at most {limit} characters"}), 400
    if not isinstance(target, str) or not is_supported(target):
        return jsonify({"error": "target is required and must be a supported language code"}), 400
    if not isinstance(source, str) or (source != AUTO_DETECT and not is_supported(source)):
        return jsonify({"error": f"source must be {AUTO_DETECT!r} or a supported language code"}), 400

    testing = app.config.get("TESTING", False)
    key = (text, source, target)

    if not testing:
        if _rate_limited(_client_ip()):
            return jsonify({"error": "too many requests — slow down for a moment"}), 429
        cached = _cache_get(key)
        if cached is not None:
            return jsonify({**cached, "cached": True})

    try:
        result = translate(text, source, target)
    except DetectionError as exc:
        return jsonify({"error": str(exc)}), 400
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502

    payload: dict[str, object] = {
        "translated_text": result.text,
        "alternates": result.alternates,
        "detected_source": result.detected_source,
        "detected_source_name": (
            language_name(result.detected_source) if result.detected_source else None
        ),
        "romanization": result.romanization,
        "note": result.note,
        "provider": result.provider,
    }

    if not testing:
        _cache_put(key, payload)
    return jsonify({**payload, "cached": False})


@app.route("/api/write", methods=["POST"])
def api_write() -> Response | tuple[Response, int]:
    """Humanize and rewrite text with explicit, reviewable edits."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    text = data.get("text")
    mode = data.get("mode", "humanize")
    tone = data.get("tone", "preserve")
    audience = data.get("audience", "general")
    preserve_terms = data.get("preserve_terms", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text is required"}), 400
    if len(text) > max_text_length():
        return jsonify({"error": f"text must be at most {max_text_length()} characters"}), 400
    if mode not in WRITING_MODES or tone not in WRITING_TONES or audience not in WRITING_AUDIENCES:
        return jsonify({"error": "unsupported writing option"}), 400
    if not isinstance(preserve_terms, str):
        return jsonify({"error": "preserve_terms must be text"}), 400
    try:
        return jsonify(rewrite_text(text, mode, tone, audience, preserve_terms))
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe() -> Response | tuple[Response, int]:
    """Transcribe a browser microphone recording for reliable voice input."""
    upload = request.files.get("audio")
    if upload is None:
        return jsonify({"error": "audio recording is required"}), 400
    audio = upload.read(15 * 1024 * 1024 + 1)
    if not audio:
        return jsonify({"error": "audio recording is empty"}), 400
    if len(audio) > 15 * 1024 * 1024:
        return jsonify({"error": "audio recording must be smaller than 15 MB"}), 413
    language = request.form.get("language", "auto")
    try:
        text = transcribe_audio(audio, upload.filename or "recording.webm", language)
        return jsonify({"text": text, "provider": "groq-whisper"})
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/camera-translate", methods=["POST"])
def api_camera_translate() -> Response | tuple[Response, int]:
    image = request.files.get("image")
    target = request.form.get("target", "")
    if image is None:
        return jsonify({"error": "camera image is required"}), 400
    if not is_supported(target):
        return jsonify({"error": "a supported target language is required"}), 400
    mime_type = image.mimetype if image.mimetype in {"image/jpeg", "image/png", "image/webp"} else "image/jpeg"
    content = image.read(5 * 1024 * 1024 + 1)
    if not content:
        return jsonify({"error": "camera image is empty"}), 400
    if len(content) > 5 * 1024 * 1024:
        return jsonify({"error": "camera image must be smaller than 5 MB"}), 413
    cache_key = (hashlib.sha256(content).hexdigest(), target)
    with _lock:
        cached = _camera_cache.get(cache_key)
        if cached is not None:
            _camera_cache.move_to_end(cache_key)
            return jsonify({**cached, "cached": True})
    try:
        result = scan_and_translate_image(content, mime_type, language_name(target))
        with _lock:
            _camera_cache[cache_key] = result
            _camera_cache.move_to_end(cache_key)
            while len(_camera_cache) > 64:
                _camera_cache.popitem(last=False)
        return jsonify({**result, "cached": False})
    except ProviderUnavailableError as exc:
        if "rate limit" in str(exc).lower():
            response = jsonify({"error": str(exc)})
            response.headers["Retry-After"] = "60"
            return response, 429
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/expression", methods=["POST"])
def api_expression() -> Response | tuple[Response, int]:
    """Read the expression in one webcam frame.

    The frame is held only for the duration of this request: it is passed
    straight to the provider and never written to disk, never logged, and
    deliberately never cached (unlike camera-translate, where the same sign
    photographed twice should hit the cache -- here an identical-looking frame
    a minute later is a *new* moment, and caching it would freeze the reading).
    """
    image = request.files.get("image")
    if image is None:
        return jsonify({"error": "an image frame is required"}), 400
    mime_type = image.mimetype if image.mimetype in {"image/jpeg", "image/png", "image/webp"} else "image/jpeg"
    content = image.read(MAX_FRAME_BYTES + 1)
    if not content:
        return jsonify({"error": "the image frame is empty"}), 400
    if len(content) > MAX_FRAME_BYTES:
        return jsonify({"error": "the image frame is too large"}), 413

    if not app.config.get("TESTING", False) and _rate_limited(_client_ip()):
        return jsonify({"error": "too many requests — slow down for a moment"}), 429

    try:
        return jsonify(read_expression(content, mime_type))
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/chat", methods=["POST"])
def api_chat() -> Response | tuple[Response, int]:
    """One conversational turn with the companion.

    History is supplied by the client each time rather than held server-side:
    the app has no accounts and no session store, and keeping transcripts in
    process memory would both leak between users on a shared instance and
    quietly break the "nothing you type is stored on a server" promise.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message is required"}), 400

    expression = data.get("expression")
    if expression is not None and not isinstance(expression, dict):
        expression = None

    if not app.config.get("TESTING", False) and _rate_limited(_client_ip()):
        return jsonify({"error": "too many requests — slow down for a moment"}), 429

    try:
        return jsonify(chat(message, data.get("history"), expression))
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5053))
    app.run(host="127.0.0.1", port=port, debug=False)
