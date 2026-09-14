        self.assertIn("error", payload)

    def test_analyze_exposes_stable_presentation_and_security_contract(self):
        status, _, payload = self.request(
            "/api/analyze",
            method="POST",
            payload={"score": 90, "symbol": "EURUSD", "timeframe": "5m", "confirmed": True, "filters_ok": True},
        )
        self.assertEqual(status, "200 OK")
        # Without senior market context, even a high score must fail closed.
        self.assertEqual(payload["signal"], "AGUARDAR")
        self.assertEqual(payload["presentation"]["label"], "AGUARDAR")
        self.assertTrue(payload["security"]["real_blocked"])
        self.assertTrue(payload["execution_allowed"] is False)
        self.assertIn("decision_id", payload)

    def test_replay_records_multiple_cases(self):
        status, _, payload = self.request(
            "/api/replay",
            method="POST",
            payload={"cases": [
                {"score": 90, "symbol": "EURUSD", "timeframe": "5m", "confirmed": True, "filters_ok": True},
                {"score": 20, "symbol": "EURUSD", "timeframe": "5m", "confirmed": False, "filters_ok": True},
            ]},
        )
        self.assertEqual(status, "200 OK")
        self.assertEqual(len(payload["results"]), 2)
        assert all(item["signal"] == "AGUARDAR" for item in payload["results"])
