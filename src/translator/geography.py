"""Where each supported language has an anchor point on the map.

An honest description of what this data is, because the map built on it should
not claim more than it knows:

Each entry is ONE representative city for a language, with that city's real
latitude and longitude. It is an anchor for placing a marker, not a claim about
where a language is spoken. Most of these languages are spoken across many
countries, several are spoken on multiple continents, and a single point cannot
represent that. English is anchored to London and Spanish to Madrid because the
markers have to go somewhere -- not because those are the only or largest
populations. The UI says "anchor", never "spoken here".

Coordinates are the well-known positions of the named cities, rounded to two
decimals. Where a language has no single obvious centre, the entry is omitted
rather than guessed: Esperanto has no geography, and inventing one would be
exactly the kind of confident fabrication this file is trying to avoid.

Projection is equirectangular and done in the client: x = (lon + 180) / 360,
y = (90 - lat) / 180. That is a plain linear mapping, so marker positions are
arithmetically exact for the coordinates given -- any inaccuracy is in the
choice of city, which is a stated judgement, not in the maths.
"""

from __future__ import annotations

# code -> (city label, latitude, longitude)
LANGUAGE_ANCHORS: dict[str, tuple[str, float, float]] = {
    "af": ("Pretoria", -25.75, 28.19),
    "sq": ("Tirana", 41.33, 19.82),
    "am": ("Addis Ababa", 9.02, 38.75),
    "ar": ("Cairo", 30.04, 31.24),
    "hy": ("Yerevan", 40.18, 44.51),
    "az": ("Baku", 40.41, 49.87),
    "eu": ("Bilbao", 43.26, -2.93),
    "bn": ("Dhaka", 23.81, 90.41),
    "bg": ("Sofia", 42.70, 23.32),
    "ca": ("Barcelona", 41.39, 2.17),
    "zh-cn": ("Beijing", 39.90, 116.41),
    "zh-tw": ("Taipei", 25.03, 121.57),
    "hr": ("Zagreb", 45.81, 15.98),
    "cs": ("Prague", 50.08, 14.44),
    "da": ("Copenhagen", 55.68, 12.57),
    "nl": ("Amsterdam", 52.37, 4.90),
    "en": ("London", 51.51, -0.13),
    "et": ("Tallinn", 59.44, 24.75),
    "fi": ("Helsinki", 60.17, 24.94),
    "fr": ("Paris", 48.86, 2.35),
    "gl": ("Santiago de Compostela", 42.88, -8.55),
    "ka": ("Tbilisi", 41.72, 44.78),
    "de": ("Berlin", 52.52, 13.40),
    "el": ("Athens", 37.98, 23.73),
    "gu": ("Ahmedabad", 23.02, 72.57),
    "he": ("Tel Aviv", 32.09, 34.78),
    "hi": ("Delhi", 28.61, 77.21),
    "hu": ("Budapest", 47.50, 19.04),
    "is": ("Reykjavik", 64.15, -21.94),
    "id": ("Jakarta", -6.21, 106.85),
    "ga": ("Dublin", 53.35, -6.26),
    "it": ("Rome", 41.90, 12.50),
    "ja": ("Tokyo", 35.68, 139.69),
    "kn": ("Bengaluru", 12.97, 77.59),
    "kk": ("Astana", 51.17, 71.43),
    "km": ("Phnom Penh", 11.56, 104.92),
    "ko": ("Seoul", 37.57, 126.98),
    "lv": ("Riga", 56.95, 24.11),
    "lt": ("Vilnius", 54.69, 25.28),
    "mk": ("Skopje", 41.996, 21.43),
    "ms": ("Kuala Lumpur", 3.14, 101.69),
    "ml": ("Kochi", 9.93, 76.27),
    "mr": ("Mumbai", 19.08, 72.88),
    "mn": ("Ulaanbaatar", 47.89, 106.91),
    "my": ("Yangon", 16.87, 96.20),
    "ne": ("Kathmandu", 27.72, 85.32),
    "no": ("Oslo", 59.91, 10.75),
    "fa": ("Tehran", 35.69, 51.39),
    "pl": ("Warsaw", 52.23, 21.01),
    "pt": ("Lisbon", 38.72, -9.14),
    "pa": ("Lahore", 31.55, 74.34),
    "ro": ("Bucharest", 44.43, 26.10),
    "ru": ("Moscow", 55.76, 37.62),
    "sr": ("Belgrade", 44.79, 20.45),
    "si": ("Colombo", 6.93, 79.86),
    "sk": ("Bratislava", 48.15, 17.11),
    "sl": ("Ljubljana", 46.06, 14.51),
    "es": ("Madrid", 40.42, -3.70),
    "sw": ("Nairobi", -1.29, 36.82),
    "sv": ("Stockholm", 59.33, 18.07),
    "tl": ("Manila", 14.60, 120.98),
    "ta": ("Chennai", 13.08, 80.27),
    "te": ("Hyderabad", 17.39, 78.49),
    "th": ("Bangkok", 13.76, 100.50),
    "tr": ("Istanbul", 41.01, 28.98),
    "uk": ("Kyiv", 50.45, 30.52),
    "ur": ("Karachi", 24.86, 67.01),
    "uz": ("Tashkent", 41.30, 69.24),
    "vi": ("Hanoi", 21.03, 105.85),
    "cy": ("Cardiff", 51.48, -3.18),
    "zu": ("Durban", -29.86, 31.02),
    "so": ("Mogadishu", 2.05, 45.32),
    "ht": ("Port-au-Prince", 18.59, -72.31),
    "eo": None,  # type: ignore[dict-item]
}

# Deliberately absent: Esperanto (constructed, no geography) and Latin (no
# living population centre; anchoring it to Rome would state something about
# today that isn't true). Rather than pin either somewhere arbitrary, they are
# dropped -- a marker in a made-up place would be a small lie in a feature
# whose whole point is showing real places.
LANGUAGE_ANCHORS = {code: value for code, value in LANGUAGE_ANCHORS.items() if value is not None}


def anchors_for(codes: frozenset[str] | set[str]) -> list[dict[str, object]]:
    """Anchor points for the languages we actually support, ready for the map.

    Codes without an anchor are omitted rather than defaulted, so the map shows
    fewer markers instead of wrong ones.
    """
    out: list[dict[str, object]] = []
    for code, (city, lat, lon) in sorted(LANGUAGE_ANCHORS.items()):
        if code not in codes:
            continue
        out.append(
            {
                "code": code,
                "city": city,
                "lat": lat,
                "lon": lon,
                # Equirectangular projection, computed here so the client does
                # no geography of its own.
                "x": round((lon + 180.0) / 360.0, 5),
                "y": round((90.0 - lat) / 180.0, 5),
            }
        )
    return out
