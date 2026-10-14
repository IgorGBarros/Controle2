"""Valida o motor de cálculo contra os resultados do Trabalho de Controle II (2013)."""

import math

import numpy as np
from django.test import SimpleTestCase

from analysis.engine import Params, ParseError, analyze
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
        cls.r = items(analyze("1", "1 11.3 14 10", Params()))

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
                r = items(analyze(num, den, Params()))
                self.assertEqual({k: it["error"] for k, it in r.items() if it["error"]}, {})

    def test_type1_ess(self):
        g = TF([1], [1, 6, 5, 0])
        self.assertEqual(g.system_type, 1)
        n = items(analyze("1", "s(s+1)(s+5)", Params()))["n"]["data"]
        self.assertEqual(n["input"], "rampa")
        self.assertAlmostEqual(n["K"], 1 / (0.05 * 0.2), places=6)
