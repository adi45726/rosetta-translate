"""The check that would have caught the worst bug this project shipped.

A stray backslash in one regex made auth.js fail to parse. Because that is an
early error, the whole module never evaluated, so not one listener in the file
was attached and every button on the sign-in gate did nothing -- silently, with
the reason visible only in a console nobody had open. The Python suite passed
throughout, and `node --check` passed too.

These tests load the real page in a real browser and ask whether the scripts
actually ran and the handlers actually exist.
"""

from __future__ import annotations

import pytest
from browser import Page, requires_chrome


@pytest.fixture(scope="module")
def page():
    with Page() as running:
        yield running


@requires_chrome
def test_page_loads_without_script_errors(page):
    errors = page.evaluate("""
      const seen = [];
      window.addEventListener('error', (e) => seen.push(String(e.message)));
      await new Promise((r) => setTimeout(r, 600));
      return { errors: seen };
    """)
    assert errors["errors"] == []


@requires_chrome
def test_every_script_module_actually_evaluated(page):
    # Each file declares something at top level. If a file failed to parse --
    # the auth.js regex bug -- its symbol is missing while every other file
    # still works, which is exactly how that failure looked.
    result = page.evaluate("""
      return {
        app: typeof runTranslate,
        companion: typeof openCompanion,
        practice: typeof openPractice,
        map: typeof openMap,
      };
    """)
    assert result == {
        "app": "function",
        "companion": "function",
        "practice": "function",
        "map": "function",
    }


@requires_chrome
def test_auth_buttons_have_listeners_attached(page):
    # The specific regression: buttons present in the DOM but inert, because
    # the module that binds them never ran.
    result = page.evaluate("""
      const ids = ['auth-google', 'auth-guest', 'auth-submit'];
      const present = ids.filter((id) => document.getElementById(id));
      // getEventListeners is a devtools API, so prove liveness differently:
      // auth.js replaces window.fetch on evaluation. If that wrapper is in
      // place, the module ran and its listeners were bound with it.
      return {
        present,
        moduleRan: window.fetch.toString().includes('/api/'),
      };
    """)
    assert result["present"] == ["auth-google", "auth-guest", "auth-submit"]
    assert result["moduleRan"] is True


@requires_chrome
def test_no_panel_renders_behind_the_modal_backdrop(page):
    # A panel once opened underneath its own backdrop and came out blurred,
    # because it had not joined the shared modal z-index rule.
    result = page.evaluate("""
      const backdrop = getComputedStyle(document.getElementById('modal-backdrop')).zIndex;
      const panels = ['tools-panel','caption-panel','writing-panel','companion-panel',
                      'practice-panel','map-panel','camera-panel'];
      const below = panels.filter((id) => {
        const node = document.getElementById(id);
        if (!node) return false;
        return Number(getComputedStyle(node).zIndex) <= Number(backdrop);
      });
      return { backdrop: Number(backdrop), below };
    """)
    assert result["below"] == [], f"panels not above the backdrop: {result['below']}"


@requires_chrome
def test_every_panel_is_centred_not_knocked_aside_by_an_animation(page):
    # An animation declared on a panel overrode the translate(-50%,-50%) that
    # centres it, pinning it off-screen for as long as its fill applied.
    result = page.evaluate("""
      const panels = ['companion-panel','practice-panel','map-panel','camera-panel'];
      const offset = [];
      for (const id of panels) {
        const node = document.getElementById(id);
        if (!node) continue;
        node.classList.remove('hidden');
        const t = getComputedStyle(node).transform;
        node.classList.add('hidden');
        // A centred fixed panel must carry a negative translation on both axes.
        if (t === 'none') { offset.push(id + ':none'); continue; }
        const parts = t.match(/matrix\\(([^)]+)\\)/);
        if (!parts) { offset.push(id + ':' + t); continue; }
        const nums = parts[1].split(',').map(Number);
        if (nums[4] >= 0 || nums[5] >= 0) offset.push(id + ':' + nums[4] + ',' + nums[5]);
      }
      return { offset };
    """)
    assert result["offset"] == [], f"panels not centred: {result['offset']}"
