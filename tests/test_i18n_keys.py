"""2026-10-12: a new string reused an existing key (ship_late) and silently replaced 'מאחר' in the fact panel: in a JS object literal the
LAST duplicate key wins with no error. Every key of each language dictionary must be unique."""
import os
import re

APP = os.path.join(os.path.dirname(__file__), "..", "static", "app.js")


def _dicts():
    src = open(APP, encoding="utf-8").read()
    start = src.index("  const STR = {")
    he = src.index("\n    he: {", start)
    en = src.index("\n    en: {", he)
    end = src.index("\n  };", en)
    return {"he": src[he:en], "en": src[en:end]}


def test_no_duplicate_keys_in_either_language():
    for lang, block in _dicts().items():
        keys = re.findall(r"(?:^|[\s,{])([A-Za-z_][A-Za-z0-9_]*):\s*['\"`(]", block)
        dup = sorted({k for k in keys if keys.count(k) > 1})
        assert not dup, "%s dictionary repeats keys: %s" % (lang, dup)
