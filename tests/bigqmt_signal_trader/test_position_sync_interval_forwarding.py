# coding: utf-8
"""position_sync_interval_seconds must reach the app when configured.

Mirrors the order_settle_timeout_seconds chain (#396): a module global
(default None = the app default, every tick), read from the redis config,
forwarded into configure() only when named. The factory then hands it to
SignalTradingApp, and a no-Redis deployment gets the Noop sink that skips
the sync entirely.
"""
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))

import bigqmt_signal_trader_redis_rpc_runtime as runtime
from bigqmt_signal_trader.adapter_factory import NoopPositionSyncSink, build_app


class PositionSyncIntervalForwardingTest(unittest.TestCase):
    def setUp(self):
        self._saved = {
            "POSITION_SYNC_INTERVAL_SECONDS": runtime.POSITION_SYNC_INTERVAL_SECONDS,
            "configure": runtime.configure,
            "set_account_id": runtime.set_account_id,
        }
        self._captured = {}
        runtime.configure = lambda **kwargs: self._captured.update(kwargs)
        runtime.set_account_id = lambda account_id: None

    def tearDown(self):
        for key, value in self._saved.items():
            setattr(runtime, key, value)

    def _configured(self):
        runtime._apply_config("TESTACCOUNT")
        return self._captured

    def test_absent_when_not_configured(self):
        runtime.POSITION_SYNC_INTERVAL_SECONDS = None

        self.assertNotIn("position_sync_interval_seconds", self._configured())

    def test_forwarded_when_configured(self):
        runtime.POSITION_SYNC_INTERVAL_SECONDS = 2

        self.assertEqual(self._configured().get("position_sync_interval_seconds"), 2.0)

    def test_configure_runtime_redis_reads_the_key(self):
        runtime.POSITION_SYNC_INTERVAL_SECONDS = None

        runtime.configure_runtime_redis({"position_sync_interval_seconds": 1.5})

        self.assertEqual(runtime.POSITION_SYNC_INTERVAL_SECONDS, 1.5)


class BuildAppWiringTest(unittest.TestCase):
    def test_factory_hands_the_interval_to_the_app(self):
        app = build_app(config={"position_sync_interval_seconds": "3"})

        self.assertEqual(app.position_sync_interval_seconds, 3.0)

    def test_factory_default_is_every_tick(self):
        self.assertEqual(build_app(config={}).position_sync_interval_seconds, 0.0)

    def test_no_redis_deployment_gets_a_sink_the_app_can_skip(self):
        app = build_app(config={"mode": "dryrun", "position_sync_type": ""})

        self.assertIsInstance(app.position_sync_sink, NoopPositionSyncSink)
        self.assertTrue(getattr(app.position_sync_sink, "is_noop", False))


if __name__ == "__main__":
    unittest.main()
