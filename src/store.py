"""SQLite persistence: conversation state, message log, and message-id deduplication.

Each call opens its own short-lived connection (WAL mode), so concurrent requests from many
customers do not share a connection. Calls for the same customer are serialised with lock().
SQLite is enough for local runs. On Replit the deployment's files are replaced on every republish, so there
the same interface runs on Replit's PostgreSQL (PostgresStore): make_store() picks it when DATABASE_URL is set.
"""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

from .conversation import ConversationState

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, received_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, direction TEXT NOT NULL,
    text TEXT NOT NULL, media_id TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages (conversation_id, id);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
"""


class SqliteStore:
    def __init__(self, path="data/bridge.db"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._locks, self._guard = {}, threading.Lock()
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def lock(self, conversation_id):
        """One customer's messages are handled one at a time; different customers run in parallel."""
        with self._guard:
            lock = self._locks.setdefault(conversation_id, threading.Lock())
        with lock:
            yield

    def load(self, conversation_id):
        with self._conn() as conn:
            row = conn.execute("SELECT state FROM conversations WHERE conversation_id=?",
                               (conversation_id,)).fetchone()
        if row:
            return ConversationState(**json.loads(row[0]))
        return ConversationState(conversation_id=conversation_id)

    def save(self, state):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO conversations VALUES (?,?,?) ON CONFLICT(conversation_id) "
                "DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
                (state.conversation_id, json.dumps(asdict(state)), time.time()))

    def get_setting(self, key, default=None):
        """Dashboard-managed settings (personas, the active persona), stored as JSON."""
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_setting(self, key, value):
        with self._conn() as conn:
            conn.execute("INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (key, json.dumps(value)))

    def log_event(self, kind, detail=""):
        """Operational trail (webhook arrivals, send failures, handler errors), newest 500 kept.
        It exists because the hosting platform's runtime logs were not readable."""
        with self._conn() as conn:
            conn.execute("INSERT INTO events (ts, kind, detail) VALUES (?,?,?)", (time.time(), kind, str(detail)[:600]))
            conn.execute("DELETE FROM events WHERE id <= (SELECT MAX(id) FROM events) - 500")

    def events(self, limit=50):
        with self._conn() as conn:
            rows = conn.execute("SELECT ts, kind, detail FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": ts, "kind": kind, "detail": detail} for ts, kind, detail in rows]

    backend = "sqlite"

    def stats(self):
        """Which database is in use and how much it holds: the quick check that data survives a republish."""
        with self._conn() as conn:
            counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("conversations", "messages", "events")}
        return {"backend": self.backend, **counts}

    def conversations(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT state FROM conversations").fetchall()
        return [ConversationState(**json.loads(row[0])) for row in rows]

    def claim_message(self, message_id, conversation_id):
        """True the first time a message id is seen. WhatsApp retries webhooks, so repeats are dropped."""
        with self._conn() as conn:
            cursor = conn.execute("INSERT INTO processed_messages VALUES (?,?,?) ON CONFLICT DO NOTHING",
                                  (message_id, conversation_id, time.time()))
            return cursor.rowcount == 1

    def release_message(self, message_id):
        """Undo a claim when processing crashed, so the provider's retry is not discarded."""
        with self._conn() as conn:
            conn.execute("DELETE FROM processed_messages WHERE message_id=?", (message_id,))

    def log_message(self, conversation_id, direction, text, media_id=""):
        with self._conn() as conn:
            conn.execute("INSERT INTO messages (conversation_id, direction, text, media_id, created_at) "
                         "VALUES (?,?,?,?,?)", (conversation_id, direction, text, media_id, time.time()))

    def messages(self, conversation_id):
        with self._conn() as conn:
            rows = conn.execute("SELECT direction, text, media_id FROM messages WHERE conversation_id=? "
                                "ORDER BY id", (conversation_id,)).fetchall()
        return [{"direction": d, "text": t, "media_id": m} for d, t, m in rows]


PG_SCHEMA = [
    "CREATE TABLE IF NOT EXISTS conversations (conversation_id TEXT PRIMARY KEY, state TEXT NOT NULL, "
    "updated_at DOUBLE PRECISION NOT NULL)",
    "CREATE TABLE IF NOT EXISTS processed_messages (message_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, "
    "received_at DOUBLE PRECISION NOT NULL)",
    "CREATE TABLE IF NOT EXISTS messages (id BIGSERIAL PRIMARY KEY, conversation_id TEXT NOT NULL, "
    "direction TEXT NOT NULL, text TEXT NOT NULL, media_id TEXT NOT NULL DEFAULT '', "
    "created_at DOUBLE PRECISION NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages (conversation_id, id)",
    "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS events (id BIGSERIAL PRIMARY KEY, ts DOUBLE PRECISION NOT NULL, "
    "kind TEXT NOT NULL, detail TEXT NOT NULL)",
]


class _PgConnection:
    """Gives a psycopg connection the small sqlite3-style surface the store uses: execute() with ? marks."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        cursor = self.conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor


class PostgresStore(SqliteStore):
    """The same store on PostgreSQL (Replit's database). Needs `psycopg[binary]`."""

    backend = "postgres"

    def __init__(self, url):
        self.url = url
        self._locks, self._guard = {}, threading.Lock()
        self._pool = self._open_pool(url)
        with self._conn() as conn:
            for statement in PG_SCHEMA:
                conn.execute(statement)

    @staticmethod
    def _open_pool(url):
        """A small connection pool when psycopg_pool is installed (each store call otherwise pays a fresh
        network connection to the database). Idle connections the server dropped are replaced."""
        try:
            from psycopg_pool import ConnectionPool
        except ImportError:
            return None
        return ConnectionPool(url, min_size=1, max_size=5, timeout=15, check=ConnectionPool.check_connection,
                              kwargs={"connect_timeout": 10}, open=True)

    @contextmanager
    def _conn(self):
        if self._pool is not None:
            with self._pool.connection() as conn:       # commits on success, rolls back on an exception
                yield _PgConnection(conn)
            return
        import psycopg                      # optional dependency, only needed on Postgres
        conn = psycopg.connect(self.url, connect_timeout=10)
        try:
            yield _PgConnection(conn)
            conn.commit()                   # an exception skips this and closing rolls the work back
        finally:
            conn.close()


def make_store(env, default_path):
    """PostgreSQL when DATABASE_URL points at one (Replit sets it), else the SQLite file."""
    url = env.get("DATABASE_URL") or ""
    if url.startswith(("postgres://", "postgresql://")):
        return PostgresStore(url)
    return SqliteStore(env.get("DATABASE_PATH") or default_path)
