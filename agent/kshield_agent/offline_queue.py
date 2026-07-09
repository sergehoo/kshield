"""KAYDAN SHIELD — Kaydan Edge Gateway v2, queue offline SQLite.

Quand la connexion WS ou HTTP est down, les événements sont écrits dans une
SQLite locale et rejoués automatiquement à la reconnexion.

Table simple :
    events(id INTEGER PK, topic TEXT, payload JSON, created_at TEXT,
            attempts INT DEFAULT 0, last_error TEXT)

Le rejeu se fait dans l'ordre chronologique (FIFO). Chaque envoi réussi
supprime la ligne. Après 10 tentatives → passage en "dead letter" (colonne
``dead=1``) pour ne pas boucler indéfiniment.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 10


class OfflineQueue:
    """Queue SQLite thread-safe pour l'offline-first."""

    def __init__(self, path: str):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    dead INTEGER DEFAULT 0
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_status "
                "ON events(dead, created_at)"
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(str(self.path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ────────────────────────────────────────────────────────────
    # Écriture
    # ────────────────────────────────────────────────────────────
    def enqueue(self, topic: str, payload: dict):
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO events(topic, payload, created_at) VALUES(?,?,?)",
                (topic, json.dumps(payload, default=str),
                 datetime.utcnow().isoformat()),
            )

    # ────────────────────────────────────────────────────────────
    # Rejeu
    # ────────────────────────────────────────────────────────────
    def peek(self, limit: int = 100) -> list[dict]:
        """Retourne les prochains événements à rejouer (non-dead), plus ancien d'abord."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, topic, payload, created_at, attempts, last_error "
                "FROM events WHERE dead=0 ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "topic": r[1],
              "payload": json.loads(r[2]) if r[2] else {},
              "created_at": r[3], "attempts": r[4], "last_error": r[5]}
            for r in rows
        ]

    def ack(self, event_id: int):
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM events WHERE id=?", (event_id,))

    def fail(self, event_id: int, error: str):
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE events "
                "SET attempts=attempts+1, last_error=?, "
                "    dead=CASE WHEN attempts+1 >= ? THEN 1 ELSE 0 END "
                "WHERE id=?",
                (error[:500], MAX_ATTEMPTS, event_id),
            )

    def stats(self) -> dict:
        with self._lock, self._connect() as conn:
            r = conn.execute(
                "SELECT "
                "SUM(CASE WHEN dead=0 THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN dead=1 THEN 1 ELSE 0 END), "
                "COUNT(*) "
                "FROM events",
            ).fetchone()
        return {
            "pending": r[0] or 0,
            "dead":    r[1] or 0,
            "total":   r[2] or 0,
        }

    def drain_dead(self):
        """Purge les events morts (à appeler manuellement après investigation)."""
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM events WHERE dead=1")


# Configuration par défaut
DEFAULT_QUEUE_PATH = "~/.kshield-agent/offline-queue.sqlite"
