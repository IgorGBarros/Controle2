"""Entrada em linguagem natural (Claude simulado), contexto da análise e IA desabilitada."""

import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from analysis import llm
from analysis.engine import Params


def describe_payload(**over):
    data = {
        "plant": {"mode": "tf", "num": "1", "den": "s^2 + 0.5s + 2", "zeros": "", "poles": "", "gain": 0,
                  "A": "", "B": "", "C": "", "D": ""},
        "controller": {"mode": "tf", "num": "1", "den": "1", "kp": 0, "ki": 0, "kd": 0},
        "sensor": {"num": "1", "den": "1"},
        "feedback": "negative",
        "delay": 0,
        "summary": "Massa-mola-amortecedor",
        "derivation": ["$m\\ddot y + b\\dot y + k y = u$"],
        "assumptions": ["m = 1 kg"],
        "questions": [],
    }
    data.update(over)
    return data


def fake_client(create_payload=None, stop_reason="end_turn"):
    client = mock.MagicMock()
    if create_payload is not None:
        client.beta.messages.create.return_value = SimpleNamespace(
            stop_reason=stop_reason, model="claude-opus-5-5",
            content=[SimpleNamespace(type="text", text=json.dumps(create_payload))],
        )
    return client


@mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"})
class DescribeTests(SimpleTestCase):
    def test_valid_description_returns_validated_spec(self):
        client = fake_client(describe_payload())
        with mock.patch.object(llm, "get_client", return_value=client):
            resp = self.client.post("/api/describe/", {"text": "massa-mola com m=1, b=0,5, k=2"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["spec"]["plant"], {"mode": "tf", "num": "1", "den": "s^2 + 0.5s + 2"})
        self.assertIsNone(body["validation_error"])
        kwargs = client.beta.messages.create.call_args.kwargs
        self.assertEqual(kwargs["model"], llm.MODEL)
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertEqual(kwargs["fallbacks"], "default")

    def test_invalid_model_output_is_flagged_by_engine(self):
        bad = describe_payload(plant={"mode": "tf", "num": "s^3", "den": "s+1", "zeros": "", "poles": "", "gain": 0,
                                      "A": "", "B": "", "C": "", "D": ""})
        with mock.patch.object(llm, "get_client", return_value=fake_client(bad)):
            resp = self.client.post("/api/describe/", {"text": "algo impróprio"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("própria", resp.json()["validation_error"])

    def test_refusal(self):
        with mock.patch.object(llm, "get_client", return_value=fake_client(describe_payload(), stop_reason="refusal")):
            resp = self.client.post("/api/describe/", {"text": "texto"}, content_type="application/json")
        self.assertEqual(resp.status_code, 422)


class DisabledTests(SimpleTestCase):
    @mock.patch.dict("os.environ", {"OLLAMA_HOST": "127.0.0.1:9"}, clear=True)
    def test_status_and_endpoints_without_key(self):
        status = self.client.get("/api/llm/status/").json()
        self.assertFalse(status["enabled"])
        # o Assistente IA usa o Ollama por padrão; sem servidor no ar, responde 503 com instruções
        self.assertEqual(status["assistant"]["provider"], "ollama")
        self.assertFalse(status["assistant"]["reachable"])
        resp = self.client.post("/api/describe/", {"text": "motor CC"}, content_type="application/json")
        self.assertEqual(resp.status_code, 503)
        resp = self.client.post("/api/assistant/", {"request": {"num": "1", "den": "s+1"}, "messages": [{"role": "user", "content": "oi"}]},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 503)


class ContextTests(SimpleTestCase):
    REQ = {"plant": {"mode": "tf", "num": "1", "den": "1 11.3 14 10"}}

    def test_context_omits_long_series(self):
        ctx = llm.analysis_context(llm.cached_analysis(self.REQ, Params()))
        self.assertLess(len(ctx), 120_000)
        self.assertIn("OGATA, 2011", ctx)
