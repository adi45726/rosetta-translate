"""Thin client for the MyMemory translation API.

Deliberately kept to one function so the provider is swappable -- a paid API
(DeepL, Google Cloud Translation, Azure Translator) can replace the body of
`translate()` without touching any caller in web/app.py.

MyMemory quirk worth documenting: it always answers HTTP 200, even on
failure (bad language pair, same source/target, etc.) -- the actual outcome
is in the JSON body's `responseStatus` field, which is an int (200) on
success but a *string* ("403") on failure. We normalize both to str() before
comparing.
"""

from __future__ import annotations

from typing import Any

import requests

from .exceptions import ProviderError, ProviderUnavailableError

MYMEMORY_ENDPOINT = "https://api.mymemory.translated.net/get"
REQUEST_TIMEOUT_SECONDS = 8.0


def translate(text: str, source: str, target: str) -> str:
    """Translate `text` from `source` to `target` (language codes, e.g. "en", "es")."""
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

    translated = data.get("responseData", {}).get("translatedText")
    if not isinstance(translated, str) or not translated:
        raise ProviderError("translation service returned no text")
    return translated
