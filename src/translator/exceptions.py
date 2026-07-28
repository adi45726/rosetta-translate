"""Exceptions raised by the translator package, caught at the Flask boundary."""

from __future__ import annotations


class TranslationError(Exception):
    """Base class for translation failures."""


class ProviderError(TranslationError):
    """The translation provider reached us but reported a failure (bad language pair, etc.)."""


class ProviderUnavailableError(TranslationError):
    """The translation provider could not be reached (network error, timeout, bad response)."""


class DetectionError(TranslationError):
    """Source-language auto-detection failed (empty/too-short/ambiguous text)."""
