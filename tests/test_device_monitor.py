import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from controller.schedule import ZONE, Scheduler
from controller.service import MQTTGateway, make_server


class DeviceMonitorTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("controller.service.mqtt.Client")
        self.client = patcher.start().return_value
        self.addCleanup(patcher.stop)
        self.client.is_connected.return_value = True
        self.client.publish.return_value.rc = 0
        self.time = 0.0
        self.gateway = MQTTGateway(lambda: self.time)

    def message(self, topic, payload, retained=False):
        self.gateway.on_message(
            None,
            None,
            SimpleNamespace(
                topic="zigbee2mqtt/" + topic,
                payload=json.dumps(payload).encode(),
                retain=retained,
            ),
        )

    def test_single_read_only_stream_independent_of_browser_reads(self):
        self.gateway.poll()
        self.client.publish.assert_not_called()
        self.message("bridge/state", {"state": "online"}, retained=True)
        self.gateway.poll()
        self.client.publish.assert_called_once_with(
            "zigbee2mqtt/plant-light/get", '{"state":""}', qos=0, retain=False
        )
        for _ in range(20):
            self.gateway.snapshot()
            self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 1)
        self.message("plant-light", {"state": "OFF"})
        self.time = 2.9
        self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 1)
        self.time = 3
        self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 2)

    def test_retained_cache_does_not_imply_freshness_and_reports_expire(self):
        self.message("bridge/state", {"state": "online"})
        self.message("plant-light", {"state": "ON"}, retained=True)
        self.assertFalse(self.gateway.snapshot()["fresh"])
        initial = self.gateway.snapshot()["version"]
        self.message("plant-light", {"state": "OFF", "power": 0})
        current = self.gateway.snapshot()
        self.assertTrue(current["fresh"])
        self.assertEqual(current["report"]["state"], "OFF")
        self.assertNotEqual(initial, current["version"])
        self.time = 11.9
        self.assertTrue(self.gateway.snapshot()["fresh"])
        self.time = 12
        self.assertFalse(self.gateway.snapshot()["fresh"])
        self.assertEqual(self.gateway.snapshot()["report"], {})
        self.message("plant-light", {"state": "ON"})
        self.assertTrue(self.gateway.snapshot()["fresh"])

    def test_missing_reports_back_off_instead_of_flooding_the_plug(self):
        self.message("bridge/state", {"state": "online"})
        self.gateway.poll()
        for second in (3, 6, 9, 12, 15, 20, 26):
            self.time = second
            self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 1)
        self.time = 27
        self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 2)
        self.message("plant-light", {"state": "ON"})
        self.time = 30
        self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 3)

    def test_physical_button_changes_display_not_the_eight_hour_schedule(self):
        self.message("bridge/state", {"state": "online"})
        wall = datetime(2026, 10, 25, 8, tzinfo=ZONE)
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(
                Path(directory) / "plan.json", self.gateway, lambda: wall, lambda: True
            )
            scheduler.save(
                {"enabled": True, "on": "08:00", "off": "16:00", "revision": 0}
            )

            def commands():
                return [
                    json.loads(call.args[1])["state"]
                    for call in self.client.publish.call_args_list
                    if call.args[0] == "zigbee2mqtt/plant-light/set"
                ]

            scheduler.tick()
            self.assertEqual(commands(), ["ON"])
            wall = wall.replace(hour=12)
            self.message("plant-light", {"state": "OFF", "power": 0})
            self.assertEqual(self.gateway.snapshot()["report"]["state"], "OFF")
            for _ in range(5):
                self.gateway.poll()
                scheduler.tick()
            self.assertEqual(commands(), ["ON"])
            self.assertTrue(scheduler.snapshot()["enabled"])
            wall = wall.replace(hour=16)
            scheduler.tick()
            self.assertEqual(
                commands(), ["ON", "OFF"]
            )  # Still sends OFF even already OFF.
            wall = wall.replace(day=26, hour=8)
            scheduler.tick()
            wall = wall.replace(hour=16)
            scheduler.tick()
            self.assertEqual(commands(), ["ON", "OFF", "ON", "OFF"])
            self.assertEqual(scheduler.plan.on, "08:00")
            self.assertEqual(scheduler.plan.off, "16:00")

    def test_early_physical_on_does_not_cancel_the_next_scheduled_on(self):
        self.message("bridge/state", {"state": "online"})
        wall = datetime(2026, 10, 25, 6, tzinfo=ZONE)
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(
                Path(directory) / "plan.json", self.gateway, lambda: wall, lambda: True
            )
            scheduler.save(
                {"enabled": True, "on": "08:00", "off": "16:00", "revision": 0}
            )
            scheduler.tick()
            self.client.publish.reset_mock()
            wall = wall.replace(hour=7)
            self.message("plant-light", {"state": "ON", "power": 23})
            scheduler.tick()
            self.client.publish.assert_not_called()  # Does not force the physical change back OFF.
            wall = wall.replace(hour=8)
            scheduler.tick()
            self.client.publish.assert_called_once_with(
                "zigbee2mqtt/plant-light/set", '{"state": "ON"}', qos=0, retain=False
            )

    def test_reconnect_requires_a_new_device_report_and_queries_immediately(self):
        self.message("bridge/state", {"state": "online"})
        self.message("plant-light", {"state": "ON"})
        self.gateway.poll()
        self.message("bridge/state", {"state": "offline"})
        self.assertFalse(self.gateway.snapshot()["fresh"])
        self.message("bridge/state", {"state": "online"})
        self.gateway.poll()
        self.assertEqual(self.client.publish.call_count, 2)
        self.assertFalse(self.gateway.snapshot()["fresh"])
        self.message("plant-light", {"state": "OFF"})
        self.assertTrue(self.gateway.snapshot()["fresh"])
        self.gateway.on_disconnect(None, None, None, None, None)
        self.assertFalse(self.gateway.snapshot()["fresh"])

    def test_status_http_is_read_only_and_does_not_multiply_device_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler = Scheduler(
                Path(directory) / "plan.json",
                self.gateway,
                lambda: datetime.now(ZONE),
                lambda: True,
            )
            server = make_server(scheduler, port=0, device_status=self.gateway.snapshot)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for _ in range(3):
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", server.server_port, timeout=3
                    )
                    connection.request("GET", "/device-status")
                    response = connection.getresponse()
                    self.assertEqual(response.status, 200)
                    self.assertFalse(json.loads(response.read())["fresh"])
                    connection.close()
                self.client.publish.assert_not_called()
            finally:
                server.shutdown()
                worker.join()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
