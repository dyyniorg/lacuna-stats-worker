from __future__ import annotations

import os
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import msgspec

RENDER_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    event_time INTEGER NOT NULL,
    municipality TEXT NOT NULL,
    round_id TEXT NOT NULL,
    cell TEXT NOT NULL,
    osm_user TEXT NOT NULL,
    changeset_id INTEGER NOT NULL,
    produced_created INTEGER NOT NULL,
    produced_modified INTEGER NOT NULL,
    committed_created INTEGER NOT NULL,
    committed_modified INTEGER NOT NULL,
    received_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS render_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    max_rowid INTEGER NOT NULL,
    event_count INTEGER NOT NULL,
    rendered_at INTEGER NOT NULL,
    render_version INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Settings:
    stats_token: str
    data_dir: Path = Path("/data")
    max_body_bytes: int = 1024
    render_check_seconds: int = 3600
    render_min_interval_seconds: int = 86400

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_dir", Path(self.data_dir))

        if len(self.stats_token) < 16:
            raise ValueError("STATS_TOKEN must be at least 16 characters")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "stats.db"

    @property
    def chart_path(self) -> Path:
        return self.data_dir / "chart.png"

    @classmethod
    def from_env(cls) -> Settings:
        token = os.environ.get("STATS_TOKEN", "")

        return cls(
            stats_token=token,
            data_dir=Path(os.environ.get("DATA_DIR", "/data")),
            max_body_bytes=int(os.environ.get("MAX_BODY_BYTES", "1024")),
            render_check_seconds=int(os.environ.get("RENDER_CHECK_SECONDS", "3600")),
            render_min_interval_seconds=int(os.environ.get("RENDER_MIN_INTERVAL_SECONDS", "86400")),
        )


class Counts(msgspec.Struct):
    created: int
    modified: int


class Event(msgspec.Struct):
    version: int
    event_id: str
    time: str
    municipality: str
    round_id: str
    cell: str
    osm_user: str
    changeset_id: int
    produced: Counts
    committed: Counts


def validate_event(body: bytes) -> Event:
    event = msgspec.json.decode(body, type=Event)

    if event.event_id != f"{event.round_id}/{event.municipality}/{event.cell}":
        raise msgspec.ValidationError("event_id does not match round_id, municipality, and cell")

    return event


def connect(settings: Settings) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.database_path, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")

    return connection


def initialize_database(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    with closing(connect(settings)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.executescript(SCHEMA)
        connection.commit()


def insert_event(settings: Settings, event: Event) -> None:
    with closing(connect(settings)) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO events (
                event_id,
                version,
                event_time,
                municipality,
                round_id,
                cell,
                osm_user,
                changeset_id,
                produced_created,
                produced_modified,
                committed_created,
                committed_modified,
                received_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.version,
                int(event.time),
                event.municipality,
                event.round_id,
                event.cell,
                event.osm_user,
                event.changeset_id,
                event.produced.created,
                event.produced.modified,
                event.committed.created,
                event.committed.modified,
                int(time.time()),
            ),
        )
        connection.commit()


def get_event_totals(settings: Settings) -> tuple[int, int, int]:
    with closing(connect(settings)) as connection:
        row = connection.execute("""
            SELECT
                COALESCE(MAX(rowid), 0) AS max_rowid,
                COUNT(*) AS event_count,
                COUNT(DISTINCT date(event_time, 'unixepoch')) AS day_count
            FROM events
            """).fetchone()
        assert row is not None

        return row["max_rowid"], row["event_count"], row["day_count"]


def get_daily_aggregates(settings: Settings) -> list[sqlite3.Row]:
    with closing(connect(settings)) as connection:
        return connection.execute("""
            SELECT
                date(event_time, 'unixepoch') AS day,
                SUM(produced_created) AS produced_created,
                SUM(produced_modified) AS produced_modified,
                SUM(committed_created) AS committed_created,
                SUM(committed_modified) AS committed_modified
            FROM events
            GROUP BY day
            ORDER BY day
            """).fetchall()


def get_render_state(settings: Settings) -> sqlite3.Row | None:
    with closing(connect(settings)) as connection:
        return connection.execute(
            "SELECT max_rowid, event_count, rendered_at, render_version FROM render_state WHERE id = 1"
        ).fetchone()


def save_render_state(settings: Settings, max_rowid: int, event_count: int) -> None:
    with closing(connect(settings)) as connection:
        connection.execute(
            """
            INSERT INTO render_state (id, max_rowid, event_count, rendered_at, render_version)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                max_rowid = excluded.max_rowid,
                event_count = excluded.event_count,
                rendered_at = excluded.rendered_at,
                render_version = excluded.render_version
            """,
            (max_rowid, event_count, int(time.time()), RENDER_VERSION),
        )
        connection.commit()
