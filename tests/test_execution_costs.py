from __future__ import annotations

import unittest

from analysis.execution_costs import TradeCostBreakdown, calculate_net_trade_return


class ExecutionCostTests(unittest.TestCase):
    def costs(self, **overrides):
        values = dict(
            spread=1.0, commission=0.5, slippage=0.25,
            swap=0.0, financing=0.0, conversion=0.0,
            currency="USD", source_id="broker-statement-2026-11",
            verified_at="2026-11-28T12:00:00Z",
        )
        values.update(overrides)
        return TradeCostBreakdown(**values)

    def test_net_return_subtracts_all_explicit_costs(self):
        result = calculate_net_trade_return(
            gross_profit_loss=10.0, capital_at_risk=100.0, costs=self.costs()
        )
        self.assertAlmostEqual(result["total_cost"], 1.75)
        self.assertAlmostEqual(result["net_profit_loss"], 8.25)
        self.assertAlmostEqual(result["net_return"], 0.0825)
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["cost_provenance"]["unknown_costs_defaulted_to_zero"])

    def test_unknown_cost_is_not_silently_zero_filled(self):
        with self.assertRaisesRegex(ValueError, "unknown costs cannot be zero-filled"):
            calculate_net_trade_return(
                gross_profit_loss=10.0, capital_at_risk=100.0,
                costs=self.costs(commission=None),
            )

    def test_negative_cost_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            self.costs(spread=-0.1).validated_amounts()

    def test_cost_source_and_timezone_required(self):
        with self.assertRaisesRegex(ValueError, "source_id is required"):
            self.costs(source_id="").validated_amounts()
        with self.assertRaisesRegex(ValueError, "include a timezone"):
            self.costs(verified_at="2026-11-28T12:00:00").validated_amounts()

    def test_invalid_capital_rejected(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            calculate_net_trade_return(
                gross_profit_loss=1.0, capital_at_risk=0.0, costs=self.costs()
            )


if __name__ == "__main__":
    unittest.main()
