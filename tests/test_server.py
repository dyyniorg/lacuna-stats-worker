import http.client
import json
import sqlite3
import threading
from pathlib import Path

import server
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


def make_settings(tmp_path: Path) -> store.Settings:
    return store.Settings(stats_token="test-token-123456", data_dir=tmp_path, max_body_bytes=1024)


def request(
    port: int,
    method: str,
    path: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def event_count(settings: store.Settings) -> int:
    connection = sqlite3.connect(settings.database_path)
    try:
        return connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        connection.close()


def test_server_endpoints(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store.initialize_database(settings)
    httpd = server.StatsServer(("127.0.0.1", 0), settings)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    body = json.dumps(example_payload()).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {settings.stats_token}",
        "Content-Type": "application/json",
    }

    try:
        status, _ = request(port, "POST", "/lacuna/stats", body, headers)
        assert status == 204
        assert event_count(settings) == 1

        status, _ = request(port, "POST", "/lacuna/stats", body, headers)
        assert status == 204
        assert event_count(settings) == 1

        bad_token_headers = {
            "Authorization": "Bearer wrong-token",
            "Content-Type": "application/json",
        }
        status, _ = request(port, "POST", "/lacuna/stats", body, bad_token_headers)
        assert status == 401

        status, _ = request(port, "POST", "/lacuna/stats", b"{", headers)
        assert status == 400

        bad_payload = example_payload()
        bad_payload["version"] = "1"
        status, _ = request(port, "POST", "/lacuna/stats", json.dumps(bad_payload).encode("utf-8"), headers)
        assert status == 422

        status, _ = request(port, "POST", "/lacuna/stats", b"x" * 1025, headers)
        assert status == 413

        chart_bytes = b"\x89PNG\r\n\x1a\nchart"
        settings.chart_path.write_bytes(chart_bytes)
        status, response_body = request(port, "GET", "/chart.png")
        assert status == 200
        assert response_body == chart_bytes

        status, _ = request(port, "GET", "/unknown")
        assert status == 404
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert not thread.is_alive()
