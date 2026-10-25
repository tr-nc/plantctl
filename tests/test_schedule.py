import http.client
import json
import tempfile
import threading
import unittest
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from controller.schedule import ZONE, ConflictError, Plan, Scheduler
from controller.service import MQTTGateway, make_server


class FakeGateway:
    online = True
    accepts = True

    def __init__(self):
        self.commands = []

    def set_state(self, state):
        if self.accepts:
            self.commands.append(state)
        return self.accepts


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "schedule.json"
        self.gateway = FakeGateway()
        self.time = datetime(2026, 10, 25, 9, tzinfo=ZONE)
        self.synced = True
        self.scheduler = self.new_scheduler()

    def new_scheduler(self):
        return Scheduler(
            self.path, self.gateway, lambda: self.time, lambda: self.synced
        )

    def save(self, **changes):
        value = asdict(self.scheduler.plan)
        value.update(changes)
        return self.scheduler.save(value)

    def test_default_disabled_and_enable_is_durable(self):
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, [])
        self.assertFalse(self.scheduler.snapshot()["enabled"])
        self.save(enabled=True)
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["ON"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        restarted = self.new_scheduler()
        self.assertTrue(restarted.snapshot()["enabled"])
        self.time = self.time.replace(hour=23)
        restarted.tick()
        self.assertEqual(self.gateway.commands, ["ON", "OFF"])

    def test_daytime_edges_and_no_repeated_dispatch_between_edges(self):
        self.time = self.time.replace(hour=7, minute=59, second=59)
        self.save(enabled=True)
        self.scheduler.tick()
        self.time = self.time.replace(hour=8, minute=0, second=0)
        self.scheduler.tick()
        # An external physical switch can still change state. Do not dispatch
        # repeatedly within one window; the dashboard manual API is gated.
        self.time = self.time.replace(hour=12)
        self.scheduler.tick()
        self.save()  # Saving unchanged configuration is not an activation event either.
        self.scheduler.tick()
        self.time = self.time.replace(hour=22)
        self.scheduler.tick()
        self.time = self.time.replace(day=26, hour=8)
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["OFF", "ON", "OFF", "ON"])

    def test_overnight_and_next_occurrence(self):
        self.time = self.time.replace(hour=23)
        result = self.save(enabled=True, on="20:00", off="06:00")
        self.assertEqual(
            result["next"], {"at": "2026-10-26T06:00:00+08:00", "state": "OFF"}
        )
        self.scheduler.tick()
        self.time = self.time.replace(day=26, hour=0)
        self.scheduler.tick()
        self.time = self.time.replace(hour=6)
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["ON", "OFF"])

    def test_disabled_does_not_switch_or_retry(self):
        self.save(enabled=True)
        self.scheduler.tick()
        self.save(enabled=False)
        self.time = self.time.replace(hour=23)
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["ON"])
        self.assertIsNone(self.scheduler.snapshot()["next"])

    def test_offline_catches_up_only_current_window(self):
        self.gateway.online = False
        self.save(enabled=True)
        self.scheduler.tick()
        self.time = self.time.replace(day=27, hour=23)
        self.scheduler.tick()
        self.gateway.online = True
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["OFF"])
        self.gateway.online = False
        self.scheduler.tick()
        self.gateway.online = True
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["OFF"])

    def test_waits_for_clock_and_retries_unsubmitted_commands(self):
        self.synced = False
        self.save(enabled=True)
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, [])
        self.synced = True
        self.gateway.accepts = False
        self.scheduler.tick()
        self.assertIsNone(self.scheduler.snapshot()["last_action"])
        self.gateway.accepts = True
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["ON"])
        self.assertEqual(self.scheduler.snapshot()["last_action"]["result"], "sent")

    def test_edit_reconciles_and_rejects_stale_clients(self):
        stale = asdict(self.scheduler.plan)
        self.save(enabled=True)
        self.scheduler.tick()
        self.save(on="12:00")
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["ON", "OFF"])
        with self.assertRaises(ConflictError):
            self.scheduler.save(stale)
        self.assertEqual(self.scheduler.plan.on, "12:00")

    def test_invalid_input_and_write_failure_preserve_plan(self):
        for update in (
            {"on": "24:00"},
            {"off": "08:00"},
            {"enabled": 1},
            {"revision": True},
            {"on": "8:00"},
        ):
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.save(**update)
        with (
            patch("controller.schedule.os.replace", side_effect=OSError("disk full")),
            self.assertRaises(OSError),
        ):
            self.save(enabled=True)
        self.assertEqual(self.scheduler.plan, Plan())
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, [])
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_manual_control_requires_persisted_manual_mode(self):
        self.scheduler.manual({"state": "ON"})
        self.assertEqual(self.gateway.commands, ["ON"])
        self.save(enabled=True)
        for service in (self.scheduler, self.new_scheduler()):
            with self.assertRaises(ConflictError):
                service.manual({"state": "OFF"})
        self.assertEqual(self.gateway.commands, ["ON"])
        self.save(enabled=False)
        self.scheduler.manual({"state": "OFF"})
        self.assertEqual(self.gateway.commands, ["ON", "OFF"])
        self.gateway.online = False
        with self.assertRaises(ConnectionError):
            self.scheduler.manual({"state": "ON"})
        with self.assertRaises(ValueError):
            self.scheduler.manual({"state": "TOGGLE"})

    def test_corrupt_file_fails_closed(self):
        self.path.write_text('{"enabled":true}')
        with self.assertRaises(ValueError):
            self.new_scheduler()

    def test_loopback_http_api_validation_persistence_and_conflict(self):
        server = make_server(self.scheduler, port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.server_close)
        self.addCleanup(worker.join)
        self.addCleanup(server.shutdown)

        def request(method, body=None, origin=True, path="/schedule"):
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_port, timeout=3
            )
            headers = {"Content-Type": "application/json", "Host": "192.168.50.102"}
            if origin:
                headers["Origin"] = "http://192.168.50.102"
            connection.request(
                method, path, json.dumps(body) if body else None, headers
            )
            response = connection.getresponse()
            result = (response.status, json.loads(response.read()))
            connection.close()
            return result

        status, data = request("GET")
        self.assertEqual(status, 200)
        self.assertFalse(data["enabled"])
        value = {"enabled": True, "on": "20:00", "off": "06:00", "revision": 0}
        self.assertEqual(request("PUT", value, origin=False)[0], 403)
        self.assertEqual(request("PUT", {**value, "on": "06:00"})[0], 400)
        self.assertEqual(request("PUT", value)[0], 200)
        self.assertEqual(request("PUT", value)[0], 409)
        self.assertTrue(self.new_scheduler().snapshot()["enabled"])
        # API save alone does not dispatch: the independent runner owns execution.
        self.assertEqual(self.gateway.commands, [])
        self.scheduler.tick()
        self.assertEqual(self.gateway.commands, ["OFF"])
        self.assertEqual(request("POST", {"state": "ON"}, path="/manual")[0], 409)
        self.assertEqual(self.gateway.commands, ["OFF"])
        self.assertEqual(
            request("POST", {"state": "ON"}, origin=False, path="/manual")[0], 403
        )
        self.assertEqual(
            request("PUT", {**value, "enabled": False, "revision": 1})[0], 200
        )
        self.assertEqual(request("POST", {"state": "ON"}, path="/manual")[0], 200)
        self.assertEqual(self.gateway.commands, ["OFF", "ON"])
        self.assertEqual(request("POST", {"state": "TOGGLE"}, path="/manual")[0], 400)

    def test_mqtt_never_retains_or_queues_commands_and_checks_bridge(self):
        with patch("controller.service.mqtt.Client") as client_class:
            client = client_class.return_value
            client.is_connected.return_value = True
            client.publish.return_value.rc = 0
            adapter = MQTTGateway()
            self.assertFalse(adapter.set_state("ON"))
            adapter.ready.set()
            self.assertTrue(adapter.set_state("OFF"))
            client.publish.assert_called_once_with(
                "zigbee2mqtt/plant-light/set", '{"state": "OFF"}', qos=0, retain=False
            )
            adapter.on_disconnect(None, None, None, None, None)
            self.assertFalse(adapter.set_state("ON"))


if __name__ == "__main__":
    unittest.main()
