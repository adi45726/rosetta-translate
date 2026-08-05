"""Browser tests for the language map.

The map is the feature with the most room to be quietly wrong: markers are
positioned by arithmetic, so a sign error or a mismatched projection puts every
dot somewhere plausible-looking but incorrect, and nothing throws. These check
the geometry rather than the plumbing.
"""

from __future__ import annotations

import pytest
from browser import Page, requires_chrome


@pytest.fixture(scope="module")
def page():
    with Page() as running:
        yield running


OPEN_MAP = """
  document.getElementById('auth-gate').classList.add('hidden');
  openMap();
  await new Promise((r) => setTimeout(r, 1200));
"""


@requires_chrome
def test_map_draws_every_anchor_and_the_borders(page):
    result = page.evaluate(OPEN_MAP + """
      return {
        markers: document.querySelectorAll('#map-markers g').length,
        borders: document.querySelectorAll('#map-borders path').length,
        graticule: document.querySelectorAll('#map-graticule line').length,
      };
    """)
    assert result["markers"] == 73, "every supported language with an anchor should have a marker"
    assert result["borders"] == 285, "Natural Earth rings should all be drawn"
    # Meridians every 30 degrees is 13 lines; parallels every 30 is 7.
    assert result["graticule"] == 20


@requires_chrome
def test_markers_are_visible_without_relying_on_an_animation(page):
    # They once used animation-fill-mode: both, so their only path to being
    # visible was a completed animation and any suppression left an empty map.
    result = page.evaluate(OPEN_MAP + """
      const g = document.querySelectorAll('#map-markers g');
      let visible = 0;
      g.forEach((n) => { if (Number(getComputedStyle(n).opacity) > 0.5) visible += 1; });
      return { total: g.length, visible };
    """)
    assert result["visible"] == result["total"]


@requires_chrome
def test_projection_places_known_cities_where_geography_says(page):
    # London is within a fifth of a degree of the prime meridian, so it must sit
    # at the horizontal centre. Tokyo far east, Reykjavik far north, Jakarta
    # south of the equator. A sign error breaks at least one of these.
    result = page.evaluate(OPEN_MAP + """
      const at = (code) => {
        const a = anchors.find((x) => x.code === code);
        return a ? { x: a.x, y: a.y } : null;
      };
      return { en: at('en'), ja: at('ja'), is: at('is'), id: at('id') };
    """)
    assert abs(result["en"]["x"] - 0.5) < 0.002
    assert result["ja"]["x"] > 0.85
    assert result["is"]["y"] < 0.15
    assert result["id"]["y"] > 0.5


@requires_chrome
def test_clicking_a_marker_sets_the_target_language(page):
    result = page.evaluate(OPEN_MAP + """
      const before = targetLang.value;
      const marker = document.querySelector('#map-markers g[data-code="ja"]');
      marker.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      return { before, after: targetLang.value };
    """)
    assert result["after"] == "ja"


@requires_chrome
def test_search_dims_non_matches_and_keeps_matches_bright(page):
    result = page.evaluate(OPEN_MAP + """
      const input = document.getElementById('map-search-input');
      input.value = 'japanese';
      input.dispatchEvent(new Event('input'));
      await new Promise((r) => setTimeout(r, 200));
      const all = [...document.querySelectorAll('#map-markers g')];
      return {
        dimmed: all.filter((g) => g.classList.contains('is-dimmed')).length,
        found: all.filter((g) => g.classList.contains('is-found')).map((g) => g.dataset.code),
      };
    """)
    assert result["found"] == ["ja"]
    assert result["dimmed"] == 72


@requires_chrome
def test_search_matches_city_as_well_as_language(page):
    # Someone typing "Tokyo" is asking the same question as someone typing
    # "Japanese", and the anchor city is shown in the UI.
    result = page.evaluate(OPEN_MAP + """
      const input = document.getElementById('map-search-input');
      input.value = 'tokyo';
      input.dispatchEvent(new Event('input'));
      await new Promise((r) => setTimeout(r, 200));
      return {
        found: [...document.querySelectorAll('#map-markers g.is-found')].map((g) => g.dataset.code),
      };
    """)
    assert result["found"] == ["ja"]


@requires_chrome
def test_zoom_narrows_the_viewbox_and_reset_restores_it(page):
    result = page.evaluate(OPEN_MAP + """
      const svg = document.getElementById('map-svg');
      const initial = svg.getAttribute('viewBox');
      document.getElementById('map-zoom-in').click();
      const zoomed = svg.getAttribute('viewBox');
      document.getElementById('map-zoom-reset').click();
      return { initial, zoomed, reset: svg.getAttribute('viewBox') };
    """)
    assert result["zoomed"] != result["initial"]
    assert float(result["zoomed"].split()[2]) < float(result["initial"].split()[2])
    assert result["reset"] == result["initial"]


@requires_chrome
def test_zoom_is_clamped_at_both_ends(page):
    # Unclamped zoom-out leaves the world a speck in empty space; unclamped
    # zoom-in eventually inverts the viewBox.
    result = page.evaluate(OPEN_MAP + """
      const svg = document.getElementById('map-svg');
      for (let i = 0; i < 40; i += 1) document.getElementById('map-zoom-out').click();
      const out = Number(svg.getAttribute('viewBox').split(' ')[2]);
      for (let i = 0; i < 40; i += 1) document.getElementById('map-zoom-in').click();
      const inn = Number(svg.getAttribute('viewBox').split(' ')[2]);
      return { out, inn };
    """)
    assert result["out"] == 720, "should not zoom out past the whole world"
    assert result["inn"] >= 720 / 8 - 0.01, "should not zoom in past the cap"
    assert result["inn"] > 0
