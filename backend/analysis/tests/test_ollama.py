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
        if isinstance(reply, dict) and "__error__" in reply:
            code, msg = reply["__error__"]
            return self._json({"error": msg}, code)
        if body.get("stream"):
            pieces, calls = (reply, []) if isinstance(reply, list) else ([reply["content"]] if reply.get("content") else [], reply.get("tool_calls", []))
            chunks = [{"message": {"role": "assistant", "content": p}, "done": False} for p in pieces]
            if calls:
                chunks.append({"message": {"role": "assistant", "content": "", "tool_calls": calls}, "done": False})
            chunks.append({"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            for c in chunks:
                self.wfile.write((json.dumps(c) + "\n").encode())
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

    def text(self, events):
        return "".join(e["text"] for e in events if e["type"] == "delta")

    def ask(self, content="oi", **extra):
        body = {"request": PLANT, "messages": [{"role": "user", "content": content}], **extra}
        return self.sse(self.client.post("/api/assistant/", body, content_type="application/json"))

    def test_status(self):
        data = self.client.get("/api/llm/status/").json()
        local = {"enabled": True, "provider": "ollama", "model": "qwen3.5", "reachable": True}
        self.assertEqual(data, {**local, "assistant": local})

    def test_assistant_defaults_to_ollama_even_with_claude_key(self):
        env = {"ANTHROPIC_API_KEY": "test", "OLLAMA_HOST": f"127.0.0.1:{self.server.server_port}"}
        with mock.patch.dict("os.environ", env, clear=True):
            status = self.client.get("/api/llm/status/").json()
            self.assertEqual(status["provider"], "anthropic")         # linguagem natural segue no Claude
            self.assertEqual(status["assistant"]["provider"], "ollama")
            FakeOllama.replies = [["Resposta local."]]
            events = self.ask()
        self.assertEqual(self.text(events), "Resposta local.")
        self.assertEqual(len(FakeOllama.requests), 1)

    def test_unreachable_returns_503(self):
        with mock.patch.dict("os.environ", {"OLLAMA_HOST": "127.0.0.1:9"}):
            resp = self.client.post("/api/assistant/", {"request": PLANT, "messages": [{"role": "user", "content": "oi"}]},
                                    content_type="application/json")
        self.assertEqual(resp.status_code, 503)
        self.assertIn("ollama pull qwen3.5", resp.json()["errors"]["llm"][0])

    def test_explains_with_compact_context(self):
        FakeOllama.replies = [["O sistema ", "é estável."]]
        events = self.ask("É estável?")
        self.assertEqual(self.text(events), "O sistema é estável.")
        self.assertEqual(events[-1]["type"], "done")
        req = FakeOllama.requests[0]
        self.assertEqual(req["model"], "qwen3.5")
        self.assertTrue(req["stream"])
        self.assertEqual(req["messages"][0]["role"], "system")
        first = req["messages"][1]["content"]
        self.assertIn("<resultados_da_ferramenta>", first)        # contexto calculado pelo motor
        self.assertIn("<cenario_do_simulador>", first)
        self.assertNotIn("<relatorio_gerado>", first)              # contexto enxuto
        self.assertLess(len(first), 16000)
        self.assertTrue(first.endswith("É estável?"))
        self.assertEqual(req["options"]["num_ctx"], 8192)
        self.assertEqual({t["function"]["name"] for t in req["tools"]},
                         {"simular", "otimizar", "sintonia_rede_neural", "propor_sintonia"})

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

    def test_tuning_with_tools_and_lenient_arguments(self):
        FakeOllama.replies = [
            # o modelo local omite campos e manda os argumentos como texto JSON
            {"content": "Vou otimizar um PI.", "tool_calls": [{"function": {"name": "otimizar", "arguments": json.dumps(
                {"estrutura": "PI", "sobressinal_max": 5, "kp_inicial": "50", "ki_inicial": 40})}}]},
            {"content": "", "tool_calls": [{"function": {"name": "propor_sintonia", "arguments": {
                "kp": 10, "ki": 6, "estrutura": "PI", "resumo": "PI otimizado.", "atendeu": True}}}]},
            ["Pronto: o PI atende ao limite de 5%."],
        ]
        events = self.ask("Quero sobressinal abaixo de 5%", sim={"tfinal": 15})
        types = [e["type"] for e in events]
        self.assertEqual(types, ["delta", "tool", "proposal", "delta", "done"])
        tool = events[1]
        self.assertEqual(tool["input"]["criterio"], "iae")          # completado com o padrão
        self.assertEqual(tool["input"]["acomodacao_max"], -1.0)
        self.assertEqual(tool["input"]["kp_inicial"], 50.0)          # texto convertido em número
        self.assertEqual(tool["result"]["violacoes"], {})
        prop = events[2]
        self.assertEqual(prop["recommendation"]["kd"], 0.0)          # ausente → ganho do cenário (0)
        self.assertIn("overshoot", prop["metrics"])                  # re-simulado pelo motor
        second = FakeOllama.requests[1]["messages"]
        self.assertEqual(second[-2]["role"], "assistant")
        self.assertEqual(second[-1]["role"], "tool")
        self.assertEqual(second[-1]["tool_name"], "otimizar")
        third = FakeOllama.requests[2]["messages"]
        self.assertIn("metricas_verificadas", third[-1]["content"])  # o modelo recebe as métricas da proposta

    def test_neural_network_tool(self):
        FakeOllama.replies = [
            {"content": "", "tool_calls": [{"function": {"name": "sintonia_rede_neural", "arguments": {}}}]},
            ["A rede sugere um PID."],
        ]
        events = self.ask("Qual sintonia a rede neural sugere?")
        tool = next(e for e in events if e["type"] == "tool")
        self.assertEqual(tool["name"], "sintonia_rede_neural")
        self.assertTrue(tool["result"]["disponivel"])
        self.assertGreater(tool["result"]["ganhos"]["kp"], 0)

    def test_conversation_history_is_sent(self):
        FakeOllama.replies = [["Sim."]]
        msgs = [{"role": "user", "content": "É estável?"}, {"role": "assistant", "content": "É, os polos estão no SPE."},
                {"role": "user", "content": "E com K = 200?"}]
        self.sse(self.client.post("/api/assistant/", {"request": PLANT, "messages": msgs}, content_type="application/json"))
        sent = FakeOllama.requests[0]["messages"]
        self.assertEqual([m["role"] for m in sent], ["system", "user", "assistant", "user"])
        self.assertEqual(sent[-1]["content"], "E com K = 200?")

    def test_unreachable_server_gives_friendly_error(self):
        with mock.patch.dict("os.environ", {"OLLAMA_HOST": "127.0.0.1:9"}):
            self.assertFalse(ollama_client.reachable(timeout=0.5))
            resp = self.client.post("/api/describe/", {"text": "um motor CC"}, content_type="application/json")
        self.assertEqual(resp.status_code, 502)
        self.assertIn("ollama serve", resp.json()["errors"]["llm"][0])

    def test_retries_with_smaller_context_when_out_of_memory(self):
        oom = "llama-server reported out-of-memory during startup: failed to allocate compute pp buffers"
        FakeOllama.replies = [{"__error__": (500, oom)}, ["Resposta com contexto menor."]]
        events = self.ask()
        self.assertEqual(self.text(events), "Resposta com contexto menor.")
        self.assertEqual([r["options"]["num_ctx"] for r in FakeOllama.requests], [8192, ollama_client.MIN_CTX])

    def test_out_of_memory_twice_gives_actionable_message(self):
        oom = "ggml_gallocr_reserve_n_impl: failed to allocate CUDA_Host buffer of size 58835008"
        FakeOllama.replies = [{"__error__": (500, oom)}, {"__error__": (500, oom)}]
        events = self.ask()
        err = next(e for e in events if e["type"] == "error")["error"]
        self.assertIn("Memória insuficiente", err)
        self.assertIn("qwen3.5:4b", err)
