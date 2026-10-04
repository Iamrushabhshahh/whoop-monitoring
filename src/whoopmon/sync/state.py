"""Local SQLite state: sync watermarks, sent record versions and seen webhook ids."""

import sqlite3
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS watermark (
    resource   TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS sent (
    resource   TEXT NOT NULL,
    record_key TEXT NOT NULL,
    sent_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (resource, record_key)
);
CREATE TABLE IF NOT EXISTS webhook_seen (
    trace_id    TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE TABLE IF NOT EXISTS sync_run (
    run_id      TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    outcome     TEXT,
    detail      TEXT
);
"""


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    # watermarks
    def get_watermark(self, resource: str) -> datetime | None:
        row = self._db.execute(
            "SELECT value FROM watermark WHERE resource=?", (resource,)
        ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def set_watermark(self, resource: str, value: datetime) -> None:
        self._db.execute(
            "INSERT INTO watermark(resource, value) VALUES(?, ?) "
            "ON CONFLICT(resource) DO UPDATE SET value=excluded.value, "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ', 'now')",
            (resource, value.isoformat()),
        )

    # record versions already shipped
    def unsent(self, resource: str, keys: Iterable[str]) -> set[str]:
        keys = list(keys)
        if not keys:
            return set()
        placeholders = ",".join("?" * len(keys))
        sent = {
            r[0]
            for r in self._db.execute(
                f"SELECT record_key FROM sent WHERE resource=? AND record_key IN ({placeholders})",  # noqa: S608
                (resource, *keys),
            )
        }
        return set(keys) - sent

    def mark_sent(self, resource: str, keys: Iterable[str]) -> None:
        self._db.executemany(
            "INSERT OR IGNORE INTO sent(resource, record_key) VALUES(?, ?)",
            [(resource, k) for k in keys],
        )

    # webhook de-duplication; returns True when the trace id is new
    def remember_webhook(self, trace_id: str) -> bool:
        cur = self._db.execute(
            "INSERT OR IGNORE INTO webhook_seen(trace_id) VALUES(?)", (trace_id,)
        )
        return cur.rowcount == 1

    # run log
    def start_run(self, run_id: str, started_at: datetime) -> None:
        self._db.execute(
            "INSERT INTO sync_run(run_id, started_at) VALUES(?, ?)",
            (run_id, started_at.isoformat()),
        )

    def finish_run(
        self, run_id: str, finished_at: datetime, outcome: str, detail: str = ""
    ) -> None:
        self._db.execute(
            "UPDATE sync_run SET finished_at=?, outcome=?, detail=? WHERE run_id=?",
            (finished_at.isoformat(), outcome, detail, run_id),
        )

    def last_runs(self, limit: int = 5) -> list[tuple[str, str, str | None, str | None]]:
        return self._db.execute(
            "SELECT run_id, started_at, finished_at, outcome FROM sync_run "
            "ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
