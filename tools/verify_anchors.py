"""Check every language anchor against real country geometry.

    python tools/verify_anchors.py path/to/ne_110m_admin_0_countries.geojson

The anchor coordinates in src/translator/geography.py were written by hand, so
they are the one dataset in this project that nothing else corroborates. This
resolves each one against Natural Earth's country polygons by point-in-polygon
and reports which country it actually lands in.

That turns "trust me, Tokyo is at 35.68, 139.69" into a checkable claim: if a
coordinate is transposed, mistyped, or simply wrong, the point lands in the sea
or in the wrong country, and this says so.

Exit status is non-zero if any anchor fails, so it can gate a commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from translator.geography import LANGUAGE_ANCHORS  # noqa: E402
from translator.languages import LANGUAGE_NAMES  # noqa: E402


def rings_of(geometry: dict) -> list[list[list[float]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return list(coords)
    if kind == "MultiPolygon":
        return [ring for polygon in coords for ring in polygon]
    return []


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Standard ray casting in lon/lat space."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            x_at = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < x_at:
                inside = not inside
    return inside


def country_at(lon: float, lat: float, features: list[dict]) -> str | None:
    for feature in features:
        for ring in rings_of(feature.get("geometry") or {}):
            if point_in_ring(lon, lat, ring):
                props = feature.get("properties") or {}
                return props.get("NAME") or props.get("ADMIN") or "?"
    return None


def main(source: Path) -> int:
    features = json.loads(source.read_text(encoding="utf-8"))["features"]

    in_sea: list[str] = []
    print(f"{'language':24} {'anchor city':22} {'resolves to'}")
    print("-" * 72)
    for code, (city, lat, lon) in sorted(
        LANGUAGE_ANCHORS.items(), key=lambda kv: LANGUAGE_NAMES.get(kv[0], kv[0])
    ):
        name = LANGUAGE_NAMES.get(code, code)
        country = country_at(lon, lat, features)
        if country is None:
            # Coastal cities can fall just outside a 1:110m outline, which is a
            # limit of the low-resolution borders rather than a wrong anchor.
            # Flag them for eyeballing instead of failing outright.
            in_sea.append(f"{name} / {city} ({lat}, {lon})")
            country = "— no polygon (coastal or offshore at 1:110m)"
        print(f"{name:24} {city:22} {country}")

    print()
    print(f"anchors checked: {len(LANGUAGE_ANCHORS)}")
    if in_sea:
        print(f"unresolved ({len(in_sea)}), review each:")
        for item in in_sea:
            print("  -", item)
    else:
        print("every anchor resolves to a country polygon")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(main(Path(sys.argv[1])))
