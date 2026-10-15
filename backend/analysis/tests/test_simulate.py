"""Simulação temporal: validação contra a resposta linear e efeitos não lineares."""

import numpy as np
from django.test import SimpleTestCase

from analysis.engine.loop import build_loop
from analysis.engine.simulate import SimParams, simulate
from analysis.engine.tf import TF, step

PLANT = {"plant": {"mode": "tf", "num": "1", "den": "1 11.3 14 10"}}


class SimulateEngineTests(SimpleTestCase):
    def setUp(self):
        self.lp = build_loop(PLANT)

    def test_linear_pi_matches_closed_loop(self):
        r = simulate(self.lp, SimParams(kp=40, ki=20, tfinal=15))
        T = self.lp.with_controller(TF([40, 20], [1, 0])).closed(1.0)
        tg = np.linspace(0, 15, 3001)
        yref = np.interp(r["t"], tg, step(T, tg))
        self.assertLess(np.max(np.abs(np.asarray(r["series"]["y"]) - yref)), 0.02)
        self.assertTrue(r["metrics"]["linear_stable"])

    def test_loop_mode_reproduces_item_e(self):
        m = simulate(self.lp, SimParams(controller="loop", k=10, tfinal=15))["metrics"]
        self.assertAlmostEqual(m["steady_error"], 0.5, places=2)
        self.assertAlmostEqual(m["overshoot"], 22.9, delta=0.5)

    def test_saturation_and_anti_windup(self):
        common = dict(kp=60, ki=60, u_min=-15, u_max=15, tfinal=20)
        none = simulate(self.lp, SimParams(anti_windup="none", **common))
        clamp = simulate(self.lp, SimParams(anti_windup="clamping", **common))
        self.assertLessEqual(np.nanmax(np.abs(clamp["series"]["u"])), 15 + 1e-9)
        self.assertGreater(none["metrics"]["overshoot"], clamp["metrics"]["overshoot"] + 20)
        self.assertGreater(none["metrics"]["sat_time"], clamp["metrics"]["sat_time"])

    def test_integral_rejects_disturbance(self):
        m = simulate(self.lp, SimParams(kp=40, ki=20, dist_time=10, dist_amp=5, tfinal=30))["metrics"]
        self.assertGreater(m["dist_peak"], 0.05)
        self.assertLess(abs(m["steady_error"]), 0.01)

    def test_exact_delay(self):
        lp = build_loop({"plant": {"mode": "tf", "num": "1", "den": "10s+1"}, "delay": 2})
        r = simulate(lp, SimParams(kp=3, ki=0.3, tfinal=60))
        t, y = np.asarray(r["t"]), np.asarray(r["series"]["y"])
        self.assertAlmostEqual(t[np.argmax(np.abs(y) > 1e-9)], 2.0, delta=0.1)

    def test_noise_is_reproducible_and_increases_control_activity(self):
        p = dict(kp=40, ki=20, kd=5, ts_ctrl=0.05, tfinal=15)
        a = simulate(self.lp, SimParams(noise_std=0.01, seed=3, **p))
        b = simulate(self.lp, SimParams(noise_std=0.01, seed=3, **p))
        clean = simulate(self.lp, SimParams(**p))
        self.assertEqual(a["series"]["ym"].tolist(), b["series"]["ym"].tolist())
        self.assertGreater(a["metrics"]["u_total_variation"], 2 * clean["metrics"]["u_total_variation"])

    def test_unstable_gain_is_flagged(self):
        m = simulate(self.lp, SimParams(kp=500, tfinal=30))["metrics"]
        self.assertTrue(m["diverged"])
        self.assertFalse(m["linear_stable"])


class SimulateApiTests(SimpleTestCase):
    def test_endpoint(self):
        body = {"request": PLANT, "sim": {"kp": 40, "ki": 20, "u_min": -10, "u_max": 10, "dist_time": 8, "dist_amp": 2}}
        resp = self.client.post("/api/simulate/", body, content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertLessEqual(len(data["t"]), 1500)
        self.assertIn("iae", data["metrics"])

    def test_invalid_saturation(self):
        body = {"request": PLANT, "sim": {"u_min": 5, "u_max": 1}}
        self.assertEqual(self.client.post("/api/simulate/", body, content_type="application/json").status_code, 400)


class SimulinkFidelityTests(SimpleTestCase):
    """Reproduz o diagrama do SIMULINK do item r do trabalho de 2013."""

    GAINS = dict(kp=46.1129, ki=53.80365, kd=10.2266)  # médias usadas no trabalho

    def setUp(self):
        self.lp = build_loop({"plant": {"mode": "zpk", "poles": "-10, -0.65+0.759934j, -0.65-0.759934j", "gain": 1}})

    def test_matches_simulink_pid_block(self):
        # bloco Step em t = 1 s, PID paralelo com filtro N = 100 e derivada sobre o erro
        r = simulate(self.lp, SimParams(**self.GAINS, n_filter=100, derivative_on="error", ref_t0=1.0, tfinal=15))
        n = 100
        c = TF(np.polyadd(np.polymul([46.1129, 53.80365], [1, n]), [10.2266 * n, 0, 0]), np.polymul([1, 0], [1, n]))
        T = self.lp.with_controller(c).closed(1.0)
        tg = np.linspace(0, 14, 2801)
        t = np.asarray(r["t"])
        yref = np.interp(t - 1.0, tg, step(T, tg), left=0.0)
        self.assertLess(np.max(np.abs(np.asarray(r["series"]["y"]) - yref)), 0.02)
        y = np.asarray(r["series"]["y"])
        self.assertAlmostEqual(y.max(), 1.49, delta=0.02)               # pico lido no Scope do trabalho
        self.assertAlmostEqual(t[np.argmax(y)] - 1.0, 1.39, delta=0.05)

    def test_item_r_uses_simulink_form(self):
        from analysis.engine import analyze_tf
        r = {it["key"]: it for it in analyze_tf("1", "1 11.3 14 10")["items"]}["r"]["data"]
        self.assertEqual(r["n_filter"], 100.0)
