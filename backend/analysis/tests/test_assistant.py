"""Assistente IA (tutor + sintonia) com o Claude simulado, e o otimizador que ele usa."""

import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from analysis import assistant, llm
from analysis.engine.loop import build_loop
from analysis.engine.optimize import Constraints, optimize_pid
from analysis.engine.simulate import SimParams

PLANT = {"plant": {"mode": "tf", "num": "1", "den": "1 11.3 14 10"}}


class OptimizerTests(SimpleTestCase):
    def test_pi_meets_overshoot_limit(self):
        lp = build_loop(PLANT)
        r = optimize_pid(lp, SimParams(tfinal=15), "PI", "iae", Constraints(overshoot_max=5), {"kp": 50, "ki": 40})
        self.assertEqual(r["violacoes"], {})
        self.assertLessEqual(r["metricas"]["overshoot"], 5.0 + 1e-6)
        self.assertEqual(r["ganhos"]["kd"], 0.0)

    def test_reports_infeasible_constraints(self):
        lp = build_loop(PLANT)
        r = optimize_pid(lp, SimParams(tfinal=15), "P", "iae", Constraints(steady_error_max=0.001), {"kp": 10}, max_evals=40)
        self.assertIn("erro_final", r["violacoes"])  # proporcional puro não zera o erro (planta tipo 0)




def tool_use(name, args, id_):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_)


def text(t):
    return SimpleNamespace(type="text", text=t)


class FakeStream:
    """Imita client.beta.messages.stream: texto em pedaços e a mensagem final com as ferramentas."""

    def __init__(self, content, stop_reason):
        self.text_stream = iter([b.text for b in content if b.type == "text"])
        self._final = SimpleNamespace(stop_reason=stop_reason, content=content)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._final


def claude(turns):
    """Cliente falso: cada turno é (conteúdo, stop_reason); guarda as mensagens enviadas."""
    client = mock.MagicMock()
    sent = []
    queue = list(turns)

    def stream(**kw):
        sent.append(json.loads(json.dumps(kw["messages"], default=lambda o: o.__dict__)))
        return FakeStream(*queue.pop(0))

    client.beta.messages.stream.side_effect = stream
    return client, sent


@mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "ASSISTANT_PROVIDER": "anthropic"})
class AssistantClaudeTests(SimpleTestCase):
    def post(self, messages, sim=None):
        body = {"request": PLANT, "messages": messages, **({"sim": sim} if sim else {})}
        resp = self.client.post("/api/assistant/", body, content_type="application/json")
        self.assertEqual(resp["Content-Type"], "text/event-stream")
        raw = b"".join(resp.streaming_content).decode()
        return [json.loads(x[6:]) for x in raw.split("\n\n") if x.startswith("data: ")]

    def test_explains_grounded_on_computed_results(self):
        client, sent = claude([([text("O ganho crítico "), text("é 148,2.")], "end_turn")])
        with mock.patch.object(llm, "get_client", return_value=client):
            events = self.post([{"role": "user", "content": "Qual o Ku?"}])
        self.assertEqual("".join(e["text"] for e in events if e["type"] == "delta"), "O ganho crítico é 148,2.")
        self.assertEqual(events[-1]["type"], "done")
        first = sent[0][0]["content"]
        self.assertIn("148.2", first[0]["text"])                 # Ku calculado pelo motor
        self.assertIn("<relatorio_gerado>", first[0]["text"])    # Claude recebe o contexto completo
        self.assertEqual(first[0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(first[1]["text"], "Qual o Ku?")
        kwargs = client.beta.messages.stream.call_args.kwargs
        self.assertEqual({t["name"] for t in kwargs["tools"]}, {"simular", "otimizar", "sintonia_rede_neural", "propor_sintonia"})

    def test_tool_loop_and_verified_proposal(self):
        opt_args = {"estrutura": "PI", "criterio": "iae", "sobressinal_max": 5, "acomodacao_max": -1, "u_max_abs": -1,
                    "erro_final_max": -1, "anti_windup": "clamping", "derivative_on": "error",
                    "kp_inicial": 50, "ki_inicial": 40, "kd_inicial": 0}
        prop_args = {"kp": 10.0, "ki": 6.0, "kd": 0.0, "estrutura": "PI", "anti_windup": "clamping", "derivative_on": "error",
                     "especificacao": "Mp ≤ 5%", "resumo": "PI otimizado.", "compromissos": "Mais lento.", "atendeu": True}
        client, sent = claude([
            ([text("Vou otimizar um PI."), tool_use("otimizar", opt_args, "t1")], "tool_use"),
            ([tool_use("propor_sintonia", prop_args, "t2")], "tool_use"),
            ([text("Pronto.")], "end_turn"),
        ])
        with mock.patch.object(llm, "get_client", return_value=client):
            events = self.post([{"role": "user", "content": "sobressinal abaixo de 5% sem saturar"}],
                               sim={"tfinal": 15, "u_min": -20, "u_max": 20})
        self.assertEqual([e["type"] for e in events], ["delta", "tool", "proposal", "delta", "done"])
        self.assertEqual(events[1]["result"]["violacoes"], {})
        self.assertLessEqual(events[1]["result"]["metricas"]["overshoot"], 5.0 + 1e-6)
        prop = events[2]
        self.assertEqual(prop["recommendation"]["kp"], 10.0)
        self.assertLessEqual(prop["metrics"]["u_max_abs"], 20 + 1e-9)    # re-simulado no cenário com saturação
        results = sent[1][-1]["content"]
        self.assertEqual(results[0]["type"], "tool_result")
        self.assertEqual(results[0]["tool_use_id"], "t1")
        self.assertIn("metricas_verificadas", sent[2][-1]["content"][0]["content"])

    def test_rejects_bad_turn_order(self):
        resp = self.client.post("/api/assistant/", {"request": PLANT, "messages": [{"role": "assistant", "content": "x"}]},
                                content_type="application/json")
        self.assertEqual(resp.status_code, 400)

    def test_tool_call_limit(self):
        sim_args = {"kp": 10, "ki": 1, "kd": 0, "anti_windup": "clamping", "derivative_on": "error"}
        turns = [([tool_use("simular", sim_args, f"t{i}")], "tool_use") for i in range(assistant.MAX_TURNS)]
        client, _ = claude(turns)
        with mock.patch.object(llm, "get_client", return_value=client):
            events = self.post([{"role": "user", "content": "simule tudo"}])
        self.assertEqual(sum(e["type"] == "tool" for e in events), assistant.MAX_TURNS)
        self.assertIn("limite de etapas", events[-2]["text"])


class CoerceArgsTests(SimpleTestCase):
    def test_fills_missing_and_invalid_values_from_scenario(self):
        base = SimParams(kp=3, ki=2, kd=1, anti_windup="back_calculation", derivative_on="measurement")
        a = assistant.coerce_args("propor_sintonia", {"kp": "7", "ki": None, "estrutura": "XYZ", "anti_windup": "foo"}, base)
        self.assertEqual((a["kp"], a["ki"], a["kd"]), (7.0, 2.0, 1.0))
        self.assertEqual(a["estrutura"], "PID")
        self.assertEqual(a["anti_windup"], "back_calculation")
        self.assertEqual(a["derivative_on"], "measurement")
        self.assertFalse(a["atendeu"])
