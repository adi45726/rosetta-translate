"""Best-effort source-language detection, used by the "Detect language" option."""

from __future__ import annotations

from langdetect import DetectorFactory, LangDetectException
from langdetect import detect as _detect

from .exceptions import DetectionError

# langdetect's Naive Bayes classifier samples internally and gives
# inconsistent results run-to-run on short/ambiguous text unless seeded.
DetectorFactory.seed = 0


def detect_language(text: str) -> str:
    """Return a best-guess language code for `text`. Raises DetectionError on failure."""
    try:
        return _detect(text)
    except LangDetectException as exc:
        raise DetectionError("could not detect the language of the given text") from exc
