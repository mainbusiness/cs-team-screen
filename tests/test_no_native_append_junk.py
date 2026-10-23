"""A DOM `Element.append()` prints whatever it is given: `null` becomes the word "null", an array becomes "[object HTMLDivElement]".
The screen's own `h()` / `add()` skip null and flatten arrays; the native method does not. Caught only in a real browser twice
(2026-10-22 the AI-notes redraft line: append(array); 2026-10-23 the cancellations card: append(..., cond ? x : null)). This test reads
static/app.js and fails on any `.append(` whose top-level argument is `null`, a ternary that can end in `null`, or an array literal.
Use add(el, [...]) for optional or listed children."""
import os
import re

APP = os.path.join(os.path.dirname(__file__), "..", "static", "app.js")
# Known sites, each with why it is still here. A new entry needs a reason; the list only shrinks.
KNOWN = {
    # The sub-cancel dialog with several contracts and no email prints "null" under the options. Not part of the 2026-10-23 request:
    # proposed to the owner as a one-line fix (add(box, [...])), not changed without his go-ahead.
    "box.append(opts, pv.email ? h(": "proposed 2026-10-23",
    # The managers' KPI grid: with no person's first-reply time from any brand (frt_human_known false) the first tile is the word "null".
    # Found by this test on 2026-10-23; outside that request, proposed to Owner, not changed.
    "k.frt_human_known ? kpi(L.frt_human_all": "proposed 2026-10-23",
}


def _args(src, i):
    """Top-level arguments of the call whose '(' is at src[i]; strings, template literals and comments are skipped."""
    depth, out, cur, j, n = 0, [], [], i + 1, len(src)
    while j < n:
        c = src[j]
        if c in "'\"`":
            k = j + 1
            while k < n and src[k] != c:
                k += 2 if src[k] == "\\" else 1
            cur.append(src[j:k + 1]); j = k + 1
            continue
        if src.startswith("//", j):
            j = src.index("\n", j)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                out.append("".join(cur).strip())
                return out
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip()); cur = []
        else:
            cur.append(c)
        j += 1
    return out


def _top_ternary_null(a):
    """`x ? y : null` at the top level of one argument (a `?` inside nested brackets belongs to a nested call)."""
    depth, q = 0, False
    for k, c in enumerate(a):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "?" and depth == 0 and a[k + 1:k + 2] not in ("?", ".") and a[k - 1:k] != "?":
            q = True
    return q and re.search(r":\s*null\s*$", a) is not None


def offenders(src):
    bad = []
    for m in re.finditer(r"\.append\(", src):
        line_start = src.rfind("\n", 0, m.start()) + 1
        line = src[line_start:src.find("\n", m.start())].strip()
        for a in _args(src, m.end() - 1):
            if a == "null" or a.startswith("[") or _top_ternary_null(a):
                if not any(k in line or k in a for k in KNOWN):
                    bad.append("%d: %s" % (src.count("\n", 0, m.start()) + 1, line[:140]))
                break
    return bad


def test_no_native_append_of_null_or_an_array():
    bad = offenders(open(APP, encoding="utf-8").read())
    assert not bad, "native append() of null / a ternary-null / an array (use add(el, [...])):\n" + "\n".join(bad)


def test_the_check_itself_finds_what_it_is_for():
    assert offenders("card.append(h('b'), ok ? h('i') : null);\n")
    assert offenders("el.append([a, b]);\n")
    assert offenders("el.append(null);\n")
    assert not offenders("el.append(h('div', null, ok ? h('i') : null));\n")       # inside h(): h skips null
    assert not offenders("el.append(a ?? b, c?.d);\n")
    assert not offenders("add(card, [h('b'), ok ? h('i') : null]);\n")
