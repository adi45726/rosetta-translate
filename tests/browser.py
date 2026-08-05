"""Drive the real page in a real browser, and assert on what it does.

Every JavaScript bug this project has shipped -- a regex that failed to parse
and killed a whole module, a panel rendering behind its own backdrop, a closure
that went stale after one click, a keyboard shortcut dead on macOS -- was found
by opening a browser and looking. None could have been caught by the Python
suite, because none of them are Python.

This is deliberately not Playwright or Selenium. Those bring a large dependency
and a driver to keep in step with the browser; this project has no build step
and installs nothing to run its own tests. Headless Chrome already ships on
every machine that has Chrome, and it can load a page, run assertions inside
it, and hand back the result through the document title. That is enough to
catch the class of bug that has actually been escaping.

Tests skip rather than fail when Chrome is absent, so the Python suite stays
runnable anywhere.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


def find_chrome() -> str | None:
    for candidate in _CHROME_CANDIDATES:
        if candidate.startswith("/") and Path(candidate).exists():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


CHROME = find_chrome()
requires_chrome = pytest.mark.skipif(CHROME is None, reason="headless Chrome not available")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Page:
    """A running app plus a browser that can be asked questions about it."""

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self._proc: subprocess.Popen | None = None
        self._env = env or {}

    def __enter__(self) -> Page:
        environment = {
            **os.environ,
            "PORT": str(self.port),
            # Keep the browser tests independent of whatever the developer's
            # .env happens to hold, exactly as conftest does for Python tests.
            "GROQ_API_KEY": "",
            "FIREBASE_API_KEY": "",
            "FIREBASE_PROJECT_ID": "",
            "ROSETTA_ALLOW_TEST_SCRIPT": "1",
            **self._env,
        }
        self._proc = subprocess.Popen(
            [sys.executable, str(ROOT / "web" / "app.py")],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._wait_for_server()
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def _wait_for_server(self, timeout: float = 25.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("the app did not start in time")

    def evaluate(self, script: str, *, path: str = "/", budget_ms: int = 9000) -> dict:
        """Run `script` in the page and return whatever it assigns to `result`.

        The script runs after load. It may be async: return a promise from an
        IIFE and it will be awaited. Anything it puts in `result` comes back
        here as parsed JSON, which is how assertions leave the browser.
        """
        assert CHROME is not None
        harness = (
            "<script>window.addEventListener('load', async () => {"
            "  try {"
            f"    const result = await (async () => {{ {script} }})();"
            "    document.title = 'ROSETTA_RESULT::' + JSON.stringify(result ?? null);"
            "  } catch (error) {"
            "    document.title = 'ROSETTA_ERROR::' + String(error && error.message || error);"
            "  }"
            "});</script>"
        )
        # Served by a route the app only exposes under this flag, so the
        # harness never has to edit files the tests are meant to be checking.
        url = f"{self.base}{path}"
        url += ("&" if "?" in url else "?") + "__test_script=" + _encode(harness)

        completed = subprocess.run(
            [
                CHROME, "--headless", "--disable-gpu", "--no-sandbox",
                "--hide-scrollbars", f"--virtual-time-budget={budget_ms}",
                "--dump-dom", url,
            ],
            capture_output=True,
            text=True,
            timeout=90,
        )
        dom = completed.stdout
        # Read the <title> specifically. Searching the whole DOM for the marker
        # finds it inside the injected script's own source first, since that
        # script is rendered into the page it is testing.
        match = re.search(r"<title[^>]*>(.*?)</title>", dom, re.S)
        if match is None:
            raise AssertionError("the page produced no title; it probably failed to load")
        title = _unescape(match.group(1)).strip()
        if title.startswith("ROSETTA_ERROR::"):
            raise AssertionError(f"page threw: {title[len('ROSETTA_ERROR::'):]}")
        if title.startswith("ROSETTA_RESULT::"):
            return json.loads(title[len("ROSETTA_RESULT::"):])
        raise AssertionError(
            "the script did not run; the page may have failed to load or thrown before it"
        )


def _encode(text: str) -> str:
    from urllib.parse import quote

    return quote(text, safe="")


def _unescape(text: str) -> str:
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
