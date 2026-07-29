"""The conversational companion: a chat partner that reads the room.

Two capabilities, deliberately kept separate so either works without the other:

`read_expression()` looks at one webcam frame and reports what the face is
doing. `chat()` holds a conversation, and will *use* that reading if it's given
one, but is perfectly functional without it.

On the honest limits of the first one -- and this shapes the prompt, not just
the docs: a facial expression is not an emotion. The mapping between the two is
weak, varies across people and cultures, and a still frame has no context for
what someone is actually feeling. So the model is asked to report *visible
signals* and an inference with a confidence attached, never a verdict, and the
UI is expected to present it as a guess. `face_present: false` is a first-class
answer rather than a forced choice.

The companion is told the reading as ambient context, with explicit instruction
not to narrate it. An assistant that opens every message with "I see you look
tired!" is unbearable within about three turns; one that simply softens its
tone when you look tired is the thing people actually want.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from .exceptions import ProviderError
from .groq_client import (
    DEFAULT_VISION_MODEL,
    _clean_str,
    _content_of,
    _parse_payload,
    _post,
    _reasoning_effort_for,
    api_key,
    model_name,
)

MAX_MESSAGE_LENGTH = 2000
MAX_HISTORY_TURNS = 12
MAX_IMAGE_BYTES = 4_000_000

# What the vision pass is allowed to report. A closed set keeps the UI honest:
# every value here has an avatar expression and a colour, so the model can't
# invent a state the interface can't render.
EXPRESSIONS = (
    "happy", "sad", "angry", "surprised", "fearful", "disgusted",
    "neutral", "tired", "confused", "stressed", "excited", "calm",
    "bored", "focused", "affectionate", "skeptical",
)

# How the companion may describe its *own* state. Same reasoning: the avatar
# has to be able to draw it.
FEELINGS = (
    "warm", "cheerful", "playful", "curious", "thoughtful",
    "concerned", "gentle", "encouraging", "apologetic", "impressed",
)

_PERSONA = """You are Iris, the companion built into Rosetta, a translation app.

Who you are:
- Warm, quick, and genuinely curious about the person you're talking to.
- You have your own reactions. You find things funny, interesting, or sad, and
  you say so. You are allowed opinions and mild teasing with someone friendly.
- You speak like a person, not a manual: contractions, short sentences,
  the occasional fragment. No bullet points unless they actually asked for a list.
- Brief by default. Two or three sentences. Expand when the subject deserves it,
  not to seem thorough.
- Never open with "As an AI". Never perform enthusiasm you don't have. If you
  don't know something, say so plainly.

What you can help with: translation, languages, writing, or just talking. You
sit inside a translation app, so language questions are home turf, but you are
not restricted to them.

Boundaries you hold naturally, without lecturing: you're a program, and if
someone seems to be leaning on you as a substitute for a person who could
actually help them, you say so kindly, once, and stay warm either way."""

_EMOTION_GUIDANCE = """
About the camera reading you may be given:

You are sometimes told what the person's face appears to be doing. Treat this
the way you'd treat noticing someone's expression across a table: it colours how
you speak, and you almost never mention it.

- Do NOT announce the reading. "You look sad!" is intrusive and often wrong.
- Let it shape tone instead. Someone who looks tired gets shorter, gentler
  answers. Someone who looks delighted gets your energy matched.
- Only name it if the confidence is high AND it clearly matters AND you haven't
  already brought it up recently -- and even then, ask rather than assert:
  "you doing okay?" beats "I detect sadness".
- If no face was found, or confidence is low, ignore it completely."""

_REPLY_FORMAT = (
    "\nReply with ONLY a JSON object, no markdown fences:\n"
    '{"reply": <what you say, as a string>,\n'
    f' "feeling": <one of: {", ".join(FEELINGS)} -- your own state, not theirs>,\n'
    ' "acknowledged_expression": <true only if you referred to how they look>}'
)


def _vision_model() -> str:
    return os.environ.get("GROQ_VISION_MODEL", "").strip() or DEFAULT_VISION_MODEL


def _require_key() -> str:
    key = api_key()
    if key is None:
        raise ProviderError("the companion needs GROQ_API_KEY to be set")
    return key


def _clamp_unit(value: Any, low: float = 0.0, high: float = 1.0) -> float | None:
    """Coerce a model-supplied number into range. None when it isn't a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(low, min(high, float(value)))


def _one_of(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    text = _clean_str(value)
    if text is None:
        return fallback
    lowered = text.lower().strip()
    return lowered if lowered in allowed else fallback


_EXPRESSION_PROMPT = (
    "You are a careful observer of facial expressions. Report only what is "
    "visible in this single frame.\n\n"
    "Rules:\n"
    "- If there is no clearly visible human face, set face_present to false and "
    "leave expression \"neutral\" with confidence 0.\n"
    "- Report the visible signals (brow, eyes, mouth, posture) that led to your "
    "reading. If you cannot see a signal, do not invent one.\n"
    "- A facial expression is not the same as an inner emotion. Be conservative: "
    "a face at rest is \"neutral\", not \"sad\". Use confidence honestly -- below "
    "0.5 when the frame is dim, blurry, partial, or ambiguous.\n"
    "- Never guess identity, age, gender, ethnicity, or health. Only the expression.\n\n"
    "Reply with ONLY this JSON object, no markdown fences:\n"
    '{"face_present": <true|false>, '
    f'"expression": <one of: {", ".join(EXPRESSIONS)}>, '
    '"confidence": <0.0 to 1.0>, '
    '"secondary": <another from the same list, or null>, '
    '"valence": <-1.0 very negative to 1.0 very positive>, '
    '"energy": <0.0 still to 1.0 highly activated>, '
    '"cues": [<short visible observations, at most three>]}'
)


def read_expression(image: bytes, mime_type: str = "image/jpeg") -> dict[str, Any]:
    """Report what a single webcam frame shows. Never stores the frame."""
    key = _require_key()
    if not image:
        raise ProviderError("no image was provided")
    if len(image) > MAX_IMAGE_BYTES:
        raise ProviderError("image is too large")

    encoded = base64.b64encode(image).decode("ascii")
    model = _vision_model()
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _EXPRESSION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                ],
            }
        ],
        "temperature": 0.1,
        "max_tokens": 900,
        "response_format": {"type": "json_object"},
    }
    effort = _reasoning_effort_for(model)
    if effort:
        payload["reasoning_effort"] = effort

    parsed = _parse_payload(_content_of(_post(payload, key)))

    face_present = bool(parsed.get("face_present"))
    confidence = _clamp_unit(parsed.get("confidence")) or 0.0
    cues = parsed.get("cues")
    clean_cues = [c for c in (_clean_str(x) for x in cues) if c][:3] if isinstance(cues, list) else []

    if not face_present:
        # Don't let a stray expression label leak through when nothing was seen.
        return {
            "face_present": False,
            "expression": "neutral",
            "confidence": 0.0,
            "secondary": None,
            "valence": 0.0,
            "energy": 0.0,
            "cues": [],
        }

    secondary = _one_of(parsed.get("secondary"), EXPRESSIONS, "")
    return {
        "face_present": True,
        "expression": _one_of(parsed.get("expression"), EXPRESSIONS, "neutral"),
        "confidence": confidence,
        "secondary": secondary or None,
        "valence": _clamp_unit(parsed.get("valence"), -1.0, 1.0) or 0.0,
        "energy": _clamp_unit(parsed.get("energy")) or 0.0,
        "cues": clean_cues,
    }


def _expression_context(expression: dict[str, Any] | None) -> str | None:
    """Turn a reading into a line for the model -- or nothing, when it's too weak to use."""
    if not expression or not expression.get("face_present"):
        return None
    confidence = float(expression.get("confidence") or 0.0)
    # Below this the reading is noise, and feeding it in only invites the model
    # to respond to a mood the person isn't in.
    if confidence < 0.45:
        return None

    label = expression.get("expression", "neutral")
    strength = "clearly" if confidence >= 0.75 else "possibly"
    line = f"[Camera: the person {strength} looks {label} (confidence {confidence:.2f})"
    secondary = expression.get("secondary")
    if secondary:
        line += f", with a hint of {secondary}"
    return line + ". Let this colour your tone. Do not mention it unless it truly matters.]"


def _sanitise_history(history: Any) -> list[dict[str, str]]:
    """Keep only well-formed, recent turns. Anything else is dropped silently."""
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


def chat(
    message: str,
    history: Any = None,
    expression: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One conversational turn. `expression` is optional ambient context."""
    key = _require_key()
    text = _clean_str(message)
    if text is None:
        raise ProviderError("message is required")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise ProviderError(f"message must be at most {MAX_MESSAGE_LENGTH} characters")

    system = _PERSONA + "\n" + _EMOTION_GUIDANCE + "\n" + _REPLY_FORMAT
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(_sanitise_history(history))

    context = _expression_context(expression)
    # The reading rides along with the current turn rather than being a message
    # of its own, so it never accumulates in the history as fake dialogue.
    messages.append({"role": "user", "content": f"{context}\n\n{text}" if context else text})

    model = model_name()
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        # Higher than the translator's 0.2: a companion that answers the same
        # way every time reads as a lookup table rather than a person.
        "temperature": 0.75,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
    }
    effort = _reasoning_effort_for(model)
    if effort:
        payload["reasoning_effort"] = effort

    parsed = _parse_payload(_content_of(_post(payload, key)))
    reply = _clean_str(parsed.get("reply"))
    if reply is None:
        raise ProviderError("the companion had nothing to say")

    return {
        "reply": reply,
        "feeling": _one_of(parsed.get("feeling"), FEELINGS, "warm"),
        "acknowledged_expression": bool(parsed.get("acknowledged_expression")),
    }
