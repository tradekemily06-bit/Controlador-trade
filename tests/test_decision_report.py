from __future__ import annotations

import json
import unittest

from analysis.decision_record import DecisionRecord
from analysis.decision_report import build_decision_report, export_decision_report
from core.models import AnalysisResult, Signal


class DecisionReportTests(unittest.TestCase):
    def test_report_preserves_decision_record_semantics(self):
        result = AnalysisResult(
            signal=Signal.AGUARDAR,
            score=42.0,
            confirmed=False,
            reason="Dados insuficientes",
            symbol="EURUSD",
            timeframe="5m",
        )
        record = DecisionRecord.from_analysis(result)
        report = build_decision_report([record], {"total": 1})
        self.assertEqual(report["record_count"], 1)
        self.assertEqual(report["records"][0]["decision_id"], record.decision_id)
        self.assertEqual(report["source_model"], "DecisionRecord")
        self.assertFalse(report["legacy_operation_memory_conversion"])
        self.assertFalse(report["execution_authorized"])
        exported = json.loads(export_decision_report(report))
        self.assertEqual(exported["report_type"], "STANDALONE_DECISION_REPORT")

    def test_report_rejects_unrelated_memory_model(self):
        with self.assertRaises(TypeError):
            build_decision_report([{"signal": "COMPRA"}], {})


if __name__ == "__main__":
    unittest.main()
