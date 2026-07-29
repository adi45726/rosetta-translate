"""The shape every provider returns, so callers never learn which one answered.

Lives in its own module (rather than next to a provider) because both the
MyMemory client and the Groq client construct it, and neither should have to
import the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# `provider` values. "none" means no provider was called at all -- the
# source and target language were the same, so the input was echoed back.
PROVIDER_NONE = "none"
PROVIDER_MYMEMORY = "mymemory"
PROVIDER_GROQ = "groq"


@dataclass(frozen=True, slots=True)
class TranslationResult:
    text: str
    alternates: list[str] = field(default_factory=list)
    # Set only when the caller asked for auto-detection. MyMemory can't do
    # this (langdetect resolves it before the call); Groq returns it inline.
    detected_source: str | None = None
    # Latin-script reading of `text`, when the target is a non-Latin script
    # and the provider can supply one. Groq only.
    romanization: str | None = None
    # A short translator's note about a genuine ambiguity ("formal register
    # assumed"). Groq only, and usually None.
    note: str | None = None
    provider: str = PROVIDER_MYMEMORY
