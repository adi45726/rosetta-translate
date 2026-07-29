"""Flask web app for Rosetta: a browser UI over the translator core in ../src."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from collections import OrderedDict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# Vercel imports this module from the repo root, so web/ is not
# automatically on the path for its own sibling modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Same directory as this file; sys.path already includes it on Vercel and
# locally because Flask runs app.py as __main__ from web/.
import admin_auth  # noqa: E402
import user_auth  # noqa: E402
from flask import (  # noqa: E402
    Flask,
    Response,
    g,
    jsonify,
    make_response,
    render_template,
    request,
)

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
    practice,
    read_expression,
    rewrite_text,
    scan_and_translate_image,
    scenario_options,
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

log = logging.getLogger(__name__)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
_firebase_admin_app = None
_firebase_admin_lock = threading.Lock()

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


def _clean_env(name: str) -> str:
    """Read an env var, rejecting a value that is obviously a mis-paste.

    Pasting into a dashboard field is easy to get wrong: a value that arrives
    carrying newlines, or containing `OTHER_VAR=`, is a chunk of a .env file
    rather than the single value asked for. That happened in production --
    FIREBASE_API_KEY held the four lines that follow it in .env, so Firebase
    was handed a nonsense key, failed to initialise, and every sign-in button
    sat there doing nothing with no clue as to why.

    Discarding such a value is deliberately better than forwarding it: an
    empty field makes the client report "not configured", which is true and
    actionable, where a corrupt one produces a silent, unexplained failure.
    """
    value = os.environ.get(name, "").strip().strip("'\"")
    if not value:
        return ""
    if "\n" in value or "\r" in value or re.search(r"\b[A-Z][A-Z0-9_]{3,}=", value):
        log.warning("%s looks like a pasted block rather than a value; ignoring it", name)
        return ""
    return value


def _firebase_config() -> dict[str, str]:
    return {
        "apiKey": _clean_env("FIREBASE_API_KEY"),
        "authDomain": _clean_env("FIREBASE_AUTH_DOMAIN"),
        "projectId": _clean_env("FIREBASE_PROJECT_ID"),
        "storageBucket": _clean_env("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": _clean_env("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": _clean_env("FIREBASE_APP_ID"),
    }


def _firebase_services():
    """Return Firebase Auth/Firestore services when server credentials exist."""
    global _firebase_admin_app
    service_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON", "")
    if not service_json:
        return None
    with _firebase_admin_lock:
        if _firebase_admin_app is None:
            import firebase_admin
            from firebase_admin import credentials

            credential = credentials.Certificate(json.loads(service_json))
            _firebase_admin_app = firebase_admin.initialize_app(credential)
    from firebase_admin import auth, firestore

    return auth, firestore.client(
        app=_firebase_admin_app,
        database_id=os.environ.get("FIREBASE_DATABASE_ID", "(default)"),
    )


def _current_user() -> dict | None:
    services = _firebase_services()
    header = request.headers.get("Authorization", "")
    if services is None or not header.startswith("Bearer "):
        return None
    try:
        return services[0].verify_id_token(header[7:])
    except Exception:
        return None



@app.before_request
def _start_request_timer() -> None:
    g.request_started = time.perf_counter()


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
    # Locked to the hosts this app genuinely talks to. 'unsafe-inline' is
    # present because the page carries inline <script> and style attributes
    # written from JS; removing it needs nonces on every inline block, which is
    # a bigger change than this pass. Even so, connect-src is the valuable
    # half: model output is rendered as textContent, but if a future change
    # ever injects markup, this stops it phoning anywhere but Google/Firebase.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' https://www.gstatic.com 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "font-src 'self'; "
        "connect-src 'self' https://*.googleapis.com https://*.firebaseio.com "
        "https://securetoken.googleapis.com https://identitytoolkit.googleapis.com "
        "https://firestore.googleapis.com https://www.gstatic.com; "
        "frame-src https://*.firebaseapp.com; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
    )
    if request.path.startswith("/api/") and request.path not in {"/api/config", "/api/profile", "/api/admin/analytics"}:
        try:
            user = _current_user()
            services = _firebase_services()
            if user and services:
                from firebase_admin import firestore

                services[1].collection("usage_events").add(
                    {
                        "uid": user["uid"],
                        "feature": request.path.removeprefix("/api/"),
                        "method": request.method,
                        "status": response.status_code,
                        "duration_ms": round((time.perf_counter() - g.request_started) * 1000, 1),
                        "anonymous": user.get("firebase", {}).get("sign_in_provider") == "anonymous",
                        "created_at": firestore.SERVER_TIMESTAMP,
                    }
                )
        except Exception:
            # Analytics must never break translation if Firebase is unavailable.
            pass
    return response


# Endpoints that spend Groq quota. Every one of these answered an anonymous
# curl before this gate existed.
_PROTECTED_PREFIXES = ("/api/translate", "/api/write", "/api/transcribe",
                       "/api/camera-translate", "/api/expression", "/api/chat",
                       "/api/practice")
# Open by design: the client needs these before it can possibly hold a token.
_OPEN_PATHS = {"/api/config", "/api/practice/scenarios"}

# What an anonymous ("guest") token may reach. Mirrors what the browser shows
# guests -- translation only -- but enforced where it cannot be edited away.
_GUEST_ALLOWED = {"/api/translate"}
GUEST_MAX_TEXT_LENGTH = 250


def _requires_user(path: str) -> bool:
    if path in _OPEN_PATHS or path.startswith("/api/admin/"):
        return False
    return any(path == p or path.startswith(p + "/") for p in _PROTECTED_PREFIXES)


@app.before_request
def _require_signed_in_user():
    """Reject unauthenticated calls to the endpoints that cost money.

    Invisible to real users: the page signs everyone in, guests included, and
    attaches the ID token to every /api/ call. It is only felt by a request
    that arrives without one -- which is exactly the traffic that was quietly
    spending the Groq quota.

    Fails open when FIREBASE_PROJECT_ID is unset, because a deployment with no
    Firebase configured has no way to verify anyone and would otherwise be
    bricked. That is the opposite of admin_auth, which fails closed: there the
    risk is unauthorised access to data, here it is a broken app for everybody.
    """
    if app.config.get("TESTING") and app.config.get("SKIP_USER_AUTH", True):
        return None
    if not _requires_user(request.path) or not user_auth.is_enforceable():
        return None
    claims = user_auth.verify(user_auth.bearer_token(request.headers.get("Authorization", "")))
    if claims is None:
        return jsonify({"error": "sign in to use this feature"}), 401

    g.user_claims = claims
    g.is_guest = claims.get("firebase", {}).get("sign_in_provider") == "anonymous"

    # The browser hides the member-only tools from guests, but that is styling,
    # not a control: an anonymous token is one unauthenticated API call away,
    # and with it a guest could reach Iris, Practice, camera and voice exactly
    # as a member does. Confirmed against production before this existed.
    if g.is_guest and request.path not in _GUEST_ALLOWED:
        return jsonify({"error": "create a free account to use this feature"}), 403

    # Same reasoning for the length cap the client applies to guests.
    if g.is_guest and request.path == "/api/translate":
        body = request.get_json(silent=True)
        text = body.get("text") if isinstance(body, dict) else None
        if isinstance(text, str) and len(text) > GUEST_MAX_TEXT_LENGTH:
            return jsonify(
                {"error": f"guests can translate up to {GUEST_MAX_TEXT_LENGTH} characters"}
            ), 403
    return None


@app.route("/")
def index() -> str:
    return render_template(
        "index.html",
        languages=LANGUAGES,
        max_length=max_text_length(),
        engine=engine_label(),
        provider=active_provider(),
        firebase_config=_firebase_config(),
    )


def _admin_session_ok() -> bool:
    return admin_auth.valid_session(request.cookies.get(admin_auth.COOKIE_NAME))


@app.route("/admin")
def admin_dashboard() -> Response | str:
    """The dashboard, behind its own passphrase.

    Deliberately not tied to the app's user authentication: no Google account,
    however privileged, opens this page. See web/admin_auth.py.
    """
    if not admin_auth.is_configured():
        # Fail closed. An unconfigured deployment must not expose a dashboard.
        return make_response(render_template("admin_login.html", disabled=True), 503)
    if not _admin_session_ok():
        return make_response(render_template("admin_login.html", disabled=False), 401)
    return render_template("admin.html", firebase_config=_firebase_config())


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login() -> Response | tuple[Response, int]:
    if not admin_auth.is_configured():
        return jsonify({"error": "the dashboard is not configured on this deployment"}), 503

    ip = _client_ip()
    remaining = admin_auth.locked_out(ip)
    if remaining:
        response = jsonify({"error": f"too many attempts — try again in {remaining // 60 + 1} minutes"})
        response.headers["Retry-After"] = str(remaining)
        return response, 429

    data = request.get_json(silent=True)
    passphrase = data.get("passphrase") if isinstance(data, dict) else None
    if not admin_auth.verify_passphrase(passphrase or "", ip):
        # One message for every failure mode: distinguishing "wrong passphrase"
        # from anything else tells an attacker which half they got right.
        return jsonify({"error": "incorrect passphrase"}), 401

    response = jsonify({"ok": True})
    response.set_cookie(
        admin_auth.COOKIE_NAME,
        admin_auth.issue_session(),
        max_age=admin_auth.SESSION_MAX_AGE,
        httponly=True,      # unreadable from JavaScript, so XSS can't lift it
        samesite="Strict",  # never sent on a cross-site request
        secure=request.is_secure,
        path="/",
    )
    return response


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout() -> Response:
    response = jsonify({"ok": True})
    response.delete_cookie(admin_auth.COOKIE_NAME, path="/")
    return response


@app.route("/api/profile", methods=["GET", "POST"])
def api_profile() -> Response | tuple[Response, int]:
    user = _current_user()
    services = _firebase_services()
    if user is None or services is None:
        return jsonify({"error": "authentication required"}), 401
    document = services[1].collection("users").document(user["uid"])
    if request.method == "GET":
        snapshot = document.get()
        return jsonify(
            {
                "profile": snapshot.to_dict() if snapshot.exists else None,
                # Admin is a separate passphrase, never a property of a user.
                "is_admin": False,
                "anonymous": user.get("firebase", {}).get("sign_in_provider") == "anonymous",
            }
        )

    data = request.get_json(silent=True) or {}
    first_name = str(data.get("first_name", "")).strip()[:60]
    last_name = str(data.get("last_name", "")).strip()[:60]
    purpose = str(data.get("purpose", "")).strip()[:80]
    role = str(data.get("role", "")).strip()[:80]
    frequency = str(data.get("frequency", "")).strip()[:40]
    languages = [str(item)[:40] for item in data.get("languages", [])[:8]] if isinstance(data.get("languages"), list) else []
    if not first_name or not last_name or not purpose:
        return jsonify({"error": "first name, last name and purpose are required"}), 400
    from firebase_admin import firestore

    existing_profile = document.get()
    profile_data = {
            "uid": user["uid"],
            "email": user.get("email"),
            "anonymous": user.get("firebase", {}).get("sign_in_provider") == "anonymous",
            "first_name": first_name,
            "last_name": last_name,
            "purpose": purpose,
            "role": role,
            "frequency": frequency,
            "languages": languages,
            "last_seen_at": firestore.SERVER_TIMESTAMP,
        }
    if not existing_profile.exists:
        profile_data["created_at"] = firestore.SERVER_TIMESTAMP
    document.set(profile_data, merge=True)
    return jsonify({"ok": True, "is_admin": False})


@app.route("/api/admin/analytics")
def api_admin_analytics() -> Response | tuple[Response, int]:
    # Gated by the standalone admin session only. A Firebase ID token -- even
    # one belonging to the operator -- is not accepted here.
    if not admin_auth.is_configured():
        return jsonify({"error": "the dashboard is not configured on this deployment"}), 503
    if not _admin_session_ok():
        return jsonify({"error": "administrator sign-in required"}), 401
    services = _firebase_services()
    if services is None:
        return jsonify({"error": "analytics storage is not configured"}), 503
    db = services[1]
    profiles = [snapshot.to_dict() for snapshot in db.collection("users").limit(500).stream()]
    from firebase_admin import firestore

    events = [
        snapshot.to_dict()
        for snapshot in db.collection("usage_events")
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(1000)
        .stream()
    ]
    feature_counts: dict[str, int] = {}
    total_duration = 0.0
    errors = 0
    for event in events:
        feature = event.get("feature", "unknown")
        feature_counts[feature] = feature_counts.get(feature, 0) + 1
        total_duration += float(event.get("duration_ms", 0))
        if int(event.get("status", 200)) >= 400:
            errors += 1
    return jsonify(
        {
            "users": profiles,
            "recent_events": events[:100],
            "metrics": {
                "total_users": len(profiles),
                "registered_users": sum(not profile.get("anonymous", False) for profile in profiles),
                "guest_users": sum(bool(profile.get("anonymous", False)) for profile in profiles),
                "requests": len(events),
                "errors": errors,
                "average_speed_ms": round(total_duration / len(events)) if events else 0,
                "feature_counts": feature_counts,
            },
        }
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


@app.route("/service-worker.js")
def service_worker() -> Response:
    """Serve the worker at the origin root so it can control the whole app."""
    response = app.send_static_file("service-worker.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


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


@app.route("/api/practice", methods=["POST"])
def api_practice() -> Response | tuple[Response, int]:
    """One turn of roleplay language practice."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    message = data.get("message", "")
    if not isinstance(message, str):
        return jsonify({"error": "message must be a string"}), 400
    language = data.get("language")
    if not isinstance(language, str) or not is_supported(language):
        return jsonify({"error": "a supported practice language is required"}), 400

    if not app.config.get("TESTING", False) and _rate_limited(_client_ip()):
        return jsonify({"error": "too many requests — slow down for a moment"}), 429

    try:
        return jsonify(
            practice(
                message,
                language,
                str(data.get("scenario", "cafe")),
                str(data.get("level", "beginner")),
                data.get("history"),
            )
        )
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/api/practice/scenarios")
def api_practice_scenarios() -> Response:
    return jsonify({"scenarios": scenario_options()})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5053))
    app.run(host="127.0.0.1", port=port, debug=False)
