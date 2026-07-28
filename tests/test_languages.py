from translator.languages import AUTO_DETECT, LANGUAGE_CODES, LANGUAGES, is_supported, language_name


def test_no_duplicate_codes():
    codes = [code for code, _ in LANGUAGES]
    assert len(codes) == len(set(codes))


def test_no_duplicate_names():
    names = [name for _, name in LANGUAGES]
    assert len(names) == len(set(names))


def test_sorted_by_name():
    names = [name for _, name in LANGUAGES]
    assert names == sorted(names)


def test_auto_detect_is_not_a_real_language_code():
    assert AUTO_DETECT not in LANGUAGE_CODES


def test_is_supported():
    assert is_supported("en")
    assert is_supported("zh-cn")
    assert not is_supported("xx")
    assert not is_supported(AUTO_DETECT)


def test_language_name_known_and_unknown():
    assert language_name("en") == "English"
    assert language_name("xx") == "xx"  # falls back to the code itself


def test_reasonable_size():
    # "universal translator" should mean more than a handful of languages,
    # but a plain <select> stops being usable well before, say, 300.
    assert 40 <= len(LANGUAGES) <= 150
