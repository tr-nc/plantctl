"""Loopback-only schedule API and background runner for the existing MQTT gateway."""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from controller.schedule import ZONE, ConflictError, Scheduler

LOG = logging.getLogger("plantctl-scheduler")


class MQTTGateway:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.ready = threading.Event()
        self.clock = clock
        self.status_lock = threading.RLock()
        self.report: dict = {}
        self.last_report: float | None = None
        self.next_query = 0.0
        self.sequence = 0
        self.instance = uuid4().hex
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
        with self.status_lock:
            self.last_report = None
            self.next_query = 0.0
        if reason_code == 0:
            client.subscribe(
                [("zigbee2mqtt/bridge/state", 1), ("zigbee2mqtt/plant-light", 0)]
            )

    def on_disconnect(self, _client, _userdata, _flags, _reason, _properties) -> None:
        self.ready.clear()

    def on_message(self, _client, _userdata, message) -> None:
        try:
            data = json.loads(message.payload)
        except (ValueError, UnicodeError):
            return
        if not isinstance(data, dict):
            return
        if message.topic == "zigbee2mqtt/bridge/state":
            if data.get("state") == "online":
                if not self.ready.is_set():
                    with self.status_lock:
                        self.next_query = 0.0
                self.ready.set()
            else:
                self.ready.clear()
                with self.status_lock:
                    self.last_report = None
        elif message.topic == "zigbee2mqtt/plant-light" and not message.retain:
            with self.status_lock:
                self.report.update(
                    {
                        key: data[key]
                        for key in ("state", "power", "voltage", "energy")
                        if key in data
                    }
                )
                if data.get("state") in ("ON", "OFF"):
                    self.last_report = self.clock()
                    self.sequence += 1

    def poll(self) -> None:
        """One read-only query stream for all clients, even with no page open."""
        with self.status_lock:
            now = self.clock()
            if not self.online or now < self.next_query:
                return
            self.next_query = now + 30
        self.client.publish(
            "zigbee2mqtt/plant-light/get", '{"state":""}', qos=0, retain=False
        )

    def snapshot(self) -> dict:
        with self.status_lock:
            fresh = (
                self.online
                and self.last_report is not None
                and self.clock() - self.last_report < 90
            )
            return {
                "gateway_online": self.online,
                "fresh": fresh,
                "report": dict(self.report) if fresh else {},
                "version": f"{self.instance}:{self.sequence}",
            }

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


def make_server(
    scheduler: Scheduler,
    port: int = 8091,
    device_status: Callable[[], dict] | None = None,
) -> ThreadingHTTPServer:
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
            if self.path == "/device-status" and device_status is not None:
                self.respond(200, device_status())
                return
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
                self.respond(503, {"error": "保存结果未确认，请重新加载核对配置。"})
            else:
                self.respond(200, result)

        def log_message(self, format: str, *args) -> None:
            LOG.info(format, *args)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def run_ticks(
    scheduler: Scheduler, stop: threading.Event, poll: Callable[[], None]
) -> None:
    while not stop.is_set():
        poll()
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
    server = make_server(scheduler, device_status=gateway.snapshot)
    stop = threading.Event()
    gateway.start()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        # Scheduling runs on the main thread: a fatal error must restart the
        # service, not silently leave a healthy-looking API with a dead worker.
        run_ticks(scheduler, stop, gateway.poll)
    finally:
        stop.set()
        server.shutdown()
        worker.join(timeout=5)
        gateway.stop()
        server.server_close()


if __name__ == "__main__":
    main()
