"""Guards on the one dataset in this project that was written by hand.

The anchor coordinates are not derived from anything: they were typed in. These
tests pin down the properties that make the map honest, so a later edit cannot
quietly reintroduce a marker for a language that doesn't exist, a coordinate
that isn't on Earth, or a default that puts an unknown language somewhere
plausible-looking.

The stronger check -- that each coordinate lands inside the right country --
needs the Natural Earth polygons and lives in tools/verify_anchors.py, which
resolved all 73 against real geometry. This file covers what can be asserted
without an 820 kB download.
"""

from __future__ import annotations

from translator.geography import LANGUAGE_ANCHORS, anchors_for
from translator.languages import LANGUAGE_CODES

# Esperanto is constructed and Latin has no living centre. Both are absent by
# decision, and naming them here means adding a third omission has to be
# deliberate rather than accidental.
DELIBERATE_OMISSIONS = {"eo", "la"}


def test_every_anchor_describes_a_language_we_actually_support():
    # A dozen anchors once described languages the app does not offer. Harmless
    # to the UI, which filters them, but it was unverified data claiming to be
    # about something that wasn't there.
    unsupported = set(LANGUAGE_ANCHORS) - set(LANGUAGE_CODES)
    assert unsupported == set(), f"anchors for unsupported languages: {sorted(unsupported)}"


def test_omissions_are_the_documented_ones():
    missing = set(LANGUAGE_CODES) - set(LANGUAGE_ANCHORS)
    assert missing == DELIBERATE_OMISSIONS, f"unexpected omissions: {sorted(missing - DELIBERATE_OMISSIONS)}"


def test_coordinates_are_on_earth():
    for code, (city, lat, lon) in LANGUAGE_ANCHORS.items():
        assert -90.0 <= lat <= 90.0, f"{code} ({city}) latitude out of range: {lat}"
        assert -180.0 <= lon <= 180.0, f"{code} ({city}) longitude out of range: {lon}"


def test_no_null_island():
    # (0, 0) is in the Gulf of Guinea and is the classic signature of a missing
    # or defaulted coordinate rather than a real place.
    for code, (city, lat, lon) in LANGUAGE_ANCHORS.items():
        assert (lat, lon) != (0.0, 0.0), f"{code} ({city}) sits at null island"


def test_every_anchor_names_a_city():
    for code, (city, _lat, _lon) in LANGUAGE_ANCHORS.items():
        assert city and city.strip(), f"{code} has no city label"


def test_projection_is_exact_for_known_points():
    by_code = {a["code"]: a for a in anchors_for(LANGUAGE_CODES)}
    # London is within a fifth of a degree of the prime meridian, so it must
    # land at the horizontal centre of an equirectangular map.
    assert abs(by_code["en"]["x"] - 0.5) < 0.001
    # Tokyo is far east; Reykjavik is far north. Both are strong directional
    # checks that a sign error would break.
    assert by_code["ja"]["x"] > 0.85
    assert by_code["is"]["y"] < 0.15
    # Jakarta is south of the equator, so it must fall below the midline.
    assert by_code["id"]["y"] > 0.5


def test_projection_stays_within_the_unit_square():
    for anchor in anchors_for(LANGUAGE_CODES):
        assert 0.0 <= anchor["x"] <= 1.0, anchor
        assert 0.0 <= anchor["y"] <= 1.0, anchor


def test_anchors_for_filters_rather_than_defaulting():
    # An unknown code must produce no marker at all. Falling back to a default
    # position would put a language somewhere it has no business being, which
    # is worse than showing nothing.
    assert anchors_for({"nonexistent-code"}) == []


def test_anchors_for_returns_only_requested_codes():
    subset = anchors_for({"en", "ja"})
    assert {a["code"] for a in subset} == {"en", "ja"}
