"""
security.py — password hashing, login rate limiting, and the engine token.

Safety model:
 - Passwords: PBKDF2-HMAC-SHA256, 16-byte random salt per user, PBKDF2_ITERATIONS rounds (>= 310k,
   OWASP). Stored as "pbkdf2_sha256$<iter>$<salt b64>$<hash b64>" so the count can rise later without a
   migration: verify() reads the count from the stored string, needs_rehash() says when to upgrade.
 - Unknown usernames are hashed against a dummy record, so response time does not reveal which
   usernames exist.
 - Rate limiting counts FAILED logins per IP and per username in sliding windows. It lives in memory, so
   the service runs ONE gunicorn worker (threads for concurrency) — see render.yaml.
 - Engine token: byte-for-byte the format Api.gs verifyToken_ accepts:
       base64url(payloadJson) + "." + base64url(HMAC-SHA256(key=TOKEN_SECRET, msg=<payload b64 string>))
   no padding, payload = {user, role, brands, lang, iat, exp} (epoch seconds). Minted per call, ~10 min.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque

PBKDF2_ITERATIONS = 600_000          # OWASP 2023 for PBKDF2-HMAC-SHA256; the floor the brief sets is 310k
PBKDF2_MIN_ITERATIONS = 310_000
SALT_BYTES = 16

ENGINE_TOKEN_TTL_S = 600             # minted per call
ENGINE_TOKEN_MAX_S = 12 * 3600       # Api.gs TOKEN_MAX_AGE_S
TOKEN_SECRET_MIN = 32                # Api.gs fails closed below this

# Engine roles, most privileged first. A user can hold several local roles (e.g. admin + user-manager);
# the token carries ONE role, the strongest one the engine knows.
ENGINE_ROLE_ORDER = ("admin", "agent", "user-manager")


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------- passwords ----------

def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    if iterations < PBKDF2_MIN_ITERATIONS:
        raise ValueError("iterations below the floor")
    salt = os.urandom(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256$%d$%s$%s" % (iterations, _b64(salt), _b64(dk))


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt_b64, hash_b64 = stored.split("$")
        it = int(it)
        if algo != "pbkdf2_sha256" or it < PBKDF2_MIN_ITERATIONS or it > 10_000_000:
            return False
        salt = base64.b64decode(salt_b64)
        want = base64.b64decode(hash_b64)
    except Exception:
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, it)
    return hmac.compare_digest(got, want)


def needs_rehash(stored: str) -> bool:
    try:
        return int(stored.split("$")[1]) < PBKDF2_ITERATIONS
    except Exception:
        return True


# A fixed dummy hash, computed once, so a login for an unknown user costs the same time.
_DUMMY_HASH = None
_DUMMY_LOCK = threading.Lock()


def burn_time_for_unknown_user(password: str) -> None:
    global _DUMMY_HASH
    with _DUMMY_LOCK:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
    verify_password(password, _DUMMY_HASH)


def temp_password() -> str:
    """One-time password for a new user / a reset: 4 groups, no look-alike characters, ~80 bits."""
    alphabet = "abcdefghjkmnpqrstuvwxyzACDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(4))


PASSWORD_MIN = 10


def password_problem(pw: str, username: str = ""):
    """None when acceptable, else an error code (translated by messages.py)."""
    if not isinstance(pw, str) or len(pw) < PASSWORD_MIN:
        return "password_too_short"
    if len(pw) > 200:
        return "password_too_long"
    if username and username.lower() in pw.lower():
        return "password_contains_username"
    if len(set(pw)) < 5:
        return "password_too_simple"
    return None


# ---------- rate limiting ----------

class LoginLimiter:
    """
    Sliding-window counter of failed logins. A key is blocked once it has `limit` failures inside
    `window_s`. Success clears the username counter (not the IP one: an attacker with one valid account
    must not reset the IP budget it is spending on other accounts).
    """

    def __init__(self, per_ip=20, per_user=5, window_s=15 * 60, clock=time.monotonic, max_keys=50_000):
        self.max_keys = max_keys
        self.per_ip = per_ip
        self.per_user = per_user
        self.window_s = window_s
        self.clock = clock
        self._hits = {}
        self._lock = threading.Lock()

    def _trim(self, key):
        q = self._hits.get(key)
        if not q:
            return 0
        cutoff = self.clock() - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        if not q:
            self._hits.pop(key, None)
            return 0
        return len(q)

    def blocked(self, ip: str, username: str):
        """Seconds to wait (int > 0) or 0 when allowed."""
        with self._lock:
            waits = []
            for key, limit in (("ip:" + ip, self.per_ip), ("u:" + username.lower(), self.per_user)):
                if self._trim(key) >= limit:
                    waits.append(int(self._hits[key][0] + self.window_s - self.clock()) + 1)
            return max(waits) if waits else 0

    def fail(self, ip: str, username: str):
        with self._lock:
            now = self.clock()
            for key in ("ip:" + ip, "u:" + username.lower()):
                self._hits.setdefault(key, deque()).append(now)
            if len(self._hits) > self.max_keys:
                self._shrink()

    def _shrink(self):
        """Memory guard (Codex 2026-10-05): drop EXPIRED windows first; if still over the cap, drop the
        least recently active USERNAME keys only. IP keys are never evicted while active, so spraying
        random usernames cannot free the IP that is doing the spraying."""
        for k in list(self._hits):
            self._trim(k)
        if len(self._hits) <= self.max_keys:
            return
        users = sorted((q[-1], k) for k, q in self._hits.items() if k.startswith("u:"))
        for _, k in users[: len(self._hits) - self.max_keys + self.max_keys // 10]:
            self._hits.pop(k, None)

    def success(self, username: str):
        with self._lock:
            self._hits.pop("u:" + username.lower(), None)


# ---------- engine token ----------

def engine_role(roles) -> str:
    for r in ENGINE_ROLE_ORDER:
        if r in roles:
            return r
    raise ValueError("user has no engine role")


def mint_engine_token(secret: str, user: str, role: str, brands, lang: str, ttl_s: int = ENGINE_TOKEN_TTL_S, now=None) -> str:
    if not isinstance(secret, str) or len(secret) < TOKEN_SECRET_MIN:
        raise ValueError("TOKEN_SECRET missing or shorter than 32 characters")
    if ttl_s <= 0 or ttl_s > ENGINE_TOKEN_MAX_S:
        raise ValueError("token lifetime must be within 12h")
    iat = int(now if now is not None else time.time())
    payload = {"user": user, "role": role, "brands": list(brands), "lang": lang, "iat": iat, "exp": iat + ttl_s}
    p64 = b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    sig = b64url(hmac.new(secret.encode("utf-8"), p64.encode("ascii"), hashlib.sha256).digest())
    return p64 + "." + sig
