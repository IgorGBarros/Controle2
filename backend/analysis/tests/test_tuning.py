"""Assistente de sintonia: otimizador e laço de ferramentas com o Claude simulado."""

import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from analysis import llm
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


@mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test", "TUNING_PROVIDER": "anthropic"})
class TuneLoopTests(SimpleTestCase):
    def body(self):
        return {"request": PLANT, "sim": {"tfinal": 15, "u_min": -20, "u_max": 20}, "goal": "sobressinal abaixo de 5% sem saturar"}

    def test_tool_loop_and_verified_final(self):
        opt_args = {"estrutura": "PI", "criterio": "iae", "sobressinal_max": 5, "acomodacao_max": -1, "u_max_abs": -1,
                    "erro_final_max": -1, "anti_windup": "clamping", "derivative_on": "error",
                    "kp_inicial": 50, "ki_inicial": 40, "kd_inicial": 0}
        final_args = {"kp": 10.0, "ki": 6.0, "kd": 0.0, "estrutura": "PI", "anti_windup": "clamping", "derivative_on": "error",
                      "especificacao": "Mp ≤ 5%", "resumo": "PI otimizado.", "compromissos": "Mais lento.", "atendeu": True}
        responses = [
            SimpleNamespace(stop_reason="tool_use", content=[text("Vou otimizar um PI."), tool_use("otimizar", opt_args, "t1")]),
            SimpleNamespace(stop_reason="tool_use", content=[tool_use("finalizar", final_args, "t2")]),
        ]
        client = mock.MagicMock()
        client.beta.messages.create.side_effect = responses
        with mock.patch.object(llm, "get_client", return_value=client):
            resp = self.client.post("/api/tune/", self.body(), content_type="application/json")
            raw = b"".join(resp.streaming_content).decode()
        events = [json.loads(x[6:]) for x in raw.split("\n\n") if x.startswith("data: ")]
        types = [e["type"] for e in events]
        self.assertEqual(types, ["start", "text", "tool", "final", "done"])
        tool_ev = events[2]
        self.assertEqual(tool_ev["name"], "otimizar")
        self.assertEqual(tool_ev["result"]["violacoes"], {})
        final = events[3]
        self.assertEqual(final["recommendation"]["kp"], 10.0)
        self.assertIn("overshoot", final["metrics"])  # re-simulado pelo motor
        # o resultado da ferramenta voltou ao modelo como tool_result
        second_call = client.beta.messages.create.call_args_list[1].kwargs["messages"]
        tool_results = next(m for m in second_call if m["role"] == "user" and isinstance(m["content"], list) and isinstance(m["content"][0], dict) and m["content"][0].get("type") == "tool_result")
        self.assertEqual(tool_results["content"][0]["tool_use_id"], "t1")
        self.assertEqual(client.beta.messages.create.call_args_list[0].kwargs["tools"][0]["strict"], True)

    def test_disabled_without_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            resp = self.client.post("/api/tune/", self.body(), content_type="application/json")
        self.assertEqual(resp.status_code, 503)
