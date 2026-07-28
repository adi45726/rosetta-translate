import pytest

from translator.detect import detect_language
from translator.exceptions import DetectionError


@pytest.mark.parametrize(
    "text,expected",
    [
        ("This is a clear and unambiguous sentence written in English.", "en"),
        ("Ceci est une phrase claire et sans ambiguïté écrite en français.", "fr"),
        ("Esta es una oración clara y sin ambigüedades escrita en español.", "es"),
        ("Dies ist ein klarer und eindeutiger Satz, der auf Deutsch geschrieben wurde.", "de"),
        ("これは日本語で書かれた明確で曖昧さのない文章です。", "ja"),
    ],
)
def test_detect_language_on_unambiguous_text(text, expected):
    assert detect_language(text) == expected


def test_detect_language_empty_text_raises():
    with pytest.raises(DetectionError):
        detect_language("")


def test_detect_language_whitespace_only_raises():
    with pytest.raises(DetectionError):
        detect_language("   ")
