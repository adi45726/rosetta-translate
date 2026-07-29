"""Picks a provider, resolves auto-detect, and degrades instead of failing.

This is the only module that knows more than one provider exists. `web/app.py`
calls `translate()` and gets a `TranslationResult` back; it never branches on
which engine answered.

The ordering is Groq first (better output, 5000-char limit, detection included)
then MyMemory (keyless, always available, 500-char limit). If Groq is
configured but errors -- rate limit, bad key, an outage -- a translation that
MyMemory could still serve is served rather than surfaced as a failure. The
user gets a slightly worse answer instead of no answer, and `result.provider`
records what actually happened so the UI can say so.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from . import client as mymemory
from . import groq_client
from .detect import detect_language
from .exceptions import ProviderError, ProviderUnavailableError
from .languages import AUTO_DETECT
from .result import PROVIDER_GROQ, PROVIDER_MYMEMORY, PROVIDER_NONE, TranslationResult

log = logging.getLogger(__name__)

MYMEMORY_MAX_TEXT_LENGTH = 500


def active_provider() -> str:
    return PROVIDER_GROQ if groq_client.is_configured() else PROVIDER_MYMEMORY


def max_text_length() -> int:
    """The longest input the *primary* provider accepts."""
    return groq_client.MAX_TEXT_LENGTH if groq_client.is_configured() else MYMEMORY_MAX_TEXT_LENGTH


def engine_label() -> str:
    """Human-readable name of the active engine, for the UI badge."""
    if groq_client.is_configured():
        # "openai/gpt-oss-120b" -> "gpt-oss-120b"; the vendor prefix is noise here.
        return f"Groq · {groq_client.model_name().split('/')[-1]}"
    return "MyMemory"


def _echo(text: str, detected: str | None = None) -> TranslationResult:
    return TranslationResult(text=text, detected_source=detected, provider=PROVIDER_NONE)


def _via_mymemory(text: str, source: str, target: str) -> TranslationResult:
    detected: str | None = None
    resolved = source
    if source == AUTO_DETECT:
        # Raises DetectionError, which the caller maps to a 400 -- unlike a
        # provider failure, "I can't tell what this is" is a problem with the
        # input, so there is nothing to fall back to.
        resolved = detect_language(text)
        detected = resolved

    if resolved == target:
        return _echo(text, detected)

    result = mymemory.translate_with_alternates(text, resolved, target)
    return replace(result, detected_source=detected, provider=PROVIDER_MYMEMORY)


def translate(text: str, source: str, target: str) -> TranslationResult:
    """Translate `text` into `target`. `source` is a language code or "auto"."""
    # Cheapest possible answer: same language in and out, no provider needed.
    # (MyMemory rejects such a request outright, so this isn't only an optimisation.)
    if source != AUTO_DETECT and source == target:
        return _echo(text)

    if groq_client.is_configured():
        try:
            return groq_client.translate(text, source, target)
        except (ProviderError, ProviderUnavailableError) as exc:
            if len(text) > MYMEMORY_MAX_TEXT_LENGTH:
                # Too long for the fallback to accept -- nothing to degrade to.
                raise
            log.warning("Groq failed (%s), falling back to MyMemory", exc)

    return _via_mymemory(text, source, target)


def rewrite_text(
    text: str, mode: str, tone: str = "preserve", audience: str = "general", preserve_terms: str = ""
) -> dict[str, object]:
    """Run a structured Writing Studio edit through the configured LLM."""
    return groq_client.rewrite_text(text, mode, tone, audience, preserve_terms)


def transcribe_audio(audio: bytes, filename: str, language: str | None = None) -> str:
    return groq_client.transcribe_audio(audio, filename, language)


def scan_and_translate_image(image: bytes, mime_type: str, target_name: str) -> dict[str, object]:
    return groq_client.scan_and_translate_image(image, mime_type, target_name)
