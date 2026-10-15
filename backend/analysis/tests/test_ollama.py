"""Provedor Ollama: o cliente conversa por HTTP com um servidor que imita a API /api/chat."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from django.test import SimpleTestCase

from analysis import llm, ollama_client

PLANT = {"plant": {"mode": "tf", "num": "1", "den": "1 11.3 14 10"}}


class FakeOllama(BaseHTTPRequestHandler):
    """Responde com a próxima resposta da fila e guarda as requisições recebidas."""

    replies: list = []
    requests: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        self._json({"models": [{"name": "qwen3.5:latest"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.requests.append(body)
        reply = FakeOllama.replies.pop(0)
        if body.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for i, piece in enumerate(reply):
                last = i == len(reply) - 1
                self.wfile.write((json.dumps({"message": {"role": "assistant", "content": piece}, "done": last,
                                              **({"done_reason": "stop"} if last else {})}) + "\n").encode())
        else:
            self._json({"message": {"role": "assistant", **reply}, "done": True, "done_reason": "stop"})

    def _json(self, data, code=200):
        raw = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


class OllamaTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.env = mock.patch.dict("os.environ", {"LLM_PROVIDER": "ollama", "OLLAMA_MODEL": "qwen3.5",
                                                 "OLLAMA_HOST": f"127.0.0.1:{cls.server.server_port}"}, clear=True)
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.server.shutdown()
        cls.server.server_close()
        super().tearDownClass()

    def setUp(self):
        FakeOllama.replies = []
        FakeOllama.requests = []

    def sse(self, resp):
        raw = b"".join(resp.streaming_content).decode()
        return [json.loads(x[6:]) for x in raw.split("\n\n") if x.startswith("data: ")]

    def test_status(self):
        data = self.client.get("/api/llm/status/").json()
        self.assertEqual(data, {"enabled": True, "provider": "ollama", "model": "qwen3.5", "reachable": True})

    def test_tutor_streams_from_local_model(self):
        FakeOllama.replies = [["O sistema ", "é estável."]]
        body = {"request": PLANT, "messages": [{"role": "user", "content": "É estável?"}]}
        events = self.sse(self.client.post("/api/tutor/", body, content_type="application/json"))
        self.assertEqual("".join(e.get("delta", "") for e in events), "O sistema é estável.")
        self.assertTrue(events[-1].get("done"))
        req = FakeOllama.requests[0]
        self.assertEqual(req["model"], "qwen3.5")
        self.assertEqual(req["messages"][0]["role"], "system")
        self.assertIn("<resultados_da_ferramenta>", req["messages"][1]["content"])  # contexto calculado pelo motor
        self.assertTrue(req["messages"][1]["content"].endswith("É estável?"))
        self.assertGreaterEqual(req["options"]["num_ctx"], 16384)

    def test_describe_uses_json_schema_and_engine_validation(self):
        out = {"plant": {"mode": "tf", "num": "10", "den": "s^2 + 2s + 10", "zeros": "", "poles": "", "gain": 0,
                         "A": "", "B": "", "C": "", "D": ""},
               "controller": {"mode": "tf", "num": "1", "den": "1", "kp": 0, "ki": 0, "kd": 0},
               "sensor": {"num": "1", "den": "1"}, "feedback": "negative", "delay": 0,
               "summary": "Massa-mola-amortecedor.", "derivation": ["$m\\ddot x + b\\dot x + kx = F$"],
               "assumptions": [], "questions": []}
        FakeOllama.replies = [{"content": json.dumps(out)}]
        resp = self.client.post("/api/describe/", {"text": "massa-mola com m=1, b=2, k=10"}, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["validation_error"])
        self.assertEqual(data["spec"]["plant"], {"mode": "tf", "num": "10", "den": "s^2 + 2s + 10"})
        self.assertEqual(data["model"], "qwen3.5")
        self.assertEqual(FakeOllama.requests[0]["format"], llm.DESCRIBE_SCHEMA)

    def test_describe_rejects_invalid_json(self):
        FakeOllama.replies = [{"content": "não sei"}]
        resp = self.client.post("/api/describe/", {"text": "um sistema qualquer"}, content_type="application/json")
        self.assertEqual(resp.status_code, 422)

    def test_tuning_tool_loop_with_lenient_arguments(self):
        FakeOllama.replies = [
            # o modelo local omite campos e manda os argumentos como texto JSON
            {"content": "Vou otimizar um PI.", "tool_calls": [{"function": {"name": "otimizar", "arguments": json.dumps(
                {"estrutura": "PI", "sobressinal_max": 5, "kp_inicial": "50", "ki_inicial": 40})}}]},
            {"content": "", "tool_calls": [{"function": {"name": "finalizar", "arguments": {
                "kp": 10, "ki": 6, "estrutura": "PI", "resumo": "PI otimizado.", "atendeu": True}}}]},
        ]
        body = {"request": PLANT, "sim": {"tfinal": 15}, "goal": "sobressinal abaixo de 5%"}
        events = self.sse(self.client.post("/api/tune/", body, content_type="application/json"))
        types = [e["type"] for e in events]
        self.assertEqual(types, ["start", "text", "tool", "final", "done"])
        tool = events[2]
        self.assertEqual(tool["input"]["criterio"], "iae")          # completado com o padrão
        self.assertEqual(tool["input"]["acomodacao_max"], -1.0)
        self.assertEqual(tool["input"]["kp_inicial"], 50.0)          # texto convertido em número
        self.assertEqual(tool["result"]["violacoes"], {})
        final = events[3]
        self.assertEqual(final["recommendation"]["kd"], 0.0)          # ausente → ganho do cenário (0)
        self.assertIn("overshoot", final["metrics"])                  # re-simulado pelo motor
        second = FakeOllama.requests[1]["messages"]
        self.assertEqual(second[-2]["role"], "assistant")
        self.assertEqual(second[-1]["role"], "tool")
        self.assertEqual(second[-1]["tool_name"], "otimizar")
        self.assertEqual(FakeOllama.requests[0]["tools"][0]["function"]["name"], "simular")

    def test_unreachable_server_gives_friendly_error(self):
        with mock.patch.dict("os.environ", {"OLLAMA_HOST": "127.0.0.1:9"}):
            self.assertFalse(ollama_client.reachable(timeout=0.5))
            resp = self.client.post("/api/describe/", {"text": "um motor CC"}, content_type="application/json")
        self.assertEqual(resp.status_code, 502)
        self.assertIn("ollama serve", resp.json()["errors"]["llm"][0])
