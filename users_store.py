"""
users_store.py — the user list on the Render persistent disk, and its audit log.

Safety model:
 - One JSON file (USERS_PATH). Every write is read-modify-write under an exclusive flock on a sibling
   lock file, then temp file in the same directory + fsync + os.replace: a crash leaves either the old
   file or the new one, never a torn one, and two writers cannot lose each other's change.
 - File mode 0600. Password hashes never leave this module except inside the stored record.
 - Every change is appended to AUDIT_PATH (JSON lines, append-only, never truncated). Audit lines carry
   who, what, which user and which FIELDS changed — never a password or a hash.
 - `sv` (session version) is bumped on every security-relevant change (password, roles, brands,
   disable). A session cookie carries the sv it was issued with; a mismatch ends the session.
"""

import contextlib
import copy
import fcntl
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,31}$")
BRAND_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,29}$")
ROLES = ("agent", "admin", "user-manager")
LANGS = ("he", "en")


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class UserStoreError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class UserStore:
    def __init__(self, path, audit_path):
        self.path = path
        self.audit_path = audit_path
        self.lock_path = path + ".lock"
        self._tlock = threading.Lock()
        self._cache = None
        self._cache_sig = None
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    # ---------- low level ----------

    @contextlib.contextmanager
    def _locked(self):
        with self._tlock:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)

    def _read_raw(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return {"version": 1, "users": {}}
        if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
            raise UserStoreError("users_file_corrupt")
        return data

    def _write_raw(self, data):
        d = os.path.dirname(os.path.abspath(self.path))
        fd, tmp = tempfile.mkstemp(prefix=".users.", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
            try:
                dfd = os.open(d, os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise
        self._cache = None

    def _snapshot(self):
        """Read, cached by (mtime_ns, size, inode) — every request reads the user fresh but cheaply."""
        try:
            st = os.stat(self.path)
            sig = (st.st_mtime_ns, st.st_size, st.st_ino)
        except FileNotFoundError:
            sig = None
        if sig is not None and sig == self._cache_sig and self._cache is not None:
            return self._cache
        data = self._read_raw()
        self._cache, self._cache_sig = data, sig
        return data

    def audit(self, actor, action, target="", detail=None):
        line = {"time": now_iso(), "actor": actor, "action": action, "target": target}
        if detail:
            line["detail"] = detail
        os.makedirs(os.path.dirname(os.path.abspath(self.audit_path)) or ".", exist_ok=True)
        fd = os.open(self.audit_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        try:
            os.write(fd, (json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
        finally:
            os.close(fd)

    def audit_tail(self, n=100):
        try:
            with open(self.audit_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 256 * 1024))
                lines = f.read().decode("utf-8", "replace").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for ln in lines[-n:]:
            with contextlib.suppress(ValueError):
                out.append(json.loads(ln))
        return list(reversed(out))

    # ---------- reads ----------

    def count(self):
        return len(self._snapshot()["users"])

    def get(self, username):
        if not isinstance(username, str):
            return None
        u = self._snapshot()["users"].get(username.lower())
        return copy.deepcopy(u) if u else None

    def all(self):
        return [copy.deepcopy(u) for _, u in sorted(self._snapshot()["users"].items())]

    # ---------- validation ----------

    @staticmethod
    def clean_fields(fields, valid_brands, partial):
        out = {}
        if "display_name" in fields or not partial:
            dn = fields.get("display_name", "")
            if not isinstance(dn, str) or len(dn) > 60:
                raise UserStoreError("bad_display_name")
            out["display_name"] = dn.strip()
        if "roles" in fields or not partial:
            roles = fields.get("roles")
            if not isinstance(roles, list) or not roles or any(r not in ROLES for r in roles):
                raise UserStoreError("bad_roles")
            out["roles"] = [r for r in ROLES if r in roles]
        if "brands" in fields or not partial:
            brands = fields.get("brands")
            if not isinstance(brands, list) or any(not isinstance(b, str) or not BRAND_RE.match(b) for b in brands):
                raise UserStoreError("bad_brands")
            unknown = [b for b in brands if b not in valid_brands]
            if unknown:
                raise UserStoreError("unknown_brand")
            out["brands"] = sorted(set(brands))
        if "lang" in fields or not partial:
            lang = fields.get("lang", "he")
            if lang not in LANGS:
                raise UserStoreError("bad_lang")
            out["lang"] = lang
        if "disabled" in fields:
            if not isinstance(fields["disabled"], bool):
                raise UserStoreError("bad_disabled")
            out["disabled"] = fields["disabled"]
        return out

    # ---------- writes ----------

    def create(self, actor, username, password_hash, fields, valid_brands, must_change=True):
        if not isinstance(username, str) or not USERNAME_RE.match(username):
            raise UserStoreError("bad_username")
        clean = self.clean_fields(fields, valid_brands, partial=False)
        with self._locked():
            data = self._read_raw()
            if username in data["users"]:
                raise UserStoreError("user_exists")
            rec = {
                "username": username, "pw": password_hash, "must_change": bool(must_change),
                "disabled": False, "sv": 1, "created_at": now_iso(), "created_by": actor,
                "updated_at": now_iso(), "last_login": None,
            }
            rec.update(clean)
            data["users"][username] = rec
            self._write_raw(data)
        self.audit(actor, "user_created", username, {k: clean[k] for k in ("roles", "brands", "lang")})
        return copy.deepcopy(rec)

    def update(self, actor, username, mutate, audit_action, audit_detail=None, bump_sv=False):
        """mutate(record) edits in place under the lock (it may raise UserStoreError to refuse)."""
        with self._locked():
            data = self._read_raw()
            rec = data["users"].get(username)
            if not rec:
                raise UserStoreError("not_found")
            before = copy.deepcopy(rec)
            mutate(rec, data["users"])
            if rec == before:
                return copy.deepcopy(rec), False
            if bump_sv:
                rec["sv"] = int(rec.get("sv", 1)) + 1
            rec["updated_at"] = now_iso()
            self._write_raw(data)
        if audit_action:
            self.audit(actor, audit_action, username, audit_detail)
        return copy.deepcopy(rec), True

    def touch_login(self, username):
        def m(rec, _all):
            rec["last_login"] = now_iso()
        with contextlib.suppress(UserStoreError):
            self.update(username, username, m, None)


def public_user(u):
    """The shape the browser sees. No hash, no session version."""
    return {
        "username": u["username"], "display_name": u.get("display_name", ""), "roles": u.get("roles", []),
        "brands": u.get("brands", []), "lang": u.get("lang", "he"), "disabled": bool(u.get("disabled")),
        "must_change": bool(u.get("must_change")), "created_at": u.get("created_at"),
        "updated_at": u.get("updated_at"), "last_login": u.get("last_login"),
    }


def seconds_since(iso):
    try:
        return time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
