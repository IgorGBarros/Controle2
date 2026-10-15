"""Sintonia aprendida: características, normalização, inferência da rede e endpoint."""

from unittest import mock

import numpy as np
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from analysis.engine import learned
from analysis.engine.loop import build_loop

PLANT = {"plant": {"mode": "tf", "num": "1", "den": "1 11.3 14 10"}}


def fake_model(out_scale=0.0) -> learned.MLP:
    """Rede mínima (7 → 2 → 3) com pesos conhecidos; saída = log10 dos ganhos normalizados."""
    n = len(learned.FEATURES)
    return learned.MLP({
        "features": learned.FEATURES, "targets": learned.TARGETS,
        "x_mean": [0.0] * n, "x_std": [1.0] * n, "y_mean": [0.0, 0.1, -0.8], "y_std": [1.0, 1.0, 1.0],
        "weights": [np.eye(n, 2).tolist(), (np.ones((2, 3)) * out_scale).tolist()], "biases": [[0.0, 0.0], [0.0, 0.0, 0.0]],
        "domain": {"tau": [0.05, 0.6], "order": [1.0, 8.0]}, "meta": {"arquitetura": [n, 2, 3]},
    })


class FeatureTests(SimpleTestCase):
    def test_reaction_curve_of_triple_lag(self):
        # 1/(s+1)³: tabela clássica L ≈ 0,805 s, T ≈ 3,695 s
        rc = learned.reaction_curve(build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 3 3 1"}}))
        self.assertAlmostEqual(rc["L"], 0.805, delta=0.02)
        self.assertAlmostEqual(rc["T"], 3.695, delta=0.03)
        self.assertAlmostEqual(rc["K0"], 1.0, places=6)

    def test_exact_dead_time(self):
        # 1/(s+1)·e^(-0,5s): L = 0,5 exato; ωu resolve atan(ω) + 0,5ω = π → ωu ≈ 3,673, Ku = √(1+ωu²)
        lp = build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 1"}, "delay": 0.5, "pade_order": 3})
        f = learned.plant_features(lp)
        self.assertAlmostEqual(f["_L"], 0.5, delta=0.01)
        self.assertAlmostEqual(f["_T"], 1.0, delta=0.01)
        ku, pu = learned.critical_point(lp)
        self.assertAlmostEqual(ku, (1 + 3.6732 ** 2) ** 0.5, delta=0.01)
        self.assertAlmostEqual(pu, 2 * np.pi / 3.6732, delta=0.005)

    def test_features_are_scale_invariant(self):
        a = learned.plant_features(build_loop(PLANT))
        # mesma planta 10x mais lenta e com ganho 5x maior: características adimensionais iguais
        b = learned.plant_features(build_loop({"plant": {"mode": "tf", "num": "500", "den": "1000 1130 140 10"}}))
        for f in learned.FEATURES:
            self.assertAlmostEqual(a[f], b[f], delta=0.02, msg=f)
        self.assertAlmostEqual(b["_tch"] / a["_tch"], 10, delta=0.1)

    def test_out_of_scope_plants(self):
        self.assertIsNone(learned.plant_features(build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 1 0"}})))
        self.assertIsNone(learned.plant_features(build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 -1"}})))

    def test_normalization_round_trip(self):
        feats = learned.plant_features(build_loop(PLANT))
        g = {"kp": 30.0, "ki": 12.0, "kd": 4.0}
        back = learned.denormalize_gains(learned.normalize_gains(g, feats), feats)
        for k in g:
            self.assertAlmostEqual(back[k], g[k], places=9)

    def test_random_plants_have_dead_time(self):
        rng = np.random.default_rng(0)
        for _ in range(25):
            feats = learned.plant_features(build_loop(learned.random_plant(rng)))
            self.assertIsNotNone(feats)
            self.assertGreater(feats["tau"], 0.01)  # L > 0: existe ótimo finito


class ModelTests(SimpleTestCase):
    def test_mlp_forward_pass(self):
        m = fake_model(out_scale=0.5)
        x = np.arange(len(learned.FEATURES), dtype=float)[None, :] - 0.5
        h = np.maximum(x @ np.eye(len(learned.FEATURES), 2), 0)
        expected = h @ (np.ones((2, 3)) * 0.5) + np.array([0.0, 0.1, -0.8])
        np.testing.assert_allclose(m.predict(x), expected)

    def test_suggest_with_model(self):
        with mock.patch.object(learned, "load_model", return_value=fake_model()):
            r = learned.suggest(build_loop(PLANT))
        self.assertTrue(r["applicable"])
        feats = learned.plant_features(build_loop(PLANT))
        expected = learned.denormalize_gains({"kp": 1.0, "ki": 10 ** 0.1, "kd": 10 ** -0.8}, feats)
        for k in expected:
            self.assertAlmostEqual(r["gains"][k], expected[k], places=6)
        self.assertIn("iae", r["metrics"])
        self.assertIn("gains", r["zn"])

    def test_suggest_scope_and_domain(self):
        with mock.patch.object(learned, "load_model", return_value=fake_model()):
            pos = learned.suggest(build_loop({**PLANT, "feedback": "positive"}))
            integ = learned.suggest(build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 1 0"}}))
            far = learned.suggest(build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 1"}, "delay": 20, "pade_order": 3}))
        self.assertFalse(pos["applicable"])
        self.assertFalse(integ["applicable"])
        with mock.patch.object(learned, "load_model", return_value=fake_model()):
            self.assertFalse(learned.suggest(build_loop({"plant": {"mode": "tf", "num": "1", "den": "1 1"}}))["applicable"])
        self.assertTrue(far["applicable"])
        self.assertTrue(any("atraso relativo" in w for w in far["warnings"]))

    def test_without_model(self):
        with mock.patch.object(learned, "load_model", return_value=None):
            self.assertFalse(learned.suggest(build_loop(PLANT))["available"])

    def test_trained_model_on_reference_plant(self):
        model = learned.load_model()
        if model is None:
            self.skipTest("modelo não treinado")
        r = learned.suggest(build_loop(PLANT))
        self.assertTrue(r["applicable"])
        self.assertFalse(r["metrics"]["diverged"])
        self.assertLess(r["metrics"]["overshoot"], 25)
        self.assertLess(r["metrics"]["iae"], r["zn"]["metrics"]["iae"] * 1.5)


class EndpointTests(SimpleTestCase):
    def test_learned_tuning_endpoint(self):
        with mock.patch.object(learned, "load_model", return_value=fake_model()):
            resp = APIClient().post("/api/learned-tuning/", {"request": PLANT}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["applicable"])

    def test_invalid_request(self):
        resp = APIClient().post("/api/learned-tuning/", {"request": {"plant": {"mode": "tf", "num": "1", "den": "x y"}}}, format="json")
        self.assertEqual(resp.status_code, 400)
