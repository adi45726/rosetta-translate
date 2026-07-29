"""Practice Partner: roleplay conversation in a language you're learning.

Iris talks *with* you. This talks *at* you in the language you're learning, in
character, and marks your work while doing it -- one turn produces the reply,
a gloss of it, a correction of what you just wrote, and a phrase you could use
next.

Two decisions shape the prompt more than anything else:

Corrections are separate from the reply. A tutor that inlines fixes ("I think
you mean 'je suis'...") breaks the roleplay every single turn, and the point of
roleplay is that it doesn't break. The character answers naturally; the
correction arrives beside it as marked-up feedback the UI can style, dismiss,
or ignore.

`correction` is null far more often than not. Models asked to critique will
find something to critique, so the prompt says explicitly that natural,
understandable input gets no correction at all -- a learner corrected on every
turn stops writing.
"""

from __future__ import annotations

from typing import Any

from .exceptions import ProviderError
from .groq_client import (
    _clean_str,
    _content_of,
    _parse_payload,
    _post,
    _reasoning_effort_for,
    api_key,
    model_name,
)
from .languages import is_supported, language_name

MAX_MESSAGE_LENGTH = 600
MAX_HISTORY_TURNS = 10

# Each scenario names who the model plays and where. Vague settings ("practise
# Spanish") produce a generic chatbot; a named role with a goal produces a
# character who actually pushes the conversation somewhere.
SCENARIOS: dict[str, dict[str, str]] = {
    "cafe": {
        "label": "At a café",
        "role": "a friendly barista taking the learner's order",
        "goal": "take their order, offer something extra, settle the bill",
    },
    "directions": {
        "label": "Asking directions",
        "role": "a local passer-by who knows the area well",
        "goal": "understand where they want to go and guide them there",
    },
    "hotel": {
        "label": "Hotel check-in",
        "role": "a receptionist checking the learner into a hotel",
        "goal": "find the booking, explain the room and the breakfast times",
    },
    "shopping": {
        "label": "Shopping",
        "role": "a shop assistant in a clothing store",
        "goal": "help them find a size and colour, and mention the price",
    },
    "doctor": {
        "label": "At the doctor",
        "role": "a calm doctor at a walk-in clinic",
        "goal": "ask what hurts, how long for, and suggest something simple",
    },
    "newfriend": {
        "label": "Making a friend",
        "role": "a curious person the learner just met at a language exchange",
        "goal": "find out about them and share a little about yourself",
    },
    "interview": {
        "label": "Job interview",
        "role": "a warm but professional hiring manager",
        "goal": "ask about their experience, strengths, and why this job",
    },
    "phone": {
        "label": "Phone call",
        "role": "someone taking a restaurant booking over the phone",
        "goal": "get the date, time, party size and a name",
    },
}

LEVELS: dict[str, str] = {
    "beginner": (
        "Use only very common words and short present-tense sentences. Speak slowly and "
        "simply, one idea per sentence. Never use idioms or slang."
    ),
    "intermediate": (
        "Use everyday conversational language including common past and future forms. "
        "A little idiom is fine if it is very common."
    ),
    "advanced": (
        "Speak as you would to a native speaker: natural pace, idiom, humour, and "
        "complex sentences where they fit."
    ),
}


def scenario_options() -> list[dict[str, str]]:
    return [{"id": key, "label": value["label"]} for key, value in SCENARIOS.items()]


def _require_key() -> str:
    key = api_key()
    if key is None:
        raise ProviderError("the practice partner needs GROQ_API_KEY to be set")
    return key


def _system_prompt(language: str, scenario: str, level: str) -> str:
    target = language_name(language)
    setting = SCENARIOS[scenario]
    return (
        f"You are roleplaying {setting['role']}. The person you are speaking to is "
        f"learning {target}. Your aim in the scene: {setting['goal']}.\n\n"
        "How to play it:\n"
        f"- Speak ONLY {target} in the `reply` field. Never break character, never "
        f"switch to another language, and never mention that this is practice.\n"
        f"- {LEVELS[level]}\n"
        "- Keep replies to one or two sentences, and end most turns with a question, so "
        "the learner always has something to answer.\n"
        "- Stay in the scene even if their message is odd or off-topic; react as your "
        "character would.\n\n"
        "Marking their message:\n"
        "- `correction` must be null when their message was natural and understandable. "
        "Small awkwardness is fine. Only correct real mistakes -- wrong grammar, wrong "
        "word, or something a native speaker would not say.\n"
        "- When you do correct, keep the explanation to one short sentence, written in "
        "English, aimed at a learner.\n"
        "- Never correct their very first message if it is a greeting.\n\n"
        "Reply with ONLY this JSON object, no markdown fences:\n"
        '{"reply": <your line, in ' + target + '>, '
        '"gloss": <a plain English translation of your line>, '
        '"correction": <null, or {"original": <their words>, "fixed": <corrected '
        'version>, "why": <one short sentence in English>}>, '
        '"score": <0-100, how natural their last message was; 100 if there was nothing '
        'to fix. Use null for their opening greeting>, '
        '"suggestion": <one short phrase in ' + target + " they could say next>, "
        '"suggestion_gloss": <that phrase in English>}'
    )


def _sanitise_history(history: Any) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []
    clean: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = _clean_str(item.get("content"))
        if role not in ("user", "assistant") or content is None:
            continue
        clean.append({"role": role, "content": content[:MAX_MESSAGE_LENGTH]})
    return clean[-(MAX_HISTORY_TURNS * 2):]


def _clean_correction(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    fixed = _clean_str(value.get("fixed"))
    why = _clean_str(value.get("why"))
    # A correction with no replacement text is noise; drop the whole thing
    # rather than render an empty card.
    if fixed is None or why is None:
        return None
    return {
        "original": _clean_str(value.get("original")) or "",
        "fixed": fixed,
        "why": why,
    }


def _clean_score(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(value)))


def practice(
    message: str,
    language: str,
    scenario: str = "cafe",
    level: str = "beginner",
    history: Any = None,
) -> dict[str, Any]:
    """One turn of roleplay practice. `message` may be empty to open the scene."""
    key = _require_key()
    if not is_supported(language):
        raise ProviderError("unsupported practice language")
    if scenario not in SCENARIOS:
        raise ProviderError("unknown scenario")
    if level not in LEVELS:
        raise ProviderError("unknown level")

    text = _clean_str(message) or ""
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ProviderError(f"message must be at most {MAX_MESSAGE_LENGTH} characters")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _system_prompt(language, scenario, level)}
    ]
    messages.extend(_sanitise_history(history))
    # An empty message means "open the scene" -- the character speaks first, so
    # the learner never faces a blank box wondering how to begin.
    messages.append(
        {"role": "user", "content": text or "[Begin the scene. Greet me in character.]"}
    )

    model = model_name()
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    effort = _reasoning_effort_for(model)
    if effort:
        payload["reasoning_effort"] = effort

    parsed = _parse_payload(_content_of(_post(payload, key)))
    reply = _clean_str(parsed.get("reply"))
    if reply is None:
        raise ProviderError("the practice partner had nothing to say")

    return {
        "reply": reply,
        "gloss": _clean_str(parsed.get("gloss")),
        # No correction on the opening turn: there is nothing of theirs to mark.
        "correction": _clean_correction(parsed.get("correction")) if text else None,
        "score": _clean_score(parsed.get("score")) if text else None,
        "suggestion": _clean_str(parsed.get("suggestion")),
        "suggestion_gloss": _clean_str(parsed.get("suggestion_gloss")),
        "language": language,
        "language_name": language_name(language),
    }
