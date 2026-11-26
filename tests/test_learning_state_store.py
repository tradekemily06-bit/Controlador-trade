from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.ecosystem_state_store import EcosystemStateStore
from core.learning_state_store import LearningStateStore
from integration.ecosystem_service import EcosystemService


class LearningStateStoreTests(unittest.TestCase):
    def test_study_records_survive_service_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "ecosystem-state.sqlite3"

            first = EcosystemService(
                learning_state_store=LearningStateStore(EcosystemStateStore(database))
            )
            first.add_learning_resource({
                "resource_id": "resource-1",
                "title": "Market structure",
                "content_type": "ARTICLE",
                "source_url": "https://example.org/market-structure",
                "tags": ["price action", "structure"],
            })
            source = first.learning_sources["resource-1"]
            source = first.validate_learning_source(
                source, content_verified=True, security_checked=True
            )
            first.admit_learning_knowledge(source, knowledge_validated=True)
            first.add_learning_observation({
                "resource_id": "resource-1",
                "statement": "A validated observation",
                "concepts": ["structure"],
                "confidence": 0.9,
                "validated": True,
            })
            first.add_learning_activity({
                "activity_id": "activity-1",
                "prompt": "Identify the market structure",
                "expected_concepts": ["structure"],
            })
            first.add_learning_attempt({
                "activity_id": "activity-1",
                "answer": "Higher highs and higher lows",
                "correct": True,
                "feedback": "Correct",
            })

            restarted = EcosystemService(
                learning_state_store=LearningStateStore(EcosystemStateStore(database))
            )
            summary = restarted.learning_summary()
            self.assertEqual(len(summary["resources"]), 1)
            self.assertEqual(len(summary["learning_sources"]), 1)
            self.assertEqual(summary["learning_sources"][0]["status"], "VALIDATED")
            self.assertTrue(summary["observations"][0]["validated"])
            self.assertEqual(summary["activities"][0]["activity_id"], "activity-1")
            self.assertEqual(summary["attempts"][0]["correct"], True)
            self.assertFalse(summary["learning_authorizes_trading"])

    def test_invalid_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            state = EcosystemStateStore(Path(directory) / "state.sqlite3")
            state.save("learning_state", {"schema_version": 999})
            with self.assertRaises(ValueError):
                LearningStateStore(state).load()


if __name__ == "__main__":
    unittest.main()
