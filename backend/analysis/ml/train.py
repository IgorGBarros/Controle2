"""Treino e avaliação da rede de sintonia (requer scikit-learn — ver requirements-ml.txt).

A rede aprende log10 dos ganhos normalizados (Kp·K₀, Ki·K₀·τ, Kd·K₀/τ) a partir das
características adimensionais da planta. A avaliação é feita no **conjunto de teste**,
re-simulando cada planta com os ganhos previstos — não basta acertar os números, a malha
precisa se comportar bem.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np

from ..engine.learned import FEATURES, OVERSHOOT_MAX, TARGETS, denormalize_gains, plant_features, scenario, zn_pid
from ..engine.loop import build_loop
from ..engine.simulate import simulate

CONTINUOUS = ["tau", "log_kappa", "pu_rel", "overshoot_ol", "order"]


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        try:
            if int(r["feasible"]) != 1:
                continue
            vals = [float(r[k]) for k in ("kp_n", "ki_n", "kd_n")]
        except (KeyError, ValueError):
            continue
        if all(v > 0 and math.isfinite(v) for v in vals):
            out.append(r)
    return out


def spec_of(r: dict) -> dict:
    spec = {"plant": {"mode": "tf", "num": r["num"], "den": r["den"]}}
    if float(r["delay"] or 0) > 1e-3:
        spec.update(delay=float(r["delay"]), pade_order=3)
    return spec


def evaluate(rows: list[dict], predict) -> dict:
    """Re-simula as plantas de teste com os ganhos previstos e compara com o ótimo e com ZN."""
    ratio_opt, ratio_zn, ok, ok_zn, div, div_zn, mp, mp_zn = [], [], 0, 0, 0, 0, [], []
    for r in rows:
        lp = build_loop(spec_of(r))
        feats = plant_features(lp)
        if feats is None:
            continue
        x = np.array([[feats[f] for f in FEATURES]])
        y = predict(x)[0]
        gains = denormalize_gains({"kp": 10 ** y[0], "ki": 10 ** y[1], "kd": 10 ** y[2]}, feats)
        base = scenario(feats)
        m = simulate(lp, replace(base, **gains))["metrics"]
        z = simulate(lp, replace(base, **zn_pid(feats)))["metrics"]
        opt_iae = float(r["opt_iae"])
        for met, ratios, mps in ((m, ratio_opt, mp), (z, ratio_zn, mp_zn)):
            bad = met.get("diverged") or not met.get("iae") or not math.isfinite(met["iae"])
            ratios.append(math.inf if bad else met["iae"] / opt_iae)
            mps.append(math.inf if bad else (met.get("overshoot") or 0.0))
        div += int(bool(m.get("diverged")))
        div_zn += int(bool(z.get("diverged")))
        ok += int(math.isfinite(mp[-1]) and mp[-1] <= OVERSHOOT_MAX + 2)
        ok_zn += int(math.isfinite(mp_zn[-1]) and mp_zn[-1] <= OVERSHOOT_MAX + 2)
    n = len(ratio_opt)

    def med(v):
        return float(np.median(v)) if v else None

    def p90(v):
        return float(np.percentile(v, 90)) if v else None

    return {
        "n_teste": n,
        "iae_rel_otimo_mediana": med(ratio_opt),
        "iae_rel_otimo_p90": p90(ratio_opt),
        "zn_iae_rel_otimo_mediana": med(ratio_zn),
        "sobressinal_mediana": med(mp),
        "zn_sobressinal_mediana": med(mp_zn),
        "taxa_spec": ok / n if n else None,          # sobressinal ≤ 12% (spec 10% + tolerância)
        "zn_taxa_spec": ok_zn / n if n else None,
        "divergiu": div,
        "zn_divergiu": div_zn,
        "melhor_que_zn": float(np.mean([a < b for a, b in zip(ratio_opt, ratio_zn)])) if n else None,
    }


def train(data: Path, out: Path, hidden=(32, 32), test_frac=0.2, seed=0, log=print) -> dict:
    from sklearn.metrics import r2_score
    from sklearn.neural_network import MLPRegressor

    rows = load_rows(data)
    if len(rows) < 50:
        raise ValueError(f"Poucos exemplos viáveis ({len(rows)}); gere mais dados.")
    X = np.array([[float(r[f]) for f in FEATURES] for r in rows])
    Y = np.log10(np.array([[float(r[k]) for k in ("kp_n", "ki_n", "kd_n")] for r in rows]))
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(rows))
    n_test = int(len(rows) * test_frac)
    te, tr = idx[:n_test], idx[n_test:]

    x_mean, x_std = X[tr].mean(0), X[tr].std(0)
    x_std[x_std < 1e-9] = 1.0
    y_mean, y_std = Y[tr].mean(0), Y[tr].std(0)
    y_std[y_std < 1e-9] = 1.0
    net = MLPRegressor(hidden_layer_sizes=hidden, activation="relu", alpha=1e-3, learning_rate_init=3e-3,
                       max_iter=4000, early_stopping=True, validation_fraction=0.15, n_iter_no_change=60,
                       random_state=seed)
    net.fit((X[tr] - x_mean) / x_std, (Y[tr] - y_mean) / y_std)

    data_json = {
        "features": FEATURES, "targets": TARGETS,
        "x_mean": x_mean.tolist(), "x_std": x_std.tolist(), "y_mean": y_mean.tolist(), "y_std": y_std.tolist(),
        "weights": [w.tolist() for w in net.coefs_], "biases": [b.tolist() for b in net.intercepts_],
        "domain": {f: [float(X[tr, FEATURES.index(f)].min()), float(X[tr, FEATURES.index(f)].max())] for f in CONTINUOUS},
    }
    from ..engine.learned import MLP

    model = MLP(data_json)
    pred_te = model.predict(X[te])
    r2 = {t: float(r2_score(Y[te, i], pred_te[:, i])) for i, t in enumerate(TARGETS)}
    log(f"R² (log ganhos, teste): {r2}")
    log("Avaliando no conjunto de teste por simulação...")
    ev = evaluate([rows[i] for i in te], model.predict)
    log(json.dumps(ev, indent=2, ensure_ascii=False))
    data_json["meta"] = {
        "arquitetura": [len(FEATURES), *hidden, len(TARGETS)],
        "parametros": int(sum(w.size + b.size for w, b in zip(net.coefs_, net.intercepts_))),
        "n_treino": int(len(tr)), "n_teste": int(len(te)), "n_total_csv": sum(1 for _ in data.open(encoding="utf-8")) - 1,
        "epocas": int(net.n_iter_), "r2_teste": r2, "avaliacao": ev,
        "especificacao": f"IAE mínimo com sobressinal ≤ {OVERSHOOT_MAX:g}% (degrau, derivada na medição)",
        "treinado_em": date.today().isoformat(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data_json, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return data_json["meta"]
