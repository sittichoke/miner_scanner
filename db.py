# db.py
import sqlite3
from typing import Any, Dict

from pydantic import BaseModel


class DB:
    """Tiny SQLite wrapper – swap out for Postgres / Influx / Timescale
    later by implementing the same interface."""

    def __init__(self, db_path: str = "miners.db") -> None:
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_schema()

    # ------------------------------------------------------------------ #
    def insert(self, data: BaseModel | Dict[str, Any]) -> None:
        """Accepts a Pydantic model or plain dict and writes a row."""
        payload = data.dict(by_alias=True) if isinstance(data, BaseModel) else data
        columns = ", ".join(payload.keys())
        placeholders = ", ".join("?" for _ in payload)
        sql = f"INSERT INTO miner_stats ({columns}) VALUES ({placeholders})"
        self.conn.execute(sql, list(payload.values()))
        self.conn.commit()

    # ------------------------------------------------------------------ #
    def _create_schema(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS miner_stats (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            collected_at  TEXT    NOT NULL,
            ip            TEXT    NOT NULL,
            model         TEXT,
            hashrate_5s   REAL,
            hashrate_avg  REAL,
            temperature   REAL,
            worker_name   TEXT,
            pool          TEXT,
            owner_name    TEXT,
            is_online     INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_miner_time ON miner_stats(ip, collected_at);
        """
        self.conn.executescript(ddl)
