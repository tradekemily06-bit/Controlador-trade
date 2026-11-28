from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.p122_broker_market_data import BrokerMarketDataSnapshot
from data.models import Candle
from analysis.tenant_market_snapshot_store import TenantMarketSnapshotStore
from security.tenant_context import TenantContext


def snapshot(close: float = 1.2) -> BrokerMarketDataSnapshot:
    start = datetime(2026, 11, 28, 12, 0, tzinfo=timezone.utc)
    candles = (
        Candle(start, 1.0, 1.3, 0.9, close, 100.0),
        Candle(start + timedelta(minutes=5), close, 1.4, 1.0, 1.25, 120.0),
    )
    return BrokerMarketDataSnapshot(
        symbol="eurusd", timeframe="5m", candles=candles,
        source="test-provider", received_at=start + timedelta(minutes=6),
    )


class TenantMarketSnapshotStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "snapshots.sqlite3"
        self.store = TenantMarketSnapshotStore(self.path)
        self.owner = TenantContext("tenant-a", "subject-a")
        self.other = TenantContext("tenant-b", "subject-a")

    def tearDown(self):
        self.temp.cleanup()

    def test_records_immutable_snapshot_and_verifies_checksum_on_read(self):
        result = self.store.record(
            self.owner, snapshot_id="snap-1", source_id="ctrader:account-1",
            snapshot=snapshot(),
        )
        self.assertEqual(result["status"], "RECORDED")
        loaded = self.store.get(self.owner, "snap-1")
        self.assertEqual(loaded["payload_sha256"], result["payload_sha256"])
        self.assertEqual(loaded["candle_count"], 2)
        self.assertEqual(
            loaded["provenance_status"],
            "PROVIDER_BOUNDARY_ASSERTED_NOT_INDEPENDENTLY_VERIFIED",
        )

    def test_identical_retry_is_idempotent_but_changed_payload_is_rejected(self):
        first = self.store.record(
            self.owner, snapshot_id="snap-1", source_id="mt5:account-1",
            snapshot=snapshot(),
        )
        retry = self.store.record(
            self.owner, snapshot_id="snap-1", source_id="mt5:account-1",
            snapshot=snapshot(),
        )
        self.assertEqual(retry["status"], "ALREADY_RECORDED")
        self.assertEqual(first["payload_sha256"], retry["payload_sha256"])
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.store.record(
                self.owner, snapshot_id="snap-1", source_id="mt5:account-1",
                snapshot=snapshot(close=1.21),
            )

    def test_snapshot_is_invisible_to_other_tenant_and_subject(self):
        self.store.record(
            self.owner, snapshot_id="private-snapshot", source_id="provider:account",
            snapshot=snapshot(),
        )
        self.assertIsNone(self.store.get(self.other, "private-snapshot"))
        self.assertIsNone(self.store.get(TenantContext("tenant-a", "subject-b"), "private-snapshot"))

    def test_non_chronological_candles_are_rejected(self):
        valid = snapshot()
        invalid = BrokerMarketDataSnapshot(
            symbol=valid.symbol, timeframe=valid.timeframe,
            candles=tuple(reversed(valid.candles)), source=valid.source,
            received_at=valid.received_at,
        )
        with self.assertRaisesRegex(ValueError, "chronological"):
            self.store.record(
                self.owner, snapshot_id="bad", source_id="provider:account",
                snapshot=invalid,
            )

    def test_checksum_tampering_is_detected(self):
        self.store.record(
            self.owner, snapshot_id="snap-1", source_id="provider:account",
            snapshot=snapshot(),
        )
        with sqlite3.connect(self.path) as db:
            db.execute(
                "UPDATE tenant_market_snapshots SET payload_json=? WHERE snapshot_id=?",
                ('{"tampered":true}', "snap-1"),
            )
        with self.assertRaisesRegex(RuntimeError, "checksum"):
            self.store.get(self.owner, "snap-1")


if __name__ == "__main__":
    unittest.main()
