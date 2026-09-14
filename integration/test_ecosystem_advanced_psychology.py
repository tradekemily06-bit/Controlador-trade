from integration.ecosystem_configuration_runtime import ConfiguredEcosystemService


def test_configured_service_exposes_advanced_psychology_without_execution_authority():
    service = ConfiguredEcosystemService()
    result = service.advanced_psychology_assessment(
        {
            "operations": 9,
            "consecutive_losses": 3,
            "recent_loss_streak": 3,
            "revenge_intent": True,
            "urgency": 9,
            "risk_per_operation": 2.0,
            "baseline_risk": 1.0,
            "post_loss_risk_change": 0.5,
            "rules_broken": 2,
            "plan_adherence": 3,
        }
    )
    assert "REVENGE_TRADING" in result["patterns"]
    assert "RISK_ESCALATION" in result["patterns"]
    assert result["severity"] == "CRITICAL"
    assert result["execution_authorized"] is False
