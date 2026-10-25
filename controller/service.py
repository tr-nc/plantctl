"""Loopback-only schedule API and background runner for the existing MQTT gateway."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from controller.schedule import ZONE, ConflictError, Scheduler

LOG = logging.getLogger("plantctl-scheduler")


class MQTTGateway:
    def __init__(self) -> None:
        self.ready = threading.Event()
        self.client = mqtt.Client(
            CallbackAPIVersion.VERSION2, client_id="plantctl-scheduler"
        )
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=15)

    @property
    def online(self) -> bool:
        return self.ready.is_set() and self.client.is_connected()

    def on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        self.ready.clear()
        if reason_code == 0:
            client.subscribe("zigbee2mqtt/bridge/state", qos=1)

    def on_disconnect(self, _client, _userdata, _flags, _reason, _properties) -> None:
        self.ready.clear()

    def on_message(self, _client, _userdata, message) -> None:
        try:
            data = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        if isinstance(data, dict) and data.get("state") == "online":
            self.ready.set()
        else:
            self.ready.clear()

    def set_state(self, state: str) -> bool:
        if not self.online:
            return False
        # QoS 0 + non-retained: never queue a stale switch command for reconnect.
        result = self.client.publish(
            "zigbee2mqtt/plant-light/set",
            json.dumps({"state": state}),
            qos=0,
            retain=False,
        )
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            LOG.info(
                "Scheduled state submitted: %s (device execution not confirmed)", state
            )
            return True
        return False

    def start(self) -> None:
        self.client.connect_async("127.0.0.1", 1883, keepalive=30)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


def make_server(scheduler: Scheduler, port: int = 8091) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(5)

        def respond(self, status: int, value: dict) -> None:
            body = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/schedule":
                self.respond(404, {"error": "Not found"})
                return
            self.respond(200, scheduler.snapshot())

        def do_PUT(self) -> None:
            if self.path != "/schedule":
                self.respond(404, {"error": "Not found"})
                return
            # LAN authentication is intentional; reject cross-origin browser writes.
            if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
                self.respond(403, {"error": "仅允许同源修改。"})
                return
            if self.headers.get("Content-Type") != "application/json":
                self.respond(415, {"error": "需要 application/json。"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1024:
                    raise ValueError("请求大小无效。")
                value = json.loads(self.rfile.read(size))
                result = scheduler.save(value)
            except ConflictError as error:
                self.respond(409, {"error": str(error)})
            except (ValueError, UnicodeError):
                self.respond(400, {"error": "配置无效：请使用不同的 HH:MM 开关时间。"})
            except OSError:
                LOG.exception("Failed to persist schedule")
                self.respond(
                    503, {"error": "保存结果未确认，请重新加载核对配置。"}
                )
            else:
                self.respond(200, result)

        def log_message(self, format: str, *args) -> None:
            LOG.info(format, *args)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def run_ticks(scheduler: Scheduler, stop: threading.Event) -> None:
    while not stop.is_set():
        scheduler.tick()
        stop.wait(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    gateway = MQTTGateway()
    scheduler = Scheduler(
        Path("/var/lib/plantctl-scheduler/schedule.json"),
        gateway,
        lambda: datetime.now(ZONE),
        lambda: Path("/run/systemd/timesync/synchronized").exists(),
    )
    server = make_server(scheduler)
    stop = threading.Event()
    gateway.start()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        # Scheduling runs on the main thread: a fatal error must restart the
        # service, not silently leave a healthy-looking API with a dead worker.
        run_ticks(scheduler, stop)
    finally:
        stop.set()
        server.shutdown()
        worker.join(timeout=5)
        gateway.stop()
        server.server_close()


if __name__ == "__main__":
    main()
