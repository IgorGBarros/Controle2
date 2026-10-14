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

    def test_examples(self):
        self.assertEqual(self.client.get("/api/examples/").status_code, 200)
