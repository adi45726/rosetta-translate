from unittest.mock import patch

import pytest

from translator import engine
from translator.exceptions import DetectionError, ProviderError, ProviderUnavailableError
from translator.result import TranslationResult


@pytest.fixture
def groq_key(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")


# ─── Provider selection ─────────────────────────────────────────────────────


def test_defaults_to_mymemory_without_a_key():
    assert engine.active_provider() == "mymemory"
    assert engine.max_text_length() == 500
    assert engine.engine_label() == "MyMemory"


def test_prefers_groq_when_configured(groq_key):
    assert engine.active_provider() == "groq"
    assert engine.max_text_length() == 2000


def test_engine_label_strips_the_vendor_prefix(groq_key, monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    assert engine.engine_label() == "Groq · gpt-oss-120b"


# ─── Same-language shortcut ─────────────────────────────────────────────────


@patch("translator.engine.groq_client.translate")
@patch("translator.engine.mymemory.translate_with_alternates")
def test_same_language_never_calls_a_provider(mock_mymemory, mock_groq, groq_key):
    result = engine.translate("hello", "en", "en")
    assert result.text == "hello"
    assert result.provider == "none"
    mock_groq.assert_not_called()
    mock_mymemory.assert_not_called()


@patch("translator.engine.mymemory.translate_with_alternates")
@patch("translator.engine.detect_language", return_value="en")
def test_auto_detect_resolving_to_the_target_short_circuits(mock_detect, mock_mymemory):
    result = engine.translate("hello there", "auto", "en")
    assert result.text == "hello there"
    assert result.detected_source == "en"
    assert result.provider == "none"
    mock_mymemory.assert_not_called()


# ─── Groq path ──────────────────────────────────────────────────────────────


@patch("translator.engine.groq_client.translate")
@patch("translator.engine.detect_language")
def test_groq_handles_auto_detect_without_langdetect(mock_detect, mock_groq, groq_key):
    mock_groq.return_value = TranslationResult(text="Bonjour", detected_source="en", provider="groq")

    result = engine.translate("Hello", "auto", "fr")

    assert result.detected_source == "en"
    assert result.provider == "groq"
    # The whole point of the Groq path: detection comes back with the
    # translation, so there is no separate langdetect step to be wrong.
    mock_detect.assert_not_called()
    assert mock_groq.call_args.args == ("Hello", "auto", "fr")


# ─── Fallback ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("failure", [ProviderUnavailableError("down"), ProviderError("bad key")])
@patch("translator.engine.groq_client.translate")
@patch("translator.engine.mymemory.translate_with_alternates")
def test_groq_failure_falls_back_to_mymemory(mock_mymemory, mock_groq, groq_key, failure):
    mock_groq.side_effect = failure
    mock_mymemory.return_value = TranslationResult(text="Hola", alternates=["Buenas"])

    result = engine.translate("Hello", "en", "es")

    assert result.text == "Hola"
    assert result.provider == "mymemory"
    mock_mymemory.assert_called_once_with("Hello", "en", "es")


@patch("translator.engine.groq_client.translate")
@patch("translator.engine.detect_language", return_value="it")
@patch("translator.engine.mymemory.translate_with_alternates")
def test_fallback_resolves_auto_detect_with_langdetect(mock_mymemory, mock_detect, mock_groq, groq_key):
    mock_groq.side_effect = ProviderUnavailableError("down")
    mock_mymemory.return_value = TranslationResult(text="Hello")

    result = engine.translate("Ciao", "auto", "en")

    assert result.detected_source == "it"
    assert result.provider == "mymemory"
    assert mock_mymemory.call_args.args == ("Ciao", "it", "en")


@patch("translator.engine.groq_client.translate")
@patch("translator.engine.mymemory.translate_with_alternates")
def test_text_too_long_for_the_fallback_reraises(mock_mymemory, mock_groq, groq_key):
    # MyMemory caps at 500 characters, so there is no degraded answer to give.
    # Surfacing Groq's failure beats silently truncating the user's text.
    mock_groq.side_effect = ProviderUnavailableError("down")

    with pytest.raises(ProviderUnavailableError):
        engine.translate("x" * 501, "en", "es")
    mock_mymemory.assert_not_called()


@patch("translator.engine.groq_client.translate")
def test_fallback_is_logged(mock_groq, groq_key, caplog):
    mock_groq.side_effect = ProviderUnavailableError("rate limited")
    with patch("translator.engine.mymemory.translate_with_alternates") as mock_mymemory:
        mock_mymemory.return_value = TranslationResult(text="Hola")
        engine.translate("Hello", "en", "es")
    assert "falling back" in caplog.text.lower()


# ─── Detection failures ─────────────────────────────────────────────────────


@patch("translator.engine.detect_language", side_effect=DetectionError("cannot tell"))
@patch("translator.engine.mymemory.translate_with_alternates")
def test_detection_failure_propagates(mock_mymemory, mock_detect):
    # A DetectionError is a problem with the input, not the provider, so it
    # must not be swallowed by the fallback machinery.
    with pytest.raises(DetectionError):
        engine.translate("12345", "auto", "es")
    mock_mymemory.assert_not_called()
