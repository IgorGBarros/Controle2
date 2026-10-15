"""Sintonia aprendida: uma rede neural que mapeia características da planta em ganhos de PID.

O aprendizado usa dados gerados pela própria ferramenta:

1. ``random_plant`` sorteia plantas estáveis (atrasos de 1ª ordem, par subamortecido, atraso
   de transporte, ganho estático);
2. ``plant_features`` extrai, de forma adimensional, as mesmas grandezas dos itens do trabalho
   (L e T da curva de reação — item p; ganho crítico Ku e período Pu — itens j/q; sobressinal
   da resposta ao degrau — itens b/k; ordem e polos complexos — itens c/d);
3. ``label_plant`` encontra os ganhos ótimos com o otimizador (IAE mínimo com sobressinal ≤ 10%);
4. a rede é treinada fora da aplicação (``manage.py treinar_sintonia``) e exportada para JSON;
   a inferência usa apenas NumPy.

Ganhos e características são normalizados pelo ganho estático K₀ e pela escala de tempo
τ = L + T da planta, como nas regras de sintonia clássicas (Ziegler-Nichols, AMIGO). Assim um
mesmo modelo serve para sistemas rápidos e lentos.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import numpy as np

from .loop import Loop, build_loop
from .optimize import Constraints, optimize_pid
from .simulate import SimParams, simulate
from .stability import critical_gain
from .tf import auto_tfinal, impulse, step, time_grid

MODEL_PATH = Path(__file__).resolve().parent.parent / "ml" / "model" / "sintonia_mlp.json"

FEATURES = ["tau", "log_kappa", "pu_rel", "has_ku", "overshoot_ol", "order", "has_complex"]
TARGETS = ["log_kp", "log_ki", "log_kd"]
OVERSHOOT_MAX = 10.0  # % — especificação usada para rotular os dados


# --- características da planta ------------------------------------------------------------

def reaction_curve(lp: Loop) -> dict | None:
    """L e T pela tangente no ponto de inflexão (1º método de Ziegler-Nichols).

    O atraso de transporte entra exato (L = L_planta + θ), e não pela aproximação de Padé, cuja
    resposta ao degrau tem um "contrapasso" que distorce a tangente.
    """
    g = lp.plant_raw
    if not g.is_stable() or g.system_type != 0:
        return None
    k0 = g.dc_gain()
    if not np.isfinite(k0) or k0 <= 0:
        return None
    t = time_grid(auto_tfinal(g), 4000)
    y = step(g, t)
    dy = impulse(g, t)
    i = int(np.argmax(dy))
    m = float(dy[i])
    if m <= 1e-12:
        return None
    L = max(float(t[i] - y[i] / m), 0.0) + lp.delay
    T = float(k0 / m)
    overshoot = max(0.0, (float(np.max(y)) - k0) / k0 * 100.0)
    return {"K0": float(k0), "L": L, "T": T, "overshoot": overshoot}


def critical_point(lp: Loop) -> tuple[float, float] | None:
    """Ganho crítico Ku e período Pu (2º método de ZN), com o atraso e^(-sθ) exato quando houver."""
    g = lp.plant_raw
    if lp.delay <= 0:
        crit = critical_gain(g.num, g.den)
        return (crit["Ku"], crit["Pu"]) if crit and crit.get("Pu") else None
    mags = np.abs(np.concatenate([g.poles(), g.zeros()]))
    mags = mags[mags > 1e-9]
    w_lo = 1e-3 * (mags.min() if mags.size else 1.0)
    w_hi = max(1e3 * (mags.max() if mags.size else 1.0), 100.0 / lp.delay)
    w = np.logspace(np.log10(w_lo), np.log10(w_hi), 20000)
    resp = g.freq(w)
    phase = np.unwrap(np.angle(resp)) - w * lp.delay
    idx = np.nonzero(phase <= -np.pi)[0]
    if not idx.size or idx[0] == 0:
        return None
    j = idx[0]
    f = (-np.pi - phase[j - 1]) / (phase[j] - phase[j - 1])
    wu = float(w[j - 1] + f * (w[j] - w[j - 1]))
    ku = 1.0 / float(np.abs(g.freq(np.array([wu]))[0]))
    return (ku, 2 * math.pi / wu) if np.isfinite(ku) and ku > 0 else None


def plant_features(lp: Loop) -> dict | None:
    """Características adimensionais da planta (None se fora do escopo: instável, integradora...)."""
    rc = reaction_curve(lp)
    if rc is None:
        return None
    k0, L, T = rc["K0"], rc["L"], rc["T"]
    tch = L + T
    if tch <= 0:
        return None
    crit = critical_point(lp)
    has_ku = crit is not None
    kappa = crit[0] * k0 if has_ku else 1e3
    poles = lp.plant_raw.poles()
    return {
        "tau": L / tch,
        "log_kappa": math.log10(min(max(kappa, 1e-3), 1e3)),
        "pu_rel": (crit[1] / tch) if has_ku else 0.0,
        "has_ku": 1.0 if has_ku else 0.0,
        "overshoot_ol": rc["overshoot"] / 100.0,
        "order": float(lp.plant_raw.order),
        "has_complex": 1.0 if np.any(np.abs(poles.imag) > 1e-9) else 0.0,
        # escalas (não entram na rede; servem para desnormalizar os ganhos)
        "_K0": k0,
        "_tch": tch,
        "_L": L,
        "_T": T,
    }


def scenario(feats: dict) -> SimParams:
    """Cenário padrão da sintonia aprendida: degrau unitário, derivada sobre a medição."""
    tch = feats["_tch"]
    return SimParams(ref_type="step", ref_amp=1.0, tfinal=max(12.0 * tch, 1.0),
                     derivative_on="measurement", n_filter=20.0 / tch, anti_windup="clamping")


def normalize_gains(g: dict, feats: dict) -> dict:
    k0, tch = feats["_K0"], feats["_tch"]
    return {"kp": g["kp"] * k0, "ki": g["ki"] * k0 * tch, "kd": g["kd"] * k0 / tch}


def denormalize_gains(n: dict, feats: dict) -> dict:
    k0, tch = feats["_K0"], feats["_tch"]
    return {"kp": n["kp"] / k0, "ki": n["ki"] / (k0 * tch), "kd": n["kd"] * tch / k0}


def zn_pid(feats: dict) -> dict:
    """PID pelo 2º método de Ziegler-Nichols (ou 1º, se não houver Ku), usado como ponto de partida."""
    if feats["has_ku"]:
        k0 = feats["_K0"]
        ku = 10 ** feats["log_kappa"] / k0
        pu = feats["pu_rel"] * feats["_tch"]
        return {"kp": 0.6 * ku, "ki": 1.2 * ku / pu, "kd": 0.075 * ku * pu}
    L, T, k0 = max(feats["_L"], 1e-3 * feats["_tch"]), feats["_T"], feats["_K0"]
    kp = 1.2 * T / (k0 * L)
    return {"kp": kp, "ki": kp / (2 * L), "kd": kp * 0.5 * L}


# --- geração de plantas e rótulos -----------------------------------------------------------

def random_plant(rng: np.random.Generator) -> dict:
    """Planta estável aleatória (especificação aceita por build_loop)."""
    n_lags = int(rng.integers(1, 5))
    taus = 10 ** rng.uniform(-1, 1, n_lags)
    den = np.array([1.0])
    for tau in taus:
        den = np.polymul(den, [tau, 1.0])
    complex_pair = rng.random() < 0.3
    if complex_pair:
        wn = 10 ** rng.uniform(-0.5, 0.5)
        zeta = rng.uniform(0.3, 0.9)
        den = np.polymul(den, [1 / wn ** 2, 2 * zeta / wn, 1.0])
    k0 = 10 ** rng.uniform(-1, 1)
    # 1ª ordem pura tem L = 0 e admite ganho infinito (não há ótimo finito): exige atraso
    needs_delay = n_lags == 1 and not complex_pair
    delay = float(rng.uniform(0.02, 1.5) * taus.sum()) if needs_delay or rng.random() < 0.6 else 0.0
    spec = {"plant": {"mode": "tf", "num": f"{k0:.6g}", "den": " ".join(f"{c:.6g}" for c in den)}}
    if delay > 1e-3:
        spec.update(delay=round(delay, 4), pade_order=3)
    return spec


def label_plant(lp: Loop, feats: dict, max_evals: int = 90) -> dict:
    """Ganhos ótimos (IAE mínimo, sobressinal ≤ 10%) e o desempenho do ZN para comparação."""
    base = scenario(feats)
    x0 = zn_pid(feats)
    res = optimize_pid(lp, base, "PID", "iae", Constraints(overshoot_max=OVERSHOOT_MAX), x0, max_evals=max_evals)
    zn = simulate(lp, replace(base, kp=x0["kp"], ki=x0["ki"], kd=x0["kd"]))["metrics"]
    return {"gains": res["ganhos"], "metrics": res["metricas"], "feasible": not res["violacoes"], "zn_metrics": zn}


# --- rede neural (inferência em NumPy) -------------------------------------------------------

class MLP:
    """Perceptron multicamadas exportado em JSON (ReLU nas camadas ocultas, saída linear)."""

    def __init__(self, data: dict):
        self.features = data["features"]
        self.targets = data["targets"]
        self.x_mean = np.array(data["x_mean"])
        self.x_std = np.array(data["x_std"])
        self.y_mean = np.array(data["y_mean"])
        self.y_std = np.array(data["y_std"])
        self.weights = [np.array(w) for w in data["weights"]]
        self.biases = [np.array(b) for b in data["biases"]]
        self.domain = data["domain"]
        self.meta = data.get("meta", {})

    def predict(self, x: np.ndarray) -> np.ndarray:
        h = (np.atleast_2d(x) - self.x_mean) / self.x_std
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            h = h @ w + b
            if i < len(self.weights) - 1:
                h = np.maximum(h, 0.0)
        return h * self.y_std + self.y_mean


@lru_cache(maxsize=1)
def load_model() -> MLP | None:
    if not MODEL_PATH.exists():
        return None
    return MLP(json.loads(MODEL_PATH.read_text(encoding="utf-8")))


def out_of_domain(feats: dict, model: MLP) -> list[str]:
    msgs = []
    names = {"tau": "atraso relativo L/(L+T)", "log_kappa": "ganho crítico normalizado",
             "pu_rel": "período crítico relativo", "overshoot_ol": "sobressinal em malha aberta", "order": "ordem da planta"}
    for f, (lo, hi) in model.domain.items():
        v = feats[f]
        span = hi - lo
        if v < lo - 0.05 * span or v > hi + 0.05 * span:
            msgs.append(f"{names.get(f, f)} = {v:.3g} fora da faixa de treino [{lo:.3g}; {hi:.3g}]")
    return msgs


def suggest(lp: Loop) -> dict:
    """Sintonia sugerida pela rede para a planta da malha, comparada com Ziegler-Nichols."""
    model = load_model()
    if model is None:
        return {"available": False, "reason": "Modelo ainda não treinado (rode manage.py treinar_sintonia)."}
    if not (lp.unity_feedback and lp.sign < 0):
        return {"available": True, "applicable": False,
                "reason": "A rede foi treinada para realimentação unitária negativa (H = 1)."}
    feats = plant_features(lp)
    if feats is None:
        return {"available": True, "applicable": False,
                "reason": "A rede foi treinada com plantas estáveis, sem integrador e com ganho estático positivo."}
    if feats["tau"] < 0.005:
        return {"available": True, "applicable": False,
                "reason": "A planta não tem atraso aparente (L ≈ 0, como uma 1ª ordem pura): o ganho pode crescer "
                          "sem limite e não existe sintonia ótima finita. A rede foi treinada com L > 0."}
    x = np.array([[feats[f] for f in model.features]])
    y = model.predict(x)[0]
    norm = {"kp": float(10 ** y[0]), "ki": float(10 ** y[1]), "kd": float(10 ** y[2])}
    gains = denormalize_gains(norm, feats)
    base = scenario(feats)
    pred = simulate(lp, replace(base, **gains))["metrics"]
    zn = zn_pid(feats)
    zn_m = simulate(lp, replace(base, **zn))["metrics"]
    return {
        "available": True,
        "applicable": True,
        "gains": gains,
        "normalized": norm,
        "features": {k: v for k, v in feats.items() if not k.startswith("_")},
        "scales": {"K0": feats["_K0"], "L": feats["_L"], "T": feats["_T"]},
        "scenario": {"derivative_on": base.derivative_on, "n_filter": base.n_filter, "tfinal": base.tfinal,
                     "anti_windup": base.anti_windup, "overshoot_max": OVERSHOOT_MAX},
        "metrics": pred,
        "zn": {"gains": zn, "metrics": zn_m},
        "warnings": out_of_domain(feats, model),
        "model": model.meta,
    }


def suggest_from_spec(spec: dict) -> dict:
    return suggest(build_loop(spec))
