from django.test import SimpleTestCase


class ApiTests(SimpleTestCase):
    def test_analyze_ok(self):
        resp = self.client.post("/api/analyze/", {"num": "1", "den": "1 11.3 14 10"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual([it["key"] for it in body["items"]], list("abcdefghijklmnopqr"))

    def test_analyze_invalid(self):
        resp = self.client.post("/api/analyze/", {"num": "s^3", "den": "s+1"}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("system", resp.json()["errors"])

    def test_analyze_loop(self):
        body = {
            "plant": {"mode": "zpk", "poles": "0, -2, -4", "gain": 8},
            "controller": {"mode": "tf", "num": "s+1", "den": "s+10"},
            "sensor": {"num": "1", "den": "1"},
            "feedback": "negative",
        }
        resp = self.client.post("/api/analyze/", body, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["system"]["standard"])

    def test_analyze_missing_plant(self):
        resp = self.client.post("/api/analyze/", {"k": 2}, content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_examples(self):
        self.assertEqual(self.client.get("/api/examples/").status_code, 200)
