from __future__ import annotations

import unittest

from core.unified_intelligence import ApplicationArea
from integration.standalone_application_factory import build_standalone_application


class FakeService:
    senior_context = None

    def system_status(self):
        return {"state": "READY"}

    def risk_status(self):
        return {"allowed": False}

    def operational_observability(self):
        return {"execution": {"allowed": False}}

    def notification_summary(self):
        return {"items": []}

    def learning_summary(self):
        return {"execution_allowed": False}

    def learning_sources_view(self):
        return [{"source_id": "source-1"}]

    def learning_resources_view(self):
        return [{"resource_id": "resource-1"}]

    def learning_observations_view(self):
        return [{"resource_id": "resource-1"}]

    def learning_activities_view(self):
        return [{"activity_id": "activity-1"}]

    def news_status(self, limit=10):
        return {"provider": "UNCONFIGURED", "live": False, "items": []}

    def statistics(self):
        return {"total": 0}

    def decision_report(self, limit=1000):
        return {
            "report_type": "STANDALONE_DECISION_REPORT",
            "record_count": 0,
            "records": [],
            "export_json": "{}",
            "execution_authorized": False,
        }


    def replay(self, cases):
        return [{"step": index, "symbol": case.get("symbol")} for index, case in enumerate(cases, start=1)]

    def memory_view(self, limit=50):
        return []

    def connections(self):
        return {"broker": "NOT_CONNECTED"}

    def saas_status(self):
        return {"identity": "NOT_CONFIGURED"}


class StandaloneApplicationFactoryTests(unittest.TestCase):
    def test_existing_read_only_services_are_wired_to_shared_intelligence(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        architecture = app.architecture()
        self.assertEqual(architecture["architecture"], "ONE_SHARED_INTELLIGENCE")
        self.assertEqual(architecture["area_handler_status"]["command_cabin"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["analysis"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["study"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["control_center"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["tax_reserve"], "CONNECTED")
        self.assertEqual(architecture["area_handler_status"]["ecosystem_assistant"], "CONNECTED")
        self.assertEqual(len(architecture["area_handler_status"]), 6)
        self.assertTrue(architecture["all_area_handlers_connected"])

    def test_fiscal_and_assistant_areas_remain_routable_when_unconfigured(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        fiscal = app.handle(area=ApplicationArea.TAX_RESERVE, task="consultar")
        assistant = app.handle(area=ApplicationArea.ECOSYSTEM_ASSISTANT, task="consultar")
        self.assertEqual(fiscal["status"], "CONNECTED")
        self.assertEqual(fiscal["result"]["status"], "NOT_CONFIGURED")
        self.assertEqual(assistant["status"], "CONNECTED")
        self.assertEqual(assistant["result"]["status"], "NOT_CONFIGURED")
        self.assertFalse(fiscal["execution_authorized"])
        self.assertFalse(assistant["execution_authorized"])

    def test_command_cabin_is_read_only(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(area=ApplicationArea.COMMAND_CABIN, task="status")
        self.assertEqual(result["status"], "CONNECTED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["result"]["execution_authorized"])

    def test_analysis_requires_validated_market_context(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(area=ApplicationArea.ANALYSIS, task="analisar")
        self.assertEqual(result["result"]["status"], "DATA_PROVIDER_NOT_CONFIGURED")
        self.assertFalse(result["execution_authorized"])

    def test_missing_fiscal_owner_rejected(self):
        from finance.fiscal_reserve import FiscalReserve
        with self.assertRaises(ValueError):
            build_standalone_application(
                ecosystem_service=FakeService(),
                fiscal_reserve=FiscalReserve(),
            )


    def test_study_area_exposes_existing_learning_subsystems(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        for operation, expected in (
            ("sources", "learning_sources"),
            ("resources", "resources"),
            ("observations", "observations"),
            ("activities", "activities"),
        ):
            result = app.handle(
                area=ApplicationArea.STUDY,
                task="consultar",
                context={"operation": operation},
            )
            self.assertEqual(result["status"], "CONNECTED")
            self.assertIn(expected, result["result"])


    def test_assistant_receives_shared_intelligence_context(self):
        class FakeAssistant:
            def __init__(self):
                self.received = None

            def ask(self, **kwargs):
                self.received = kwargs.get("shared_intelligence_context")
                return {"answer": "Consulta somente leitura"}

        assistant = FakeAssistant()
        app = build_standalone_application(
            ecosystem_service=FakeService(),
            assistant=assistant,
            trusted_identity="trusted-user",
            fiscal_owner_id="trusted-owner",
        )
        result = app.handle(
            area=ApplicationArea.ECOSYSTEM_ASSISTANT,
            task="Explique o estado do ecossistema",
        )
        self.assertEqual(result["status"], "CONNECTED")
        self.assertEqual(assistant.received["architecture"], "ONE_SHARED_INTELLIGENCE")
        self.assertEqual(assistant.received["area"], "ecosystem_assistant")
        self.assertIn("risk_assessment", assistant.received["shared_capabilities"])
        self.assertFalse(result["execution_authorized"])

    def test_study_area_exposes_existing_learning_attempts(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(
            area=ApplicationArea.STUDY,
            task="consultar tentativas",
            context={"operation": "attempts"},
        )
        self.assertEqual(result["status"], "CONNECTED")
        self.assertEqual(result["result"]["attempts"], [])
        self.assertFalse(result["execution_authorized"])

    def test_study_area_exposes_existing_laboratory_replay(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(
            area=ApplicationArea.STUDY,
            task="replay de laboratório",
            context={"operation": "replay", "cases": [{"symbol": "EURUSD"}]},
        )
        self.assertEqual(result["status"], "CONNECTED")
        self.assertEqual(result["result"]["replay"][0]["symbol"], "EURUSD")
        self.assertFalse(result["execution_authorized"])

    def test_study_replay_rejects_empty_or_oversized_case_lists(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        with self.assertRaises(ValueError):
            app.handle(
                area=ApplicationArea.STUDY,
                task="replay",
                context={"operation": "replay", "cases": []},
            )

    def test_analysis_and_memory_expose_decision_report(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        report = app.handle(
            area=ApplicationArea.ANALYSIS,
            task="exportar relatório",
            context={"operation": "reports"},
        )
        memory_report = app.handle(
            area=ApplicationArea.MEMORY,
            task="consultar relatório",
            context={"operation": "report"},
        )
        self.assertEqual(report["result"]["reporting_status"], "DECISION_REPORT_READY")
        self.assertEqual(report["result"]["report"]["report_type"], "STANDALONE_DECISION_REPORT")
        self.assertEqual(memory_report["result"]["report"]["record_count"], 0)
        self.assertFalse(report["execution_authorized"])
        self.assertFalse(memory_report["execution_authorized"])

    def test_analysis_area_exposes_existing_statistics_and_news(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        stats = app.handle(
            area=ApplicationArea.ANALYSIS,
            task="consultar",
            context={"operation": "statistics"},
        )
        news = app.handle(
            area=ApplicationArea.ANALYSIS,
            task="consultar",
            context={"operation": "news"},
        )
        self.assertEqual(stats["result"]["reporting_status"], "STATISTICS_AVAILABLE")
        self.assertEqual(news["result"]["news"]["live"], False)

    def test_analysis_exposes_calendar_store_without_claiming_live_refresh(self):
        class FakeCalendarStore:
            def __init__(self):
                self.received = None

            def list_latest(self, **kwargs):
                self.received = kwargs
                return [{"source_id": "bls", "title": "US CPI", "actual": None}]

        store = FakeCalendarStore()
        app = build_standalone_application(
            ecosystem_service=FakeService(),
            economic_calendar_store=store,
        )
        result = app.handle(
            area=ApplicationArea.ANALYSIS,
            task="consultar calendário",
            context={
                "operation": "economic_calendar",
                "start_at": "2026-11-28T00:00:00Z",
                "end_at": "2026-11-29T00:00:00Z",
                "limit": 100,
            },
        )

        assert result["result"]["status"] == "STORED_OBSERVATIONS"
        assert result["result"]["events"][0]["actual"] is None
        assert result["result"]["live"] is False
        assert result["result"]["source_refresh"] == "NOT_REPORTED"
        assert store.received["limit"] == 100
        assert result["execution_authorized"] is False

    def test_analysis_reports_calendar_not_configured_without_store(self):
        app = build_standalone_application(ecosystem_service=FakeService())
        result = app.handle(
            area=ApplicationArea.ANALYSIS,
            task="consultar calendário",
            context={"operation": "economic_calendar"},
        )
        assert result["result"]["status"] == "CALENDAR_STORE_NOT_CONFIGURED"
        assert result["result"]["live"] is False

    def test_analysis_calendar_rejects_invalid_query_window_and_limit(self):
        class FakeCalendarStore:
            def list_latest(self, **kwargs):
                return []

        app = build_standalone_application(
            ecosystem_service=FakeService(),
            economic_calendar_store=FakeCalendarStore(),
        )
        with self.assertRaises(ValueError):
            app.handle(
                area=ApplicationArea.ANALYSIS,
                task="consultar calendário",
                context={"operation": "calendar", "start_at": "today", "end_at": "tomorrow"},
            )
        with self.assertRaises(ValueError):
            app.handle(
                area=ApplicationArea.ANALYSIS,
                task="consultar calendário",
                context={
                    "operation": "calendar",
                    "start_at": "2026-11-28T00:00:00Z",
                    "end_at": "2026-11-29T00:00:00Z",
                    "limit": True,
                },
            )


if __name__ == "__main__":
    unittest.main()
