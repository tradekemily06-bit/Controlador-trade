from __future__ import annotations

from execution.mt5_demo_first_order import build_demo_request, main


def test_example_builds_request_without_direct_dispatch(capsys):
    request = build_demo_request()

    assert request.mode.value == "DEMO"
    assert request.request_id == "mt5-demo-first-order"

    main()
    output = capsys.readouterr().out
    assert "DIRECT_BROKER_DISPATCH=False" in output
    assert "orchestrated DEMO flow" in output
