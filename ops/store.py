"""Key-value store with the few Redis primitives the agent needs, in two backends behind one interface:

* RedisStore  - Upstash Redis REST API (hosted, serverless-safe; free tier)
* SQLiteStore - a local file or ":memory:" (development and tests)

Values are JSON. Lists follow Redis semantics (rpush appends, lrange stop is inclusive, negative indexes allowed).
"""
import json
import os
import sqlite3
import threading
import time
import urllib.request


def _slice(items, start, stop):
    n = len(items)
    start = max(n + start, 0) if start < 0 else start
    stop = n + stop if stop < 0 else stop
    return items[start:stop + 1]


class Store:
    def get(self, key, default=None): raise NotImplementedError
    def set(self, key, value, ttl=None): raise NotImplementedError
    def set_nx(self, key, value, ttl=None): raise NotImplementedError  # -> True if it was set
    def delete(self, key): raise NotImplementedError
    def incr(self, key, ttl=None): raise NotImplementedError        # -> new value; ttl only set on creation
    def rpush(self, key, value, ttl=None): raise NotImplementedError
    def lrange(self, key, start=0, stop=-1): raise NotImplementedError
    def ltrim(self, key, start, stop): raise NotImplementedError
    def sadd(self, key, member): raise NotImplementedError
    def srem(self, key, member): raise NotImplementedError
    def smembers(self, key): raise NotImplementedError
    kind = "abstract"


class SQLiteStore(Store):
    kind = "sqlite"

    def __init__(self, path=":memory:"):
        self.con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.Lock()
        with self.lock:
            self.con.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, exp REAL)")
            self.con.execute("CREATE TABLE IF NOT EXISTS lists (id INTEGER PRIMARY KEY AUTOINCREMENT, k TEXT, v TEXT)")
            self.con.execute("CREATE INDEX IF NOT EXISTS ix_lists_k ON lists(k, id)")
            self.con.execute("CREATE TABLE IF NOT EXISTS sets (k TEXT, m TEXT, PRIMARY KEY (k, m))")

    def _purge(self, key):
        self.con.execute("DELETE FROM kv WHERE k = ? AND exp IS NOT NULL AND exp < ?", (key, time.time()))

    @staticmethod
    def _exp(ttl):
        return time.time() + ttl if ttl else None

    def get(self, key, default=None):
        with self.lock:
            self._purge(key)
            row = self.con.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key, value, ttl=None):
        with self.lock:
            self.con.execute("INSERT OR REPLACE INTO kv (k, v, exp) VALUES (?, ?, ?)",
                             (key, json.dumps(value), self._exp(ttl)))

    def set_nx(self, key, value, ttl=None):
        with self.lock:
            self._purge(key)
            cur = self.con.execute("INSERT OR IGNORE INTO kv (k, v, exp) VALUES (?, ?, ?)",
                                   (key, json.dumps(value), self._exp(ttl)))
            return cur.rowcount == 1

    def delete(self, key):
        with self.lock:
            self.con.execute("DELETE FROM kv WHERE k = ?", (key,))
            self.con.execute("DELETE FROM lists WHERE k = ?", (key,))
            self.con.execute("DELETE FROM sets WHERE k = ?", (key,))

    def incr(self, key, ttl=None):
        with self.lock:
            self._purge(key)
            row = self.con.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
            if row is None:
                self.con.execute("INSERT INTO kv (k, v, exp) VALUES (?, '1', ?)", (key, self._exp(ttl)))
                return 1
            value = int(json.loads(row[0])) + 1
            self.con.execute("UPDATE kv SET v = ? WHERE k = ?", (json.dumps(value), key))
            return value

    def rpush(self, key, value, ttl=None):
        with self.lock:
            self.con.execute("INSERT INTO lists (k, v) VALUES (?, ?)", (key, json.dumps(value)))
            if ttl:  # list expiry is tracked through a kv marker
                self.con.execute("INSERT OR REPLACE INTO kv (k, v, exp) VALUES (?, '1', ?)",
                                 (f"__ttl__:{key}", self._exp(ttl)))

    def _list_alive(self, key):
        marker = self.con.execute("SELECT exp FROM kv WHERE k = ?", (f"__ttl__:{key}",)).fetchone()
        if marker and marker[0] is not None and marker[0] < time.time():
            self.con.execute("DELETE FROM lists WHERE k = ?", (key,))
            self.con.execute("DELETE FROM kv WHERE k = ?", (f"__ttl__:{key}",))

    def lrange(self, key, start=0, stop=-1):
        with self.lock:
            self._list_alive(key)
            rows = [json.loads(r[0]) for r in self.con.execute("SELECT v FROM lists WHERE k = ? ORDER BY id", (key,))]
        return _slice(rows, start, stop)

    def ltrim(self, key, start, stop):
        with self.lock:
            ids = [r[0] for r in self.con.execute("SELECT id FROM lists WHERE k = ? ORDER BY id", (key,))]
            keep = set(_slice(ids, start, stop))
            for i in ids:
                if i not in keep:
                    self.con.execute("DELETE FROM lists WHERE id = ?", (i,))

    def sadd(self, key, member):
        with self.lock:
            self.con.execute("INSERT OR IGNORE INTO sets (k, m) VALUES (?, ?)", (key, str(member)))

    def srem(self, key, member):
        with self.lock:
            self.con.execute("DELETE FROM sets WHERE k = ? AND m = ?", (key, str(member)))

    def smembers(self, key):
        with self.lock:
            return {r[0] for r in self.con.execute("SELECT m FROM sets WHERE k = ?", (key,))}


class RedisStore(Store):
    """Upstash Redis over its REST API: POST [command, args...] with a bearer token -> {"result": ...}."""
    kind = "redis"

    def __init__(self, url, token, transport=None):
        self.url, self.token = url.rstrip("/"), token
        self.transport = transport or self._http

    def _http(self, command):
        req = urllib.request.Request(self.url, data=json.dumps(command).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
        if "error" in body:
            raise RuntimeError(f"Redis error: {body['error']}")
        return body.get("result")

    def _cmd(self, *args):
        return self.transport([str(a) for a in args])

    def get(self, key, default=None):
        raw = self._cmd("GET", key)
        return json.loads(raw) if raw is not None else default

    def set(self, key, value, ttl=None):
        self._cmd("SET", key, json.dumps(value), *(["EX", int(ttl)] if ttl else []))

    def set_nx(self, key, value, ttl=None):
        return self._cmd("SET", key, json.dumps(value), "NX", *(["EX", int(ttl)] if ttl else [])) == "OK"

    def delete(self, key):
        self._cmd("DEL", key)

    def incr(self, key, ttl=None):
        value = int(self._cmd("INCR", key))
        if value == 1 and ttl:
            self._cmd("EXPIRE", key, int(ttl))
        return value

    def rpush(self, key, value, ttl=None):
        self._cmd("RPUSH", key, json.dumps(value))
        if ttl:
            self._cmd("EXPIRE", key, int(ttl))

    def lrange(self, key, start=0, stop=-1):
        return [json.loads(x) for x in (self._cmd("LRANGE", key, start, stop) or [])]

    def ltrim(self, key, start, stop):
        self._cmd("LTRIM", key, start, stop)

    def sadd(self, key, member):
        self._cmd("SADD", key, member)

    def srem(self, key, member):
        self._cmd("SREM", key, member)

    def smembers(self, key):
        return set(self._cmd("SMEMBERS", key) or [])


def from_settings(settings):
    if settings.redis_url and settings.redis_token:
        return RedisStore(settings.redis_url, settings.redis_token)
    if os.environ.get("VERCEL"):  # read-only filesystem: /tmp works but is per-instance and temporary
        return SQLiteStore("/tmp/fleetlog-ops.db")
    path = settings.sqlite_path or ":memory:"
    if path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return SQLiteStore(path)
