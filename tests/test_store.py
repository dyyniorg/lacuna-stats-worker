import json
import sqlite3
from pathlib import Path
from typing import cast

import msgspec
import pytest

import store


def example_payload() -> dict[str, object]:
    return {
        "version": 1,
        "event_id": "1794139200/291/01_10",
        "time": "1794139200",
        "municipality": "291",
        "round_id": "1794139200",
        "cell": "01_10",
        "osm_user": "example_user",
        "changeset_id": 123456789,
        "produced": {
            "created": 7,
            "modified": 2,
        },
        "committed": {
            "created": 7,
            "modified": 2,
        },
    }


def encode(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def make_settings(tmp_path: Path) -> store.Settings:
    return store.Settings(stats_token="test-token-123456", data_dir=tmp_path)


def test_example_event_is_valid() -> None:
    event = store.validate_event(encode(example_payload()))

    assert event.event_id == "1794139200/291/01_10"
    assert event.time == "1794139200"
    assert event.municipality == "291"
    assert event.round_id == "1794139200"
    assert event.cell == "01_10"
    assert event.osm_user == "example_user"
    assert event.changeset_id == 123456789
    assert event.produced.created == 7
    assert event.produced.modified == 2
    assert event.committed.created == 7
    assert event.committed.modified == 2


def test_rejects_event_id_mismatch() -> None:
    payload = example_payload()
    payload["event_id"] = "1794139200/999/01_10"

    with pytest.raises(msgspec.ValidationError):
        store.validate_event(encode(payload))


def test_ignores_extra_fields() -> None:
    payload = example_payload()
    payload["extra"] = True

    event = store.validate_event(encode(payload))

    assert event.event_id == "1794139200/291/01_10"


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("version",), "1"),
        (("time",), 1794139200),
        (("changeset_id",), True),
        (("produced", "created"), "7"),
    ],
)
def test_rejects_invalid_types(field_path: tuple[str, ...], value: object) -> None:
    payload = example_payload()
    target: dict[str, object] = payload
    for key in field_path[:-1]:
        target = cast("dict[str, object]", target[key])
    target[field_path[-1]] = value

    with pytest.raises(msgspec.ValidationError):
        store.validate_event(encode(payload))


def test_insert_is_idempotent_and_sets_received_at(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store.initialize_database(settings)
    event = store.validate_event(encode(example_payload()))

    store.insert_event(settings, event)
    store.insert_event(settings, event)

    connection = sqlite3.connect(settings.database_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS event_count, MIN(received_at) AS received_at FROM events"
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] == 1
    assert isinstance(row[1], int)
    assert row[1] > 0
