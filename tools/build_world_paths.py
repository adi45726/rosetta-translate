"""Turn Natural Earth country borders into SVG paths for the language map.

Run this only when the border data needs regenerating:

    python tools/build_world_paths.py path/to/ne_110m_admin_0_countries.geojson

Source: Natural Earth, 1:110m Admin 0 Countries, via
https://github.com/nvkelso/natural-earth-vector -- public domain.

Why this is a build step rather than runtime work: the raw GeoJSON is 820 kB,
and none of it changes between requests. Projecting and simplifying once, then
serving the result as a static file, keeps the shipped payload small without
approximating anything at request time.

The projection matches src/translator/geography.py exactly -- equirectangular,
x = (lon + 180) / 360, y = (90 - lat) / 180 -- because the borders and the
language markers have to share one coordinate space or the markers will sit in
the wrong countries.

Simplification is Douglas-Peucker with a tolerance in output pixels. It drops
vertices that fall within the tolerance of the line they sit on, so coastlines
lose detail but never move: no point is invented or displaced, only omitted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WIDTH = 720.0
HEIGHT = 360.0
# In output pixels. At 0.35 the outlines stay recognisable at the size the map
# is drawn while discarding most of the vertices in the source data.
TOLERANCE = 0.35
# Rings smaller than this in bounding box are dropped: at map scale they are
# sub-pixel specks, and keeping ~1500 of them triples the file for no visible
# difference.
MIN_RING_EXTENT = 1.2


def project(lon: float, lat: float) -> tuple[float, float]:
    return ((lon + 180.0) / 360.0) * WIDTH, ((90.0 - lat) / 180.0) * HEIGHT


def _perpendicular_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    (px, py), (sx, sy), (ex, ey) = point, start, end
    dx, dy = ex - sx, ey - sy
    if dx == 0 and dy == 0:
        return ((px - sx) ** 2 + (py - sy) ** 2) ** 0.5
    t = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return ((px - (sx + t * dx)) ** 2 + (py - (sy + t * dy)) ** 2) ** 0.5


def simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker. Keeps a subset of the original points; invents none."""
    if len(points) < 3:
        return points
    first, last = points[0], points[-1]
    index, furthest = -1, 0.0
    for i in range(1, len(points) - 1):
        d = _perpendicular_distance(points[i], first, last)
        if d > furthest:
            index, furthest = i, d
    if furthest <= tolerance:
        return [first, last]
    left = simplify(points[: index + 1], tolerance)
    right = simplify(points[index:], tolerance)
    return left[:-1] + right


def ring_to_path(ring: list[list[float]]) -> str | None:
    projected = [project(float(lon), float(lat)) for lon, lat, *_ in ring]
    xs = [p[0] for p in projected]
    ys = [p[1] for p in projected]
    if max(xs) - min(xs) < MIN_RING_EXTENT and max(ys) - min(ys) < MIN_RING_EXTENT:
        return None

    reduced = simplify(projected, TOLERANCE)
    if len(reduced) < 3:
        return None
    head = f"M{reduced[0][0]:.1f} {reduced[0][1]:.1f}"
    rest = "".join(f"L{x:.1f} {y:.1f}" for x, y in reduced[1:])
    return head + rest + "Z"


def rings_of(geometry: dict) -> list[list[list[float]]]:
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        return list(coords)
    if kind == "MultiPolygon":
        return [ring for polygon in coords for ring in polygon]
    return []


def main(source: Path, destination: Path) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    paths: list[str] = []
    for feature in data.get("features", []):
        for ring in rings_of(feature.get("geometry") or {}):
            path = ring_to_path(ring)
            if path:
                paths.append(path)

    payload = {
        "source": "Natural Earth 1:110m Admin 0 Countries (public domain)",
        "projection": "equirectangular",
        "viewBox": [WIDTH, HEIGHT],
        "tolerance_px": TOLERANCE,
        "paths": paths,
    }
    destination.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"{len(paths)} rings -> {destination} ({destination.stat().st_size // 1024} kB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    root = Path(__file__).resolve().parents[1]
    main(Path(sys.argv[1]), root / "web" / "static" / "data" / "world-borders.json")
