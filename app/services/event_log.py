import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

_DB_PATH = Path(settings.data_dir) / "event_log.db"
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS process_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_uuid TEXT NOT NULL,
                phase_number INTEGER,
                step_name TEXT,
                event TEXT NOT NULL,
                detail TEXT,
                timestamp TEXT NOT NULL
            )
            """
        )
        _conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_process_events_workflow
            ON process_events (workflow_uuid, timestamp)
            """
        )
        _conn.commit()
    return _conn


def record(workflow_uuid: str, event: str, phase_number: int | None = None, step_name: str | None = None, detail: dict | str | None = None) -> int:
    conn = _get_conn()
    ts = datetime.now(timezone.utc).isoformat()
    detail_str = json.dumps(detail) if isinstance(detail, dict) else detail
    cur = conn.execute(
        """
        INSERT INTO process_events (workflow_uuid, phase_number, step_name, event, detail, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (workflow_uuid, phase_number, step_name, event, detail_str, ts),
    )
    conn.commit()
    return cur.lastrowid


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None
