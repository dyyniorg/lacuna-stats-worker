import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import render
import store


def make_settings(tmp_path: Path, min_interval: int = 86400) -> store.Settings:
    return store.Settings(
        stats_token="test-token-123456",
        data_dir=tmp_path,
        render_min_interval_seconds=min_interval,
    )


def fixed_event(day: str, cell: str, created: int, modified: int) -> store.Event:
    event_time = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())
    round_id = str(event_time)
    return store.Event(
        version=1,
        event_id=f"{round_id}/091/{cell}",
        time=str(event_time),
        municipality="091",
        round_id=round_id,
        cell=cell,
        osm_user="tester",
        changeset_id=1,
        produced=store.Counts(created=created, modified=modified),
        committed=store.Counts(created=created, modified=modified),
    )


def seed(settings: store.Settings, events: list[store.Event]) -> None:
    store.initialize_database(settings)
    for event in events:
        store.insert_event(settings, event)


def test_render_writes_chart(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed(
        settings,
        [
            fixed_event("2026-11-01", "01_10", 2, 1),
            fixed_event("2026-11-02", "01_11", 3, 2),
        ],
    )

    assert render.render_conditionally(settings) is True
    assert settings.chart_path.exists()
    assert settings.chart_path.stat().st_size > 0


def test_render_skips_single_day_data(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed(
        settings,
        [
            fixed_event("2026-11-01", "01_10", 2, 1),
            fixed_event("2026-11-01", "01_11", 3, 2),
        ],
    )

    assert render.render_conditionally(settings) is False
    assert render.render_conditionally(settings, force=True) is False
    assert not settings.chart_path.exists()


def test_render_skips_when_no_new_data(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed(
        settings,
        [
            fixed_event("2026-11-01", "01_10", 2, 1),
            fixed_event("2026-11-02", "01_11", 3, 2),
        ],
    )

    assert render.render_conditionally(settings) is True
    first_chart = settings.chart_path.read_bytes()

    assert render.render_conditionally(settings) is False
    assert settings.chart_path.read_bytes() == first_chart


def test_render_after_new_event_with_zero_interval(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed(
        settings,
        [
            fixed_event("2026-11-01", "01_10", 2, 1),
            fixed_event("2026-11-02", "01_11", 3, 2),
        ],
    )
    assert render.render_conditionally(settings) is True

    zero_interval_settings = make_settings(tmp_path, min_interval=0)
    store.insert_event(zero_interval_settings, fixed_event("2026-11-03", "01_12", 4, 2))

    assert render.render_conditionally(zero_interval_settings) is True


def test_render_skips_empty_database(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store.initialize_database(settings)

    assert render.render_conditionally(settings) is False
    assert render.render_conditionally(settings, force=True) is False
    assert not settings.chart_path.exists()


def test_render_state_is_updated(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    seed(
        settings,
        [
            fixed_event("2026-11-01", "01_10", 2, 1),
            fixed_event("2026-11-02", "01_11", 3, 2),
        ],
    )

    assert render.render_conditionally(settings) is True

    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    try:
        state = connection.execute(
            "SELECT max_rowid, event_count, rendered_at, render_version FROM render_state WHERE id = 1"
        ).fetchone()
    finally:
        connection.close()

    assert state["max_rowid"] == 2
    assert state["event_count"] == 2
    assert state["rendered_at"] > 0
    assert state["render_version"] == store.RENDER_VERSION
