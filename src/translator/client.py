"""Thin client for the MyMemory translation API.

The keyless baseline provider, and the fallback when Groq is unconfigured or
failing -- see `engine.py`, which is what callers actually go through. Kept to
one network function so a third provider (DeepL, Google Cloud Translation) is
a new module plus one branch in the engine, and nothing else.

MyMemory quirks worth documenting:

1. It always answers HTTP 200, even on failure (bad language pair, same
   source/target, etc.) -- the actual outcome is in the JSON body's
   `responseStatus` field, which is an int (200) on success but a *string*
   ("403") on failure. We normalize both to str() before comparing.
2. The top-level `responseData.translatedText` is chosen by segment-match
   score alone, ignoring the separate `quality` score -- so it can surface a
   `quality: "0"` entry from unreviewed crowd-sourced data (`created-by:
   "Public_Corpora"`) over a `quality: "74"` correct translation sitting
   right below it in `matches`. Confirmed live: "Good morning, how are you?"
   -> "Ahora que no estás, que no te puedo ver" (quality 0) instead of
   "Buenos días, ¿cómo está?" (quality 74, same 0.99 match score). We
   re-rank `matches` ourselves instead of trusting the top-level field.
"""

from __future__ import annotations

from typing import Any

import requests

from .exceptions import ProviderError, ProviderUnavailableError
from .result import TranslationResult

MYMEMORY_ENDPOINT = "https://api.mymemory.translated.net/get"
REQUEST_TIMEOUT_SECONDS = 8.0
MIN_ACCEPTABLE_QUALITY = 40
DEFAULT_MAX_ALTERNATES = 3
MAX_TEXT_LENGTH = 500

__all__ = ["TranslationResult", "translate", "translate_with_alternates"]


def _quality_of(entry: dict[str, Any]) -> int | None:
    """Parse a match's `quality` field. None means "no score" (e.g. pure MT), not "bad"."""
    value = entry.get("quality")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _match_score_of(entry: dict[str, Any]) -> float:
    value = entry.get("match")
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ranked_translations(data: dict[str, Any]) -> list[str]:
    """All acceptable-quality candidates from `matches`, ranked best-first, deduped.

    Empty (not None) when there are no usable candidates -- e.g. a pure-MT
    response with an empty `matches` list -- so callers fall back to the
    top-level field.
    """
    candidates = []
    for entry in data.get("matches") or []:
        translation = entry.get("translation")
        if not isinstance(translation, str) or not translation.strip():
            continue
        quality = _quality_of(entry)
        if quality is not None and quality < MIN_ACCEPTABLE_QUALITY:
            continue
        candidates.append(
            (_match_score_of(entry), quality if quality is not None else 50, translation.strip())
        )
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)

    seen: set[str] = set()
    ranked: list[str] = []
    for _, _, text in candidates:
        if text not in seen:
            seen.add(text)
            ranked.append(text)
    return ranked


def _fetch(text: str, source: str, target: str) -> dict[str, Any]:
    try:
        response = requests.get(
            MYMEMORY_ENDPOINT,
            params={"q": text, "langpair": f"{source}|{target}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data: Any = response.json()
    except requests.RequestException as exc:
        raise ProviderUnavailableError("could not reach the translation service") from exc
    except ValueError as exc:
        raise ProviderUnavailableError("translation service returned an invalid response") from exc

    if str(data.get("responseStatus")) != "200":
        message = data.get("responseDetails") or "translation failed"
        raise ProviderError(str(message))
    return data


def translate(text: str, source: str, target: str) -> str:
    """Translate `text` from `source` to `target` (language codes, e.g. "en", "es")."""
    data = _fetch(text, source, target)
    ranked = _ranked_translations(data)
    translated = ranked[0] if ranked else data.get("responseData", {}).get("translatedText")
    if not isinstance(translated, str) or not translated:
        raise ProviderError("translation service returned no text")
    return translated


def translate_with_alternates(
    text: str, source: str, target: str, max_alternates: int = DEFAULT_MAX_ALTERNATES
) -> TranslationResult:
    """Like `translate`, but also returns up to `max_alternates` other candidate translations."""
    data = _fetch(text, source, target)
    ranked = _ranked_translations(data)
    primary = ranked[0] if ranked else data.get("responseData", {}).get("translatedText")
    if not isinstance(primary, str) or not primary:
        raise ProviderError("translation service returned no text")
    alternates = [t for t in ranked if t != primary][:max_alternates]
    return TranslationResult(text=primary, alternates=alternates)
