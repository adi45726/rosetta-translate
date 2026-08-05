"""Browser tests for Iris and the Practice Partner.

Both are stateful in a way the Python suite cannot see: bubbles that rewrite
each other, a face driven by SVG path swaps, a score that accumulates. The one
bug this file exists for is the alternate-chip swap, which corrupted itself on
a second click because a handler trusted a value captured when it was created
rather than what the element currently held.
"""

from __future__ import annotations

import pytest
from browser import Page, requires_chrome


@pytest.fixture(scope="module")
def page():
    with Page() as running:
        yield running


UNGATE = "document.getElementById('auth-gate').classList.add('hidden');"


@requires_chrome
def test_alternate_chip_swaps_cleanly_on_repeated_clicks(page):
    # The regression: the handler closed over the value the chip had when it
    # was built, but the swap rewrites that label. A second click re-showed the
    # phrasing already on screen and destroyed the demoted original.
    result = page.evaluate(UNGATE + """
      state.lastTranslation = 'PRIMARY';
      renderAlternates(['ALT1', 'ALT2']);
      const chip = alternatesRow.children[0];
      chip.click();
      const afterOne = { out: targetText.textContent, chip: chip.textContent };
      chip.click();
      const afterTwo = { out: targetText.textContent, chip: chip.textContent };
      const labels = [...alternatesRow.children].map((c) => c.textContent);
      return { afterOne, afterTwo, labels, duplicated: labels.includes(targetText.textContent) };
    """)
    assert result["afterOne"] == {"out": "ALT1", "chip": "PRIMARY"}
    # A second click must return the original, not repeat the first swap.
    assert result["afterTwo"] == {"out": "PRIMARY", "chip": "ALT1"}
    assert result["duplicated"] is False


@requires_chrome
def test_iris_face_changes_shape_with_her_feeling(page):
    # Each feeling maps to a distinct mouth path. If the lookup silently fell
    # back, every feeling would render the same face and nothing would error.
    result = page.evaluate(UNGATE + """
      const shapes = {};
      for (const feeling of ['warm', 'cheerful', 'concerned', 'thoughtful']) {
        setIrisFeeling(feeling);
        shapes[feeling] = document.getElementById('iris-mouth').getAttribute('d');
      }
      return { shapes, distinct: new Set(Object.values(shapes)).size };
    """)
    assert result["distinct"] == 4, "each feeling should draw a different mouth"


@requires_chrome
def test_unknown_feeling_falls_back_rather_than_breaking_the_face(page):
    result = page.evaluate(UNGATE + """
      setIrisFeeling('warm');
      const warm = document.getElementById('iris-mouth').getAttribute('d');
      setIrisFeeling('not-a-feeling');
      return { warm, after: document.getElementById('iris-mouth').getAttribute('d') };
    """)
    assert result["after"] == result["warm"]


@requires_chrome
def test_closing_iris_releases_the_camera_and_stops_speech(page):
    # Closing mid-speech once left her talking to an empty room, and the camera
    # light stayed on.
    result = page.evaluate(UNGATE + """
      openCompanion();
      companionSee.checked = true;
      closeCompanion();
      return {
        hidden: companionPanel.classList.contains('hidden'),
        cameraOff: companionSee.checked === false,
        speaking: document.querySelector('.iris-stage').classList.contains('is-speaking'),
      };
    """)
    assert result == {"hidden": True, "cameraOff": True, "speaking": False}


@requires_chrome
def test_practice_score_ring_tracks_the_running_average(page):
    result = page.evaluate(UNGATE + """
      openPractice();
      resetScore();
      const empty = document.getElementById('score-value').textContent;
      pushScore(60);
      pushScore(100);
      return { empty, average: document.getElementById('score-value').textContent };
    """)
    assert result["empty"] == "—"
    assert result["average"] == "80"


@requires_chrome
def test_practice_correction_renders_beside_the_conversation(page):
    # Corrections must not be inlined into the character's reply: that breaks
    # the roleplay every turn, which is the whole point of roleplay.
    result = page.evaluate(UNGATE + """
      openPractice();
      practiceThread.innerHTML = '';
      addPracticeBubble('Claro, un cafe grande.', 'partner', 'Sure, a large coffee.');
      addCorrection({ original: 'yo querer', fixed: 'yo quiero', why: 'Use the conjugated form.' });
      const card = practiceThread.querySelector('.correction-card');
      const bubble = practiceThread.querySelector('.bubble');
      return {
        hasCard: Boolean(card),
        cardText: card ? card.textContent : '',
        bubbleUntouched: bubble ? bubble.textContent : '',
      };
    """)
    assert result["hasCard"] is True
    assert "yo quiero" in result["cardText"]
    # The reply itself must be unchanged by the correction beside it.
    assert result["bubbleUntouched"] == "Claro, un cafe grande."
