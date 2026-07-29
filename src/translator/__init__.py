"""Rosetta's translation core: language list, provider clients, and detection.

Callers should use `translate()` (the engine router) rather than reaching for
a specific provider module -- it handles provider selection, auto-detect
resolution, and falling back when the preferred provider is unavailable.
"""

from .client import translate_with_alternates
from .companion import EXPRESSIONS, FEELINGS, chat, read_expression
from .detect import detect_language
from .engine import (
    active_provider,
    engine_label,
    max_text_length,
    rewrite_text,
    scan_and_translate_image,
    transcribe_audio,
    translate,
)
from .exceptions import DetectionError, ProviderError, ProviderUnavailableError, TranslationError
from .groq_client import WRITING_AUDIENCES, WRITING_MODES, WRITING_TONES
from .languages import AUTO_DETECT, LANGUAGE_CODES, LANGUAGE_NAMES, LANGUAGES, is_supported, language_name
from .result import PROVIDER_GROQ, PROVIDER_MYMEMORY, PROVIDER_NONE, TranslationResult
from .tutor import LEVELS, SCENARIOS, practice, scenario_options

__all__ = [
    "AUTO_DETECT",
    "LANGUAGES",
    "LANGUAGE_CODES",
    "LANGUAGE_NAMES",
    "PROVIDER_GROQ",
    "PROVIDER_MYMEMORY",
    "PROVIDER_NONE",
    "DetectionError",
    "ProviderError",
    "ProviderUnavailableError",
    "TranslationError",
    "TranslationResult",
    "active_provider",
    "detect_language",
    "engine_label",
    "is_supported",
    "language_name",
    "max_text_length",
    "translate",
    "rewrite_text",
    "transcribe_audio",
    "scan_and_translate_image",
    "WRITING_MODES",
    "WRITING_TONES",
    "WRITING_AUDIENCES",
    "translate_with_alternates",
    "EXPRESSIONS",
    "FEELINGS",
    "chat",
    "read_expression",
    "practice",
    "scenario_options",
    "SCENARIOS",
    "LEVELS",
]
