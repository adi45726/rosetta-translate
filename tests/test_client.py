from unittest.mock import Mock, patch

import pytest
import requests

from translator.client import translate
from translator.exceptions import ProviderError, ProviderUnavailableError


def _mock_response(json_data, status_code=200):
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = Mock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    return resp


@patch("translator.client.requests.get")
def test_translate_success(mock_get):
    mock_get.return_value = _mock_response(
        {"responseStatus": 200, "responseData": {"translatedText": "Hola mundo"}}
    )
    assert translate("Hello world", "en", "es") == "Hola mundo"
    mock_get.assert_called_once()
    _, kwargs = mock_get.call_args
    assert kwargs["params"] == {"q": "Hello world", "langpair": "en|es"}


@patch("translator.client.requests.get")
def test_translate_prefers_higher_quality_match_over_top_level_field(mock_get):
    # Regression test: confirmed live against api.mymemory.translated.net for
    # "Good morning, how are you?" en->es. The top-level responseData field
    # picked a quality:"0" crowd-sourced entry (wrong translation) over a
    # quality:"74" entry sitting right below it in `matches` (correct).
    mock_get.return_value = _mock_response(
        {
            "responseStatus": 200,
            "responseData": {"translatedText": "Ahora que no estás, que no te puedo ver"},
            "matches": [
                {
                    "match": 1,
                    "quality": "0",
                    "created-by": "Public_Corpora",
                    "translation": "Ahora que no estás, que no te puedo ver",
                },
                {
                    "match": 0.99,
                    "quality": "74",
                    "created-by": "MateCat",
                    "translation": "Buenos días, ¿cómo está?",
                },
            ],
        }
    )
    assert translate("Good morning, how are you?", "en", "es") == "Buenos días, ¿cómo está?"


@patch("translator.client.requests.get")
def test_translate_falls_back_to_top_level_field_when_no_good_matches(mock_get):
    mock_get.return_value = _mock_response(
        {
            "responseStatus": 200,
            "responseData": {"translatedText": "some MT-only result"},
            "matches": [],
        }
    )
    assert translate("hi", "en", "es") == "some MT-only result"


@patch("translator.client.requests.get")
def test_translate_ignores_all_low_quality_matches_and_falls_back(mock_get):
    mock_get.return_value = _mock_response(
        {
            "responseStatus": 200,
            "responseData": {"translatedText": "fallback text"},
            "matches": [
                {"match": 1, "quality": "0", "created-by": "x", "translation": "garbage"},
                {"match": 0.9, "quality": "10", "created-by": "y", "translation": "also garbage"},
            ],
        }
    )
    assert translate("hi", "en", "es") == "fallback text"


@patch("translator.client.requests.get")
def test_translate_same_language_provider_error(mock_get):
    # MyMemory answers this with HTTP 200 but responseStatus "403" in the body.
    mock_get.return_value = _mock_response(
        {
            "responseStatus": "403",
            "responseDetails": "PLEASE SELECT TWO DISTINCT LANGUAGES",
            "responseData": {"translatedText": "PLEASE SELECT TWO DISTINCT LANGUAGES"},
        }
    )
    with pytest.raises(ProviderError, match="DISTINCT LANGUAGES"):
        translate("hi", "en", "en")


@patch("translator.client.requests.get")
def test_translate_invalid_language_provider_error(mock_get):
    mock_get.return_value = _mock_response(
        {
            "responseStatus": "403",
            "responseDetails": "'ZZ' IS AN INVALID TARGET LANGUAGE",
            "responseData": {"translatedText": "'ZZ' IS AN INVALID TARGET LANGUAGE"},
        }
    )
    with pytest.raises(ProviderError, match="INVALID TARGET LANGUAGE"):
        translate("hi", "en", "zz")


@patch("translator.client.requests.get")
def test_translate_missing_translated_text_is_provider_error(mock_get):
    mock_get.return_value = _mock_response({"responseStatus": 200, "responseData": {}})
    with pytest.raises(ProviderError, match="no text"):
        translate("hi", "en", "es")


@patch("translator.client.requests.get")
def test_translate_network_error_raises_unavailable(mock_get):
    mock_get.side_effect = requests.ConnectionError("boom")
    with pytest.raises(ProviderUnavailableError):
        translate("hi", "en", "es")


@patch("translator.client.requests.get")
def test_translate_timeout_raises_unavailable(mock_get):
    mock_get.side_effect = requests.Timeout("too slow")
    with pytest.raises(ProviderUnavailableError):
        translate("hi", "en", "es")


@patch("translator.client.requests.get")
def test_translate_invalid_json_raises_unavailable(mock_get):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.side_effect = ValueError("not json")
    mock_get.return_value = resp
    with pytest.raises(ProviderUnavailableError):
        translate("hi", "en", "es")


@patch("translator.client.requests.get")
def test_translate_http_error_status_raises_unavailable(mock_get):
    mock_get.return_value = _mock_response({}, status_code=500)
    with pytest.raises(ProviderUnavailableError):
        translate("hi", "en", "es")
