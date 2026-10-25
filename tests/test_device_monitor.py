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
        self.time = 30
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
        self.time = 89
        self.assertTrue(self.gateway.snapshot()["fresh"])
        self.time = 90
        self.assertFalse(self.gateway.snapshot()["fresh"])
        self.assertEqual(self.gateway.snapshot()["report"], {})
        self.message("plant-light", {"state": "ON"})
        self.assertTrue(self.gateway.snapshot()["fresh"])

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
