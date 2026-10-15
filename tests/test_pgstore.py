"""The screen's state in Postgres (2026-10-16, no persistent disk): user store, activity log, snoozes, one-time disk import +
backup, and the two-instance race. Needs CS_TEST_PG=<url> (local throwaway Postgres: node /Users/Shared/cs_core_pgtest_start.mjs)."""
import io
import json
import os
import tarfile
import threading

import pytest

PG = os.environ.get("CS_TEST_PG", "postgresql://cs:cs@127.0.0.1:54329/cs_test")
pytest.importorskip("psycopg")
import pgstore  # noqa: E402
import dashboard as D  # noqa: E402
import snooze as S  # noqa: E402
from users_store import PgUserStore, UserStore, UserStoreError  # noqa: E402

VB = ["rozela", "velora"]


@pytest.fixture
def db():
    try:
        pgstore.reset_all(PG)
    except Exception as e:                            # no local test postgres: say so loudly, never silently pass
        pytest.fail("local test Postgres not reachable (%s): start node /Users/Shared/cs_core_pgtest_start.mjs" % e)
    d = pgstore.DB(PG, size=6)
    yield d


F = {"display_name": "x", "roles": ["agent"], "brands": ["rozela"], "lang": "he"}


def test_users_crud_audit_and_sv(db):
    st = PgUserStore(db)
    st.create("t", "dana", "HASH", F, VB, must_change=False)
    with pytest.raises(UserStoreError) as e:
        st.create("t", "dana", "HASH", F, VB)
    assert e.value.code == "user_exists"
    assert st.count() == 1 and st.get("DANA")["pw"] == "HASH" and st.get("nobody") is None
    r, ch = st.update("t", "dana", lambda rec, al: rec.update(must_change=True), "pw_change", bump_sv=True)
    assert ch and r["sv"] == 2 and st.get("dana")["must_change"] is True
    _, ch2 = st.update("t", "dana", lambda rec, al: None, "noop")
    assert not ch2
    with pytest.raises(UserStoreError):
        st.update("t", "ghost", lambda rec, al: None, "x")
    def boom(rec, al):
        raise UserStoreError("last_admin")
    with pytest.raises(UserStoreError):
        st.update("t", "dana", boom, "x")
    assert st.get("dana")["sv"] == 2                                   # a refused change rolls back
    st.touch_login("dana")
    assert st.get("dana")["last_login"]
    tail = st.audit_tail(10)
    assert [a["action"] for a in tail][:2] == ["pw_change", "user_created"] and "HASH" not in json.dumps(tail)
    assert [u["username"] for u in st.all()] == ["dana"]


def test_users_two_instances_do_not_lose_updates(db):
    a, b = PgUserStore(db), PgUserStore(pgstore.DB(PG, size=3))     # two "instances": separate pools, no shared lock
    a.create("t", "u1", "H", F, VB)
    def bump(st):
        for _ in range(15):
            st.update("t", "u1", lambda rec, al: rec.update(n=rec.get("n", 0) + 1), None)
    ts = [threading.Thread(target=bump, args=(s,)) for s in (a, b, a, b)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert a.get("u1")["n"] == 60


def test_activity_log_roundtrip(db):
    now = [1_760_000_000.0]
    lg = D.PgActivityLog(db, "/tmp/cs-test-act-root", clock=lambda: now[0])
    assert lg.first_day() is None
    assert lg.record("dana", "rozela", "t1", "wa", "open")
    assert not lg.record("dana", "rozela", "t1", "wa", "open")         # dedupe is unchanged
    lg.touch("dana")
    day = D.il_day(now[0])
    assert [e["u"] for e in lg.events(day)] == ["dana"] and lg.presence(day)["dana"]
    assert lg.first_day() == day
    lg.write_snap(day, {"a": 1})
    lg.write_snap(day, {"a": 2})
    assert lg.read_snap(day) == {"a": 2} and lg.read_snap("2000-01-01") is None


def test_snooze_store(db):
    now = [1000.0]
    s = S.PgSnoozeStore(db, clock=lambda: now[0])
    row = {"status": "ready", "n": 1}
    rec = s.put("dana", "rozela", "t1", 2000.0, row)
    assert [r["id"] for r in s.mine("dana")] == ["t1"] and rec["until"] == 2000.0
    assert s.drop("dana", "rozela", "t1") is True and s.mine("dana") == []
    s.put("dana", "rozela", "t2", 1500.0, row)
    now[0] = 1500.0 + S.KEEP_ENDED_S + 5                                 # long-ended records are pruned on the next write
    s.put("dana", "rozela", "t3", now[0] + 100, row)
    assert [r["id"] for r in s.records()] == ["t3"]


def test_translate_cache(db):
    c = pgstore.PgTranslateCache(db, ttl_s=1000)
    assert c.get("k") is None
    c.put("k", "שלום")
    assert c.get("k") == "שלום"
    c.put("k", "v2")
    assert c.get("k") == "v2"
    old = pgstore.PgTranslateCache(db, ttl_s=-1)
    assert old.get("k") is None


def _make_disk(tmp_path):
    d = tmp_path / "disk"
    (d / "activity").mkdir(parents=True)
    (d / "ticket-cache" / "rozela").mkdir(parents=True)
    (d / "ticket-cache" / "rozela" / "boot.json").write_text("{}")
    users = {"version": 1, "users": {"ana": {"username": "ana", "pw": "H1", "sv": 3, "roles": ["admin"], "brands": ["rozela"], "lang": "he"},
                                      "bob": {"username": "bob", "pw": "H2", "sv": 1, "roles": ["agent"], "brands": ["rozela"], "lang": "he"}}}
    (d / "users.json").write_text(json.dumps(users))
    (d / "users-audit.jsonl").write_text(json.dumps({"time": "t", "actor": "a", "action": "x", "target": "ana"}) + "\n\nnot json\n")
    (d / "activity" / "act-2026-10-14.jsonl").write_text(
        json.dumps({"ts": 1.0, "u": "ana", "b": "rozela", "t": "t1", "ch": "", "k": "open", "cat": ""}) + "\n"
        + json.dumps({"ts": 2.0, "u": "ana", "b": "rozela", "t": "t2", "ch": "", "k": "open", "cat": ""}) + "\n")
    (d / "activity" / "act-2026-10-15.jsonl").write_text(json.dumps({"ts": 3.0, "u": "bob", "b": "rozela", "t": "t3", "ch": "", "k": "open", "cat": ""}) + "\n")
    (d / "activity" / "pres-2026-10-14.jsonl").write_text(json.dumps({"u": "ana", "m": 5}) + "\n")
    (d / "activity" / "snap-2026-10-14.json").write_text(json.dumps({"day": "2026-10-14"}))
    (d / "activity" / "ds-rozela-2026-10-14.json").write_text(json.dumps({"at": 1}))
    (d / "snooze.json").write_text(json.dumps({"rozela|t1|ana": {"u": "ana", "b": "rozela", "id": "t1", "until": 9e12, "at": 1}}))
    return str(d)


def test_import_and_backup_are_idempotent(db, tmp_path):
    disk = _make_disk(tmp_path)
    out = pgstore.backup_and_import(db, disk)
    assert out["imported"] == {"users": 2, "audit": 1, "activity_events": 3, "presence_rows": 1, "activity_days": 2, "snapshots": 1, "snoozes": 1}
    st = PgUserStore(db)
    assert st.get("ana")["sv"] == 3 and st.count() == 2
    lg = D.PgActivityLog(db, str(tmp_path / "cache"))
    assert lg.first_day() == "2026-10-14" and len(lg.events("2026-10-14")) == 2 and lg.presence("2026-10-14") == {"ana": {5}}
    assert lg.read_snap("2026-10-14") == {"day": "2026-10-14"}
    assert len(S.PgSnoozeStore(db, clock=lambda: 1.0).records()) == 1
    # the backup row: a real tar.gz of the disk, pure caches left out, hash matches
    name, sha, size, files, blob = db.q("select name, sha256, size, files, data from screen_backup")[0]
    import hashlib
    assert hashlib.sha256(bytes(blob)).hexdigest() == sha and len(blob) == size
    names = sorted(tarfile.open(fileobj=io.BytesIO(bytes(blob)), mode="r:gz").getnames())
    assert "users.json" in names and "activity/act-2026-10-14.jsonl" in names and not any(n.startswith("ticket-cache") for n in names)
    assert sorted(f["name"] for f in files) == names
    # a second boot (or the second instance during a deploy) changes nothing
    st.update("t", "ana", lambda r, a: r.update(sv=9), None)
    pgstore.backup_and_import(db, disk)
    assert st.get("ana")["sv"] == 9 and st.count() == 2 and db.q("select count(*) from screen_backup")[0][0] == 1
    assert db.q("select count(*) from screen_activity")[0][0] == 4


def test_import_refuses_a_broken_users_file(db, tmp_path):
    d = tmp_path / "disk2"
    d.mkdir()
    (d / "users.json").write_text('{"nope": 1}')
    with pytest.raises(RuntimeError):
        pgstore.backup_and_import(db, str(d))
    assert PgUserStore(db).count() == 0                                  # nothing half-imported


def test_no_disk_is_a_clean_skip(db, tmp_path):
    assert pgstore.backup_and_import(db, str(tmp_path / "gone")) == {"skipped": "no disk"}
    assert pgstore.backup_and_import(db, "") == {"skipped": "no disk"}


def test_app_boots_on_postgres_and_logs_in_an_imported_user(tmp_path, pw_hash, transport):
    """The real boot path: empty tables + the old disk -> backup + import -> an imported user signs in; a restart changes nothing."""
    import conftest
    from app import create_app
    pgstore.reset_all(PG)
    disk = tmp_path / "disk"
    disk.mkdir()
    rec = {"username": "ana", "pw": pw_hash, "sv": 1, "roles": ["agent"], "brands": ["rozela"], "lang": "he", "disabled": False, "must_change": False}
    (disk / "users.json").write_text(json.dumps({"version": 1, "users": {"ana": rec}}))
    cfg = {"SECRET_KEY": "s" * 48, "TOKEN_SECRET": conftest.TOKEN_SECRET, "ENGINES_JSON": json.dumps(conftest.ENGINES), "TRANSPORT": transport,
           "TRUSTED_PROXY_HOPS": 0, "ADMIN_BOOTSTRAP": "", "DB_URL": PG, "USERS_PATH": str(disk / "users.json"), "CACHE_BASE": str(tmp_path / "cache")}
    for _ in range(2):                                                    # second pass = a restart / the second instance
        app = create_app(cfg)
        app.testing = True
        c = conftest.client_for(app)
        assert conftest.login(c, "ana").status_code == 302
        assert c.get("/api/me").status_code == 200
        cache = app.extensions["cs"]["ticket_cache"]
        cache.drain()
        for pool in (cache.top_pool, cache.fg_pool, cache.pool):
            pool.shutdown(wait=True)
    db = pgstore.DB(PG, size=1)
    assert db.q("select count(*) from screen_backup")[0][0] == 1 and PgUserStore(db).count() == 1
