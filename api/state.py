"""Small SQLite store for API-only state: users, alert read-marks and the JWT secret."""
import hashlib
import hmac
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import settings as S

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, full_name TEXT, role TEXT NOT NULL,
    salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_reads (
    username TEXT NOT NULL, alert_id TEXT NOT NULL, read_at TEXT NOT NULL, PRIMARY KEY (username, alert_id));
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
_ITERATIONS = 200_000
_secret_cache = None


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def db():
    con = sqlite3.connect(S.STATE_DB)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return salt, digest.hex()


def init():
    """Create tables and the admin user. Returns warnings to log."""
    warnings = []
    S.RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript(_SCHEMA)
        if not con.execute("SELECT 1 FROM users WHERE username = ?", (S.ADMIN_USER,)).fetchone():
            if not S.ADMIN_PASSWORD:
                warnings.append(f"Created user '{S.ADMIN_USER}' with the local demo password. "
                                "Set FLEET_ADMIN_PASSWORD before exposing the API beyond a local demo.")
            salt, digest = hash_password(S.ADMIN_PASSWORD or S.DEMO_PASSWORD)
            con.execute("INSERT INTO users VALUES (?, ?, ?, ?, ?, ?)",
                        (S.ADMIN_USER, S.ADMIN_NAME, "admin", salt, digest, now()))
    return warnings


def jwt_secret():
    global _secret_cache
    if S.JWT_SECRET:
        return S.JWT_SECRET
    if _secret_cache is None:
        with db() as con:
            row = con.execute("SELECT value FROM meta WHERE key = 'jwt_secret'").fetchone()
            if row is None:
                value = secrets.token_urlsafe(48)
                con.execute("INSERT INTO meta VALUES ('jwt_secret', ?)", (value,))
            else:
                value = row["value"]
        _secret_cache = value
    return _secret_cache


def _public(row):
    return {"username": row["username"], "full_name": row["full_name"], "role": row["role"]}


def get_user(username):
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return _public(row) if row else None


def verify_user(username, password):
    with db() as con:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        hash_password(password)  # same work either way, so timing does not reveal valid usernames
        return None
    _, digest = hash_password(password, row["salt"])
    return _public(row) if hmac.compare_digest(digest, row["password_hash"]) else None


def read_alert_ids(username):
    with db() as con:
        return {r["alert_id"] for r in con.execute("SELECT alert_id FROM alert_reads WHERE username = ?", (username,))}


def mark_read(username, alert_ids):
    with db() as con:
        con.executemany("INSERT OR IGNORE INTO alert_reads VALUES (?, ?, ?)", [(username, a, now()) for a in alert_ids])
