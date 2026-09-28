from datetime import datetime, timezone

import pytest

from core.p46_automation_lifecycle import AutomationLifecycleState
from core.p47_automation_closure import AutomationClosure
from execution.icmarkets_mt5_demo_outcome import MT5OutcomeEvidence
from integration.mt5_post_demo_learning import MT5PostDemoLearningBridge


class FakePostDemo:
    def __init__(self):
        self.kwargs = None

    def process(self, **kwargs):
        self.kwargs = kwargs
        return "p139-result"


def evidence(cycle_id="cycle-1"):
    return MT5OutcomeEvidence(
        decision_id="decision-1",
        cycle_id=cycle_id,
        request_id="request-1",
        position_id="123",
        close_external_id="900",
        deal_ids=("602",),
        financial_result=10.3,
        outcome="WIN",
        observed_at=datetime.now(timezone.utc),
    )


def closure(cycle_id="cycle-1"):
    return AutomationClosure(
        cycle_id=cycle_id,
        terminal_state=AutomationLifecycleState.COMPLETED,
        closed_at=datetime.now(timezone.utc),
    )


def test_verified_mt5_evidence_is_forwarded_to_p139():
    post_demo = FakePostDemo()
    bridge = MT5PostDemoLearningBridge(post_demo=post_demo)

    result = bridge.process(
        evidence=evidence(),
        closure=closure(),
        analysis=object(),
        market_context=object(),
        note_id="note-1",
        what_happened="fechou",
        why_assessment="teste",
    )

    assert result == "p139-result"
    assert post_demo.kwargs["outcome"] == "WIN"
    assert post_demo.kwargs["financial_result"] == 10.3
    assert post_demo.kwargs["external_observation"].cycle_id == "cycle-1"
    assert "MT5 position_id=123" in post_demo.kwargs["evidence"]


def test_bridge_rejects_cycle_mismatch():
    bridge = MT5PostDemoLearningBridge(post_demo=FakePostDemo())

    with pytest.raises(ValueError, match="cycle_id"):
        bridge.process(
            evidence=evidence("cycle-a"),
            closure=closure("cycle-b"),
            analysis=object(),
            market_context=object(),
            note_id="note-1",
            what_happened="fechou",
            why_assessment="teste",
        )
