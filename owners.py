"""Owner accounts (2026-11-25).

An owner account leaves no trace of WHEN or HOW LONG it is on the screen for anyone else:
  * no presence minutes and no activity events are written for it (the managers' board has no row for it, it is never "online now",
    and the per-agent tables of the quality check, the SLA board, the cancellations board and the weekly summary skip it);
  * it is never shown on a ticket's "someone else is here / typing" chip;
  * its last sign-in and last-change time are not returned by the user manager, and the user-manager change log drops its lines,
    for anyone but the owner himself.
Brand totals that the ENGINE counts (sends, closes, cancels) still include its work: only the per-person row is gone.

An owner account can be changed (edit, roles, brands, disable, password reset) only by the owner himself or by an ops account.
The command line (manage.py, on the server) is not limited by this.

Config (env): HIDDEN_OWNERS (comma list, default "guy"), OWNER_OPS (comma list, default "claude-admin").
"""
import os
import re

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,39}$")


def _parse(raw):
    out = set()
    for x in str(raw or "").split(","):
        x = x.strip().lower()
        if _NAME_RE.match(x):
            out.add(x)
    return frozenset(out)


HIDDEN = _parse(os.environ.get("HIDDEN_OWNERS", "guy"))
OPS = _parse(os.environ.get("OWNER_OPS", "claude-admin"))


def configure(hidden=None, ops=None):
    """Tests / create_app overrides (a comma string or an iterable)."""
    global HIDDEN, OPS
    if hidden is not None:
        HIDDEN = _parse(hidden if isinstance(hidden, str) else ",".join(str(x) for x in hidden))
    if ops is not None:
        OPS = _parse(ops if isinstance(ops, str) else ",".join(str(x) for x in ops))


def _n(name):
    return name.strip().lower() if isinstance(name, str) else ""


def is_hidden(name):
    """An owner account: never written to the presence / activity log, never a per-person row on any board."""
    return _n(name) in HIDDEN


def hidden_from(viewer, name):
    """True when `name` is an owner account and `viewer` is not that same account (None = an unknown viewer: hidden)."""
    return is_hidden(name) and _n(viewer) != _n(name)


def may_change(actor, target):
    """Only the owner himself or an ops account may change an owner account."""
    if not is_hidden(target):
        return True
    a = _n(actor)
    return a == _n(target) or a in OPS


def mentions(obj, depth=0):
    """True when any string value in obj (dict / list, nested) IS an owner username (exact, case-insensitive; 'agent-one' is not 'guy')."""
    if depth > 6:
        return False
    if isinstance(obj, str):
        return is_hidden(obj)
    if isinstance(obj, dict):
        return any(mentions(k, depth + 1) or mentions(v, depth + 1) for k, v in obj.items())
    if isinstance(obj, (list, tuple)):
        return any(mentions(v, depth + 1) for v in obj)
    return False


def drop(mapping):
    """A copy of a {username: ...} dict without the owner accounts."""
    return {k: v for k, v in (mapping or {}).items() if not is_hidden(k)}
