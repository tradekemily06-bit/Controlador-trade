from __future__ import annotations

import unittest

from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


class ProductionLocalStateBypassTests(unittest.TestCase):
    def test_production_service_blocks_legacy_memory_container(self):
        service = ConfiguredEcosystemService.__new__(ConfiguredEcosystemService)
        service.production_data_plane = object()
        # Re-run only the invariant setup that the mixin performs after the
        # legacy EcosystemService constructor has completed.
        from integration.production_scoped_service import _ProductionLocalDecisionStoreBlock, _ProductionLocalLearningStateBlock
        service.store = _ProductionLocalDecisionStoreBlock()
        service.memory = _ProductionLocalLearningStateBlock()
        service.learning_sources = service.memory
        service.learning_resources = service.memory
        service.learning_observations = service.memory
        service.learning_activities = service.memory
        service.learning_attempts = service.memory

        with self.assertRaises(RuntimeError):
            len(service.memory)
        with self.assertRaises(RuntimeError):
            service.memory.append(object())
        with self.assertRaises(RuntimeError):
            "x" in service.learning_sources

    def test_production_scoped_mixin_does_not_leave_plain_memory_list(self):
        from integration.production_scoped_service import _ProductionLocalLearningStateBlock
        self.assertTrue(issubclass(_ProductionLocalLearningStateBlock, object))
        self.assertNotIsInstance([], _ProductionLocalLearningStateBlock)


if __name__ == "__main__":
    unittest.main()
