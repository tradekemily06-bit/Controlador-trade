def test_reconciliation_repairs_partial_unknown_lifecycle_projection(tmp_path):
    gw, ledger, lifecycle = gateway(tmp_path, FakeAdapter())
    ledger.reserve("projection-mismatch")
    ledger.attach_external_id("projection-mismatch", "broker-reconcile")
    ledger.mark_unknown("projection-mismatch")
    lifecycle.put(
        ExecutionLifecycleRecord(
            "projection-mismatch",
            ExecutionLifecycleState.PENDING,
            datetime.now(timezone.utc),
        )
    )
    gw.reconcile_unknown(
        "projection-mismatch",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )
    assert ledger.status("projection-mismatch") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert lifecycle.get("projection-mismatch").state is ExecutionLifecycleState.ACCEPTED


def test_repair_lifecycle_projection_can_recreate_missing_projection(tmp_path):