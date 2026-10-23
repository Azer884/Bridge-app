"""SQLite persistence: conversation state, message log, and message-id deduplication.

Each call opens its own short-lived connection (WAL mode), so concurrent requests from many
customers do not share a connection. Calls for the same customer are serialised with lock().
SQLite is enough for a demo; the same interface can sit on Postgres later.
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

    def conversations(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT state FROM conversations").fetchall()
        return [ConversationState(**json.loads(row[0])) for row in rows]

    def claim_message(self, message_id, conversation_id):
        """True the first time a message id is seen. WhatsApp retries webhooks, so repeats are dropped."""
        with self._conn() as conn:
            cursor = conn.execute("INSERT OR IGNORE INTO processed_messages VALUES (?,?,?)",
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
