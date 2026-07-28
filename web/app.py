"""Flask web app for Rosetta: a browser UI over the translator core in ../src."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flask import Flask, Response, jsonify, render_template, request  # noqa: E402

from translator import (  # noqa: E402
    AUTO_DETECT,
    LANGUAGES,
    DetectionError,
    ProviderError,
    ProviderUnavailableError,
    detect_language,
    is_supported,
    language_name,
)
from translator import (
    translate as translate_text,
)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

MAX_TEXT_LENGTH = 500


@app.route("/")
def index() -> str:
    return render_template("index.html", languages=LANGUAGES)


@app.route("/api/translate", methods=["POST"])
def api_translate() -> Response | tuple[Response, int]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    text = data.get("text")
    source = data.get("source")
    target = data.get("target")

    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "text is required"}), 400
    if len(text) > MAX_TEXT_LENGTH:
        return jsonify({"error": f"text must be at most {MAX_TEXT_LENGTH} characters"}), 400
    if not isinstance(target, str) or not is_supported(target):
        return jsonify({"error": "target is required and must be a supported language code"}), 400
    if not isinstance(source, str) or (source != AUTO_DETECT and not is_supported(source)):
        return jsonify({"error": f"source must be {AUTO_DETECT!r} or a supported language code"}), 400

    detected_source: str | None = None
    resolved_source = source
    if source == AUTO_DETECT:
        try:
            resolved_source = detect_language(text)
        except DetectionError as exc:
            return jsonify({"error": str(exc)}), 400
        detected_source = resolved_source

    if resolved_source == target:
        # Same language either way -- skip the round trip to the provider.
        return jsonify(
            {
                "translated_text": text,
                "detected_source": detected_source,
                "detected_source_name": language_name(detected_source) if detected_source else None,
            }
        )

    try:
        translated = translate_text(text, resolved_source, target)
    except ProviderUnavailableError as exc:
        return jsonify({"error": str(exc)}), 503
    except ProviderError as exc:
        return jsonify({"error": str(exc)}), 502

    return jsonify(
        {
            "translated_text": translated,
            "detected_source": detected_source,
            "detected_source_name": language_name(detected_source) if detected_source else None,
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5053))
    app.run(host="127.0.0.1", port=port, debug=False)
