"""
pw_launch.py — one way to start a browser for every real-browser test and for tools/screens.py.

Why: a venv's Playwright expects ONE bundled Chromium build (e.g. chromium-1140 for 1.48). When the machine's cache
holds a different one (chromium-1223), `chromium.launch()` dies with "Executable doesn't exist" and 11 tests fail
for a reason that says nothing about the screen (seen 2026-10-05). Order tried:
  1. the bundled Chromium,  2. installed Google Chrome (channel="chrome"),
  3. $PW_CHROMIUM or the newest Chromium in ~/Library/Caches/ms-playwright.
If none starts, the test FAILS with the reasons — it is never skipped, so a green run always means a real browser ran.
With CS_REQUIRE_BROWSER=1 (the deploy gate sets it) a missing Playwright package is a failure too, not a skip.
"""
import glob
import os

import pytest

try:
    import playwright.sync_api as pw  # noqa: F401
except ImportError:  # pragma: no cover
    if os.environ.get("CS_REQUIRE_BROWSER") == "1":
        raise
    pw = pytest.importorskip("playwright.sync_api")


def _cached_chromiums():
    root = os.path.expanduser("~/Library/Caches/ms-playwright")
    pats = ["chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
            "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
            "chromium-*/chrome-linux*/chrome"]
    found = [p for pat in pats for p in glob.glob(os.path.join(root, pat))]
    return sorted(found, key=lambda p: int("".join(ch for ch in p.split("chromium-")[1].split("/")[0] if ch.isdigit()) or 0), reverse=True)


def launch(p, **kw):
    errors = []
    attempts = [("bundled chromium", {}), ("Google Chrome", {"channel": "chrome"})]
    for exe in ([os.environ["PW_CHROMIUM"]] if os.environ.get("PW_CHROMIUM") else []) + _cached_chromiums():
        attempts.append((exe, {"executable_path": exe}))
    for name, extra in attempts:
        try:
            return p.chromium.launch(**dict(kw, **extra))
        except Exception as e:  # noqa: BLE001 — every failure is reported below
            errors.append("%s: %s" % (name, str(e).strip().splitlines()[0][:160]))
    msg = "no usable Chromium for the browser tests:\n  " + "\n  ".join(errors)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        pytest.fail(msg, pytrace=False)
    raise RuntimeError(msg)
