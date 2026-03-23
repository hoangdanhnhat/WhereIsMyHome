"""SQLite-backed IP history storage."""

from __future__ import annotations

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IPRecord:
    ip: str
    timestamp: str  # ISO-8601 UTC


class IPStorage:
    """Thread-safe (single-writer) SQLite store for IP history."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        logger.info("Storage initialised at %s", db_path)

    # ---- schema ----------------------------------------------------------

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ip_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                ip        TEXT    NOT NULL,
                timestamp TEXT    NOT NULL
            )
            """
        )
        self._conn.commit()

    # ---- public API ------------------------------------------------------

    def get_current_ip(self) -> str | None:
        """Return the most-recently stored IP, or None."""
        row = self._conn.execute(
            "SELECT ip FROM ip_history ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def store_ip(self, ip: str) -> None:
        """Insert a new IP record."""
        ts = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO ip_history (ip, timestamp) VALUES (?, ?)",
            (ip, ts),
        )
        self._conn.commit()
        logger.info("Stored new IP: %s at %s", ip, ts)

    def get_history(self, limit: int = 20) -> list[IPRecord]:
        """Return the last *limit* IP changes, newest first."""
        rows = self._conn.execute(
            "SELECT ip, timestamp FROM ip_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [IPRecord(ip=r[0], timestamp=r[1]) for r in rows]

    def get_record_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM ip_history").fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self._conn.close()
        logger.info("Storage closed.")
