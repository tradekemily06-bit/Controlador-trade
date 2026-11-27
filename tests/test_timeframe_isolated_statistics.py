from __future__ import annotations

import unittest

from analysis.decision_record import DecisionRecord
from analysis.statistics import summarize_context_groups


def record(
    decision_id: str,
    *,
    timeframe: str,
    signal: str = "COMPRA",
    outcome: str = "WIN",
    symbol: str = "EURUSD",
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        created_at="2026-11-27T12:00:00+00:00",
        symbol=symbol,
        timeframe=timeframe,
        signal=signal,
        score=80.0,
        confirmed=True,
        reason="test",
        outcome=outcome,
    )


class TimeframeIsolatedStatisticsTests(unittest.TestCase):
    def test_m1_never_borrows_m5_outcomes(self):
        groups = summarize_context_groups([
            record("m1-loss", timeframe="1m", outcome="LOSS"),
            record("m5-win-1", timeframe="5m", outcome="WIN"),
            record("m5-win-2", timeframe="5m", outcome="WIN"),
            record("m5-win-3", timeframe="5m", outcome="WIN"),
        ])

        m1 = groups["EURUSD|1m|COMPRA"]
        m5 = groups["EURUSD|5m|COMPRA"]
        self.assertEqual(m1["descriptive_outcomes"]["closed"], 1)
        self.assertEqual(m1["descriptive_outcomes"]["win_rate"], 0.0)
        self.assertEqual(m5["descriptive_outcomes"]["closed"], 3)
        self.assertEqual(m5["descriptive_outcomes"]["win_rate"], 100.0)
        self.assertIsNone(m1["probability_of_profit"])
        self.assertEqual(m1["calibration_status"], "NOT_CALIBRATED")

    def test_symbol_and_direction_are_also_isolated(self):
        groups = summarize_context_groups([
            record("eurusd-buy", timeframe="1m", signal="COMPRA", outcome="LOSS"),
            record("eurusd-sell", timeframe="1m", signal="VENDA", outcome="WIN"),
            record("gbpusd-buy", timeframe="1m", signal="COMPRA", outcome="WIN", symbol="GBPUSD"),
        ])
        self.assertEqual(set(groups), {
            "EURUSD|1m|COMPRA",
            "EURUSD|1m|VENDA",
            "GBPUSD|1m|COMPRA",
        })
        self.assertEqual(
            groups["EURUSD|1m|COMPRA"]["descriptive_outcomes"]["win_rate"],
            0.0,
        )
        self.assertEqual(
            groups["EURUSD|1m|VENDA"]["descriptive_outcomes"]["win_rate"],
            100.0,
        )

    def test_no_cross_timeframe_aggregation_is_returned(self):
        groups = summarize_context_groups([
            record("m1", timeframe="1m", outcome="LOSS"),
            record("m5", timeframe="5m", outcome="WIN"),
        ])
        self.assertEqual(len(groups), 2)
        self.assertNotIn("all_timeframes", groups)


if __name__ == "__main__":
    unittest.main()
