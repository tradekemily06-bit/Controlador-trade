from __future__ import annotations

import unittest

from analysis.probability_calibration import (
    ProbabilityForecast,
    evaluate_probability_calibration,
)


def forecast(
    forecast_id: str,
    *,
    timeframe: str = "1m",
    symbol: str = "EURUSD",
    direction: str = "COMPRA",
    probability: float = 0.7,
    outcome: bool = True,
    provenance: str = "REAL_MARKET_DATA",
    out_of_sample: bool = True,
    model_version: str = "v1",
) -> ProbabilityForecast:
    return ProbabilityForecast(
        forecast_id=forecast_id,
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        model_version=model_version,
        probability=probability,
        outcome=outcome,
        forecast_at="2026-11-27T10:00:00+00:00",
        resolved_at="2026-11-27T10:01:00+00:00",
        provenance=provenance,
        out_of_sample=out_of_sample,
    )


class ProbabilityCalibrationTests(unittest.TestCase):
    def test_m1_does_not_borrow_m5_samples(self):
        records = [
            forecast("m1", timeframe="1m", outcome=False),
            forecast("m5-1", timeframe="5m"),
            forecast("m5-2", timeframe="5m"),
            forecast("m5-3", timeframe="5m"),
        ]
        result = evaluate_probability_calibration(records, minimum_sample_count=3)
        self.assertEqual(result["EURUSD|1m|COMPRA|v1"]["sample_count"], 1)
        self.assertEqual(
            result["EURUSD|1m|COMPRA|v1"]["calibration_status"],
            "INSUFFICIENT_SAMPLE",
        )
        self.assertEqual(
            result["EURUSD|5m|COMPRA|v1"]["calibration_status"],
            "EVALUATED_REQUIRES_REVIEW",
        )
        self.assertIsNone(result["EURUSD|5m|COMPRA|v1"]["probability_of_profit"])

    def test_platform_timeframe_aliases_share_only_the_same_canonical_timeframe(self):
        records = [
            forecast("compact", timeframe="1m"),
            forecast("platform", timeframe="M1"),
            forecast("m5", timeframe="M5"),
        ]
        result = evaluate_probability_calibration(records, minimum_sample_count=2)
        self.assertEqual(result["EURUSD|1m|COMPRA|v1"]["sample_count"], 2)
        self.assertEqual(result["EURUSD|1m|COMPRA|v1"]["calibration_status"], "EVALUATED_REQUIRES_REVIEW")
        self.assertEqual(result["EURUSD|5m|COMPRA|v1"]["sample_count"], 1)
        self.assertEqual(result["EURUSD|5m|COMPRA|v1"]["calibration_status"], "INSUFFICIENT_SAMPLE")

    def test_unsupported_timeframe_and_direction_are_rejected(self):
        records = [
            forecast("bad-timeframe", timeframe="M60"),
            forecast("bad-direction", direction="AGUARDAR"),
        ]
        self.assertEqual(evaluate_probability_calibration(records), {})

    def test_minimum_sample_count_must_be_an_integer(self):
        with self.assertRaises(ValueError):
            evaluate_probability_calibration([], minimum_sample_count=2.5)

    def test_symbol_direction_and_model_version_are_isolated(self):
        records = [
            forecast("a", symbol="EURUSD"),
            forecast("b", symbol="GBPUSD"),
            forecast("c", direction="VENDA"),
            forecast("d", model_version="v2"),
        ]
        result = evaluate_probability_calibration(records, minimum_sample_count=2)
        self.assertEqual(len(result), 4)
        self.assertTrue(all(x["sample_count"] == 1 for x in result.values()))

    def test_simulated_and_in_sample_records_are_rejected(self):
        result = evaluate_probability_calibration([
            forecast("sim", provenance="SIMULATED_DEMO"),
            forecast("train", out_of_sample=False),
        ])
        self.assertEqual(result, {})

    def test_forecast_must_precede_resolution_and_probability_be_valid(self):
        late = ProbabilityForecast(
            **{
                **forecast("late").__dict__,
                "forecast_at": "2026-11-27T10:02:00+00:00",
            }
        )
        invalid = ProbabilityForecast(
            **{**forecast("invalid").__dict__, "probability": 1.5}
        )
        self.assertEqual(evaluate_probability_calibration([late, invalid]), {})

    def test_duplicate_forecast_ids_are_not_double_counted(self):
        item = forecast("duplicate")
        result = evaluate_probability_calibration([item, item])
        self.assertEqual(result["EURUSD|1m|COMPRA|v1"]["sample_count"], 1)
        self.assertEqual(result["EURUSD|1m|COMPRA|v1"]["rejected_records"], 1)

    def test_reliability_diagnostics_include_uncertainty(self):
        records = [
            forecast(f"f-{i}", probability=0.7, outcome=(i < 70))
            for i in range(100)
        ]
        result = evaluate_probability_calibration(records, minimum_sample_count=100)
        item = result["EURUSD|1m|COMPRA|v1"]
        self.assertEqual(item["calibration_status"], "EVALUATED_REQUIRES_REVIEW")
        self.assertAlmostEqual(item["brier_score"], 0.21)
        self.assertTrue(item["reliability_bins"])
        self.assertEqual(len(item["reliability_bins"][0]["observed_rate_95ci"]), 2)
        self.assertIsNone(item["probability_of_profit"])


if __name__ == "__main__":
    unittest.main()
