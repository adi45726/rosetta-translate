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
