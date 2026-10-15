"""Valida o motor de cálculo contra os resultados do Trabalho de Controle II (2013)."""

import math

import numpy as np
from django.test import SimpleTestCase

from analysis.engine import InputError, Params, ParseError, analyze, analyze_tf
from analysis.engine.parsing import parse_polynomial
from analysis.engine.stability import critical_gain, routh_table, stable_k_intervals
from analysis.engine.tf import TF


def items(result):
    return {it["key"]: it for it in result["items"]}


class ParsingTests(SimpleTestCase):
    def test_vector_format(self):
        np.testing.assert_allclose(parse_polynomial("[1 11.3 14 10]"), [1, 11.3, 14, 10])
        np.testing.assert_allclose(parse_polynomial("1, 2, 3"), [1, 2, 3])

    def test_expression_format(self):
        np.testing.assert_allclose(parse_polynomial("(s+10)(s^2+1.3s+1)"), [1, 11.3, 14, 10])
        np.testing.assert_allclose(parse_polynomial("2(s+3)"), [2, 6])

    def test_rejects_other_symbols(self):
        with self.assertRaises(ParseError):
            parse_polynomial("x^2 + 1")
        with self.assertRaises(ParseError):
            parse_polynomial("__import__('os')")
        with self.assertRaises(ParseError):
            parse_polynomial("s^999")


class StabilityTests(SimpleTestCase):
    num, den = [1.0], [1.0, 11.3, 14.0, 10.0]

    def test_critical_gain(self):
        crit = critical_gain(self.num, self.den)
        self.assertAlmostEqual(crit["Ku"], 148.2, places=6)
        self.assertAlmostEqual(crit["wu"], math.sqrt(14), places=6)
        self.assertAlmostEqual(crit["Pu"], 2 * math.pi / math.sqrt(14), places=6)

    def test_stable_interval(self):
        self.assertEqual(len(stable_k_intervals(self.num, self.den)), 1)
        lo, hi = stable_k_intervals(self.num, self.den)[0]
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 148.2, places=6)

    def test_routh(self):
        self.assertTrue(routh_table(self.den)["stable"])
        self.assertEqual(routh_table([1, -1, -2])["sign_changes"], 1)


class Trabalho2013Tests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.r = items(analyze_tf("1", "1 11.3 14 10", Params()))

    def test_no_item_errors(self):
        self.assertEqual([k for k, it in self.r.items() if it["error"]], [])

    def test_item_c_wn_zeta(self):
        dom = self.r["c"]["data"]["dominant"]
        self.assertAlmostEqual(dom["wn"], 1.0, places=6)
        self.assertAlmostEqual(dom["zeta"], 0.65, places=6)

    def test_item_d_poles(self):
        poles = sorted((p["value"]["re"], p["value"]["im"]) for p in self.r["d"]["data"]["poles"])
        self.assertAlmostEqual(poles[0][0], -10.0, places=6)
        self.assertAlmostEqual(poles[1][0], -0.65, places=6)
        self.assertAlmostEqual(abs(poles[1][1]), 0.7599, places=4)

    def test_item_g_gain_margin(self):
        m = self.r["g"]["data"]["margins"]
        self.assertAlmostEqual(m["gm"], 148.2, places=3)
        self.assertEqual(m["pm"], "inf")

    def test_item_k_transient(self):
        dom = self.r["k"]["data"]["dominant"]
        self.assertAlmostEqual(dom["peak_time"], 4.1340, places=3)
        self.assertAlmostEqual(dom["settling_time_2"], 6.1538, places=3)

    def test_item_n_flags_instability(self):
        n = self.r["n"]["data"]
        self.assertAlmostEqual(n["K"], 190.0, places=6)
        self.assertFalse(n["stable"])
        self.assertIn("INSTÁVEL", n["warning"])

    def test_item_o_desired_poles(self):
        o = self.r["o"]["data"]
        self.assertAlmostEqual(o["sigma"], 4 / 3, places=6)
        self.assertAlmostEqual(o["wd"], 1.62, places=2)
        self.assertAlmostEqual(o["wn"], 2.096, places=3)

    def test_item_q_table(self):
        pid = self.r["q"]["data"]["table"][2]
        self.assertAlmostEqual(pid["Kp"], 88.92, places=6)
        self.assertAlmostEqual(pid["Ki"], 1.2 * 148.2 / (2 * math.pi / math.sqrt(14)), places=6)
        self.assertAlmostEqual(pid["Kd"], 0.075 * 148.2 * 2 * math.pi / math.sqrt(14), places=6)

    def test_item_r_average(self):
        r = self.r["r"]["data"]
        p, q = self.r["p"]["data"]["table"][2], self.r["q"]["data"]["table"][2]
        self.assertAlmostEqual(r["average"]["PID"]["Kp"], (p["Kp"] + q["Kp"]) / 2, places=6)
        self.assertTrue(r["stable"])


class GenericSystemsTests(SimpleTestCase):
    def test_many_plants_run_without_errors(self):
        for num, den in [
            ("4", "s^2+2s+4"),
            ("1", "s(s+1)(s+5)"),
            ("1", "(s-1)(s+2)"),
            ("s+1", "s+2"),
            ("1", "s^2"),
            ("-s+1", "(s+1)^3"),
        ]:
            with self.subTest(num=num, den=den):
                r = items(analyze_tf(num, den, Params()))
                self.assertEqual({k: it["error"] for k, it in r.items() if it["error"]}, {})

    def test_type1_ess(self):
        g = TF([1], [1, 6, 5, 0])
        self.assertEqual(g.system_type, 1)
        n = items(analyze_tf("1", "s(s+1)(s+5)", Params()))["n"]["data"]
        self.assertEqual(n["input"], "rampa")
        self.assertAlmostEqual(n["K"], 1 / (0.05 * 0.2), places=6)


def loop_items(spec):
    r = analyze(spec, Params())
    errs = {it["key"]: it["error"] for it in r["items"] if it["error"]}
    assert not errs, errs
    return r, items(r)


class LoopTests(SimpleTestCase):
    """Malhas genéricas: controlador C(s), sensor H(s), sinal da realimentação, atraso."""

    def test_zpk_and_ss_match_tf(self):
        _, tf = loop_items({"plant": {"mode": "tf", "num": "1", "den": "1 11.3 14 10"}})
        _, zpk = loop_items({"plant": {"mode": "zpk", "zeros": "", "poles": "-10, -0.65+0.759934j, -0.65-0.759934j", "gain": 1}})
        _, ss = loop_items({"plant": {"mode": "ss", "A": "[-11.3 -14 -10; 1 0 0; 0 1 0]", "B": "[1;0;0]", "C": "[0 0 1]", "D": "0"}})
        for other in (zpk, ss):
            self.assertAlmostEqual(other["j"]["data"]["critical"]["Ku"], tf["j"]["data"]["critical"]["Ku"], places=3)

    def test_complex_without_conjugate_is_rejected(self):
        with self.assertRaises(InputError):
            analyze({"plant": {"mode": "zpk", "poles": "-1+2j", "gain": 1}}, Params())

    def test_sensor_changes_closed_loop(self):
        # T = K G/(1 + K G H): G = 10/(s(s+2)), H = 5/(s+5)
        r, it = loop_items({"plant": {"mode": "tf", "num": "10", "den": "s(s+2)"}, "sensor": {"num": "5", "den": "s+5"}})
        self.assertFalse(r["system"]["standard"])
        crit = it["j"]["data"]["critical"]
        # s^3 + 7s^2 + 10s + 50K = 0  ->  Ku = 70/50, wu = sqrt(10)
        self.assertAlmostEqual(crit["Ku"], 1.4, places=6)
        self.assertAlmostEqual(crit["wu"], math.sqrt(10), places=6)
        n = it["n"]["data"]
        self.assertEqual(n["input"], "rampa")
        self.assertAlmostEqual(n["K"], 0.8, places=6)  # e_rampa = (1-K)/(5K)
        self.assertTrue(n["stable"])

    def test_positive_feedback(self):
        _, it = loop_items({"plant": {"mode": "tf", "num": "1", "den": "(s+1)(s+3)"}, "feedback": "positive"})
        lo, hi = it["j"]["data"]["stable_intervals"][0]
        self.assertAlmostEqual(hi, 3.0, places=6)  # s^2 + 4s + 3 - K
        self.assertFalse(it["q"]["data"]["applicable"])

    def test_controller_multiplies_loop(self):
        _, it = loop_items({"plant": {"mode": "tf", "num": "1", "den": "(s+1)(s+2)(s+5)"},
                            "controller": {"mode": "pid", "kp": 20, "ki": 10, "kd": 5}})
        # PID com integrador -> erro nulo ao degrau, n) trata a rampa
        self.assertEqual(it["n"]["data"]["input"], "rampa")
        self.assertEqual(it["i"]["data"]["system_type"], 1)

    def test_delay_uses_pade(self):
        r, it = loop_items({"plant": {"mode": "tf", "num": "1", "den": "10s+1"}, "delay": 2, "pade_order": 3})
        self.assertEqual(len(r["system"]["open_loop"]["poles"]), 4)
        self.assertTrue(it["p"]["data"]["applicable"])
        self.assertGreater(it["p"]["data"]["L"], 1.0)

    def test_improper_loop_rejected(self):
        with self.assertRaises(InputError):
            analyze({"plant": {"mode": "tf", "num": "1", "den": "s+1"}, "controller": {"num": "s^2", "den": "1"}}, Params())


class ReportTests(SimpleTestCase):
    def test_report_sections_and_references(self):
        r = analyze_tf("1", "1 11.3 14 10", Params())
        rep = r["report"]
        self.assertEqual(len(rep["sections"]), 9)
        self.assertEqual({ref["key"] for ref in rep["references"]}, {"ogata", "meza"})
        text = " ".join(" ".join(s["paragraphs"] + s["bullets"]) for s in rep["sections"])
        self.assertIn("148,2", text)          # Ku
        self.assertIn("MEZA, 2024", text)
        self.assertIn("OGATA, 2011", text)
        self.assertNotIn("Não foi possível", text)
        freq = next(s for s in rep["sections"] if s["key"] == "frequencia")
        self.assertEqual(freq["chart"]["kind"], "nyquist")
        self.assertGreater(len(freq["chart"]["re"]), 100)


class OutputHygieneTests(SimpleTestCase):
    def test_no_control_characters_in_payload(self):
        """Regressão: um \\f virou caractere de controle e quebrou o LaTeX do item a."""
        import json
        import re
        r = analyze({"plant": {"mode": "tf", "num": "1", "den": "s+1"}, "sensor": {"num": "2", "den": "1"}}, Params())
        text = json.dumps(r, ensure_ascii=False)
        self.assertIsNone(re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text))
        a = next(it for it in r["items"] if it["key"] == "a")["data"]
        self.assertIn("\\frac{", a["closed_loop"])
