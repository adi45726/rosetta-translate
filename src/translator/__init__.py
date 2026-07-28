"""Rosetta's translation core: language list, provider client, and detection."""

from .client import translate
from .detect import detect_language
from .exceptions import DetectionError, ProviderError, ProviderUnavailableError, TranslationError
from .languages import AUTO_DETECT, LANGUAGE_CODES, LANGUAGE_NAMES, LANGUAGES, is_supported, language_name

__all__ = [
    "AUTO_DETECT",
    "LANGUAGES",
    "LANGUAGE_CODES",
    "LANGUAGE_NAMES",
    "DetectionError",
    "ProviderError",
    "ProviderUnavailableError",
    "TranslationError",
    "detect_language",
    "is_supported",
    "language_name",
    "translate",
]
