from __future__ import annotations

import hmac
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import msgspec

import render
import store

LISTEN_PORT = 8000


class StatsHandler(BaseHTTPRequestHandler):
    protocol_version: str = "HTTP/1.1"
    close_connection: bool

    @property
    def settings(self) -> store.Settings:
        return cast("StatsServer", self.server).settings

    def _send_bytes(
        self,
        status: int,
        content_type: str,
        body: bytes,
        cache_control: str | None = None,
        close: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))

        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)

        if close:
            self.close_connection = True
            self.send_header("Connection", "close")

        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, message: str, close: bool = False) -> None:
        self._send_bytes(status, "text/plain; charset=utf-8", message.encode("utf-8"), close=close)

    def _send_not_found(self, close: bool = False) -> None:
        self._send_text(404, "not found\n", close=close)

    def do_POST(self) -> None:
        if self.path != "/lacuna/stats":
            self._send_not_found(close=True)
            return

        authorization = self.headers.get("Authorization", "")
        prefix = "Bearer "
        token = authorization[len(prefix) :] if authorization.startswith(prefix) else ""

        if not hmac.compare_digest(token.encode("utf-8"), self.settings.stats_token.encode("utf-8")):
            self._send_text(401, "unauthorized\n", close=True)
            return

        content_type = self.headers.get("Content-Type", "")

        if not content_type.lower().startswith("application/json"):
            self._send_text(415, "content type must be application/json\n", close=True)
            return

        content_length_header = self.headers.get("Content-Length", "")

        try:
            content_length = int(content_length_header)
        except ValueError:
            self._send_text(411, "Content-Length is invalid\n", close=True)
            return

        if content_length < 0:
            self._send_text(411, "Content-Length is invalid\n", close=True)
            return

        if content_length > self.settings.max_body_bytes:
            self._send_text(413, "request body too large\n", close=True)
            return

        body = self.rfile.read(content_length)

        if len(body) != content_length:
            self._send_text(400, "request body was shorter than Content-Length\n", close=True)
            return

        try:
            event = store.validate_event(body)
        except msgspec.ValidationError as error:
            self._send_text(422, f"{error}\n")
            return
        except msgspec.DecodeError:
            self._send_text(400, "request body is not valid JSON\n")
            return

        if store.insert_event(self.settings, event):
            print(f"stored event {event.event_id}", flush=True)

        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path == "/lacuna/healthz":
            self._send_bytes(200, "text/plain", b"ok\n")
            return

        if self.path == "/lacuna/chart.png":
            try:
                body = self.settings.chart_path.read_bytes()
            except FileNotFoundError:
                self._send_not_found()
                return
            self._send_bytes(200, "image/png", body, cache_control="no-cache")
            return

        self._send_not_found()


class StatsServer(ThreadingHTTPServer):
    daemon_threads: bool = True
    allow_reuse_address: bool = True
    settings: store.Settings

    def __init__(self, server_address: tuple[str, int], settings: store.Settings) -> None:
        self.settings = settings
        super().__init__(server_address, StatsHandler)


def main() -> None:
    settings = store.Settings.from_env()
    store.initialize_database(settings)

    render_thread = threading.Thread(
        target=render.run_render_loop,
        args=(settings,),
        daemon=True,
        name="render",
    )
    render_thread.start()

    server = StatsServer(("0.0.0.0", LISTEN_PORT), settings)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
