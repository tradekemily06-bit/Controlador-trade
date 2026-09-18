
def test_reconciliation_recreates_missing_lifecycle_projection(tmp_path):
    gw, ledger, lifecycle = gateway(tmp_path, FakeAdapter())
    ledger.reserve("missing-projection")
    ledger.attach_external_id("missing-projection", "broker-reconcile")
    ledger.mark_unknown("missing-projection")
    lifecycle_path = tmp_path / "execution-lifecycle.json"
    if lifecycle_path.exists():
        lifecycle_path.unlink()

    gw.reconcile_unknown(
        "missing-projection",
        broker="fake",
        authorization=auth(),
        reconciliation_boundary=ExternalOrderReconciliationBoundary(),
    )

    assert ledger.status("missing-projection") is ExecutionLedgerStatus.RECONCILED_EXECUTED
    assert ExecutionLifecycleStore(lifecycle_path).get("missing-projection").state is ExecutionLifecycleState.ACCEPTED


