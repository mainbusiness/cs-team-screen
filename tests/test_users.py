"""User manager: who may do what, lockout guards, audit, and the CLI."""
import json

import manage
from conftest import PASSWORD, add_user, client_for, login, logged_in, spa_csrf, store_of


def post(c, tok, path, body):
    return c.post(path, json=body, headers={"X-CSRF-Token": tok})


def test_agent_cannot_open_the_user_manager(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "noa", ["agent"], ["rozela"])
    assert c.get("/api/manage/users").status_code == 403
    assert post(c, tok, "/api/manage/users", {"username": "x1", "roles": ["agent"], "brands": [], "lang": "he"}).status_code == 403
    assert post(c, tok, "/api/manage/users/noa", {"roles": ["admin"]}).status_code == 403
    assert c.get("/api/manage/audit").status_code == 403


def test_user_manager_creates_an_agent_with_a_temp_password(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "mgr", ["user-manager"], [])
    r = post(c, tok, "/api/manage/users", {"username": "agent-two", "display_name": "נציגה ב", "roles": ["agent"], "brands": ["celesta", "apexmen"], "lang": "he"})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"], j
    assert j["user"]["must_change"] and "pw" not in j["user"] and "sv" not in j["user"]
    c2 = client_for(app, "10.7.7.7")
    assert login(c2, "agent-two", j["temp_password"]).headers["Location"].endswith("/cs/password")


def test_user_manager_cannot_create_or_touch_admins(app, pw_hash):
    add_user(app, pw_hash, "guy", ["admin"], ["rozela"])
    c, tok = logged_in(app, pw_hash, "mgr", ["user-manager"], [])
    assert post(c, tok, "/api/manage/users", {"username": "evil", "roles": ["admin"], "brands": [], "lang": "he"}).status_code == 403
    assert store_of(app).get("evil") is None
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    r = post(c, tok, "/api/manage/users/noa", {"roles": ["agent", "admin"]})
    assert r.status_code == 403 and r.get_json()["error"] == "only_admin_grants_admin"
    assert post(c, tok, "/api/manage/users/guy", {"disabled": True}).status_code == 403
    assert post(c, tok, "/api/manage/users/guy/reset", {}).status_code == 403
    assert post(c, tok, "/api/manage/users/guy", {"brands": []}).status_code == 403
    assert store_of(app).get("guy")["disabled"] is False


def test_admin_can_grant_admin_and_change_everything(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ["rozela"])
    r = post(c, tok, "/api/manage/users/noa", {"roles": ["agent", "admin"], "brands": ["rozela", "velora"], "lang": "en"})
    assert r.status_code == 200, r.get_json()
    u = store_of(app).get("noa")
    assert u["roles"] == ["agent", "admin"] and u["brands"] == ["rozela", "velora"] and u["lang"] == "en"


def test_nobody_locks_themselves_out(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "manager", ["admin", "user-manager"], ["rozela"])
    assert post(c, tok, "/api/manage/users/manager", {"disabled": True}).get_json()["error"] == "self_lockout"
    assert post(c, tok, "/api/manage/users/manager", {"roles": ["agent"]}).get_json()["error"] == "self_lockout"
    assert post(c, tok, "/api/manage/users/manager", {"display_name": "המנהל"}).status_code == 200


def test_security_change_logs_the_target_out(app, pw_hash):
    c_noa, _ = logged_in(app, pw_hash, "noa", ["agent"], ["rozela", "celesta"])
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    assert c_noa.get("/api/me").status_code == 200
    assert post(c, tok, "/api/manage/users/noa", {"brands": ["celesta"]}).status_code == 200
    assert c_noa.get("/api/me").status_code == 401
    c_noa2 = client_for(app, "10.8.8.8")
    login(c_noa2, "noa")
    assert [b["id"] for b in c_noa2.get("/api/me").get_json()["brands"]] == ["celesta"]


def test_reset_password_shows_once_and_forces_change(app, pw_hash):
    add_user(app, pw_hash, "noa", ["agent"], ["rozela"])
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    j = post(c, tok, "/api/manage/users/noa/reset", {}).get_json()
    assert j["ok"] and len(j["temp_password"]) >= 16
    assert login(client_for(app, "10.5.5.5"), "noa", PASSWORD).status_code == 401
    assert login(client_for(app, "10.6.6.6"), "noa", j["temp_password"]).headers["Location"].endswith("/cs/password")
    assert "temp_password" not in json.dumps(c.get("/api/manage/users").get_json())


def test_validation_errors_are_hebrew(app, pw_hash):
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    j = post(c, tok, "/api/manage/users", {"username": "Bad Name!", "roles": ["agent"], "brands": [], "lang": "he"}).get_json()
    assert j["error"] == "bad_username" and "שם משתמש" in j["msg"]
    j = post(c, tok, "/api/manage/users", {"username": "ok1", "roles": ["agent"], "brands": ["nosuchbrand"], "lang": "he"}).get_json()
    assert j["error"] == "unknown_brand"
    j = post(c, tok, "/api/manage/users", {"username": "ok2", "roles": [], "brands": [], "lang": "he"}).get_json()
    assert j["error"] == "bad_roles"
    j = post(c, tok, "/api/manage/users", {"username": "manager", "roles": ["agent"], "brands": [], "lang": "he"}).get_json()
    assert j["error"] == "user_exists"


def test_every_change_is_audited_without_secrets(app, pw_hash, tmp_path):
    c, tok = logged_in(app, pw_hash, "manager", ["admin"], ["rozela"])
    j = post(c, tok, "/api/manage/users", {"username": "ron", "roles": ["agent"], "brands": ["rozela"], "lang": "he"}).get_json()
    post(c, tok, "/api/manage/users/ron", {"lang": "en"})
    post(c, tok, "/api/manage/users/ron/reset", {})
    post(c, tok, "/api/manage/users/ron", {"disabled": True})
    lines = [json.loads(x) for x in (tmp_path / "audit.jsonl").read_text().splitlines()]
    acts = [(x["actor"], x["action"], x["target"]) for x in lines if x["target"] == "ron"]
    assert ("manager", "user_created", "ron") in acts and ("manager", "password_reset", "ron") in acts
    assert sum(1 for a in acts if a[1] == "user_updated") == 2
    raw = (tmp_path / "audit.jsonl").read_text()
    assert j["temp_password"] not in raw and "pbkdf2" not in raw
    audit = c.get("/api/manage/audit").get_json()["lines"]
    assert audit[0]["target"] == "ron"


def test_cli_add_user_seed_and_last_admin_guard(tmp_path, capsys):
    users = str(tmp_path / "u.json")
    assert manage.main(["--users", users, "seed-team"]) == 0
    out = capsys.readouterr().out
    assert out.count("temp password:") == 4
    s = manage.store_from(type("A", (), {"users": users})())
    assert s.get("manager")["roles"] == ["admin", "user-manager"]
    assert s.get("agent-one")["brands"] == ["rozela", "velora"]
    assert s.get("agent-two")["brands"] == ["apexmen", "celesta"]
    assert set(s.get("guy")["brands"]) == {"rozela", "celesta", "velora", "apexmen"}
    assert all(u["must_change"] for u in s.all())
    assert manage.main(["--users", users, "seed-team"]) == 0           # idempotent
    assert "exists" in capsys.readouterr().out
    assert manage.main(["--users", users, "disable", "guy"]) == 0
    assert manage.main(["--users", users, "disable", "manager"]) == 1   # the last enabled admin
    assert manage.main(["--users", users, "add-user", "zed", "--roles", "agent", "--brands", "rozela"]) == 0
    assert "one-time temporary password" in capsys.readouterr().out
