"""Sintonia numérica de controladores P, PI, PD e PID com restrições.

Minimiza um critério de desempenho (IAE, ITAE ou ISE) da simulação no tempo, penalizando
violações de restrições (sobressinal, tempo de acomodação, esforço de controle, erro final).
É usado pelo assistente de sintonia com IA, mas não depende dele.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from scipy.optimize import minimize

from .loop import Loop
from .simulate import SimParams, simulate

STRUCTURES = {"P": ("kp",), "PI": ("kp", "ki"), "PD": ("kp", "kd"), "PID": ("kp", "ki", "kd")}


@dataclass
class Constraints:
    overshoot_max: float | None = None   # %
    settling_max: float | None = None    # s
    u_abs_max: float | None = None       # |u| máximo
    steady_error_max: float | None = None

    @classmethod
    def from_tool(cls, d: dict) -> "Constraints":
        def opt(v):
            return None if v is None or v < 0 else float(v)
        return cls(opt(d.get("sobressinal_max")), opt(d.get("acomodacao_max")),
                   opt(d.get("u_max_abs")), opt(d.get("erro_final_max")))


def violations(m: dict, c: Constraints) -> dict:
    out = {}
    if m.get("diverged"):
        return {"divergiu": True}
    if c.overshoot_max is not None and (m.get("overshoot") or 0) > c.overshoot_max:
        out["sobressinal"] = m["overshoot"]
    if c.settling_max is not None:
        ts = m.get("settling_time")
        if ts is None or ts > c.settling_max:
            out["acomodacao"] = ts
    if c.u_abs_max is not None and (m.get("u_max_abs") or 0) > c.u_abs_max:
        out["u_max_abs"] = m["u_max_abs"]
    if c.steady_error_max is not None and abs(m.get("steady_error") or 0) > c.steady_error_max:
        out["erro_final"] = m.get("steady_error")
    if m.get("linear_stable") is False:
        out["malha_linear_instavel"] = True
    return out


def metrics_for(lp: Loop, base: SimParams, gains: dict, fast: bool = True) -> dict:
    p = replace(base, controller="pid", fast=fast, kp=gains.get("kp", 0.0), ki=gains.get("ki", 0.0), kd=gains.get("kd", 0.0))
    return simulate(lp, p)["metrics"]


def cost(m: dict, criterion: str, c: Constraints) -> float:
    if m.get("diverged"):
        return 1e9
    j = float(m.get(criterion) or 0.0)
    pen = 0.0
    if c.overshoot_max is not None:
        pen += max(0.0, (m.get("overshoot") or 0) - c.overshoot_max) / max(c.overshoot_max, 1.0)
    if c.settling_max is not None:
        ts = m.get("settling_time")
        pen += 3.0 if ts is None else max(0.0, ts - c.settling_max) / c.settling_max
    if c.u_abs_max is not None:
        pen += max(0.0, (m.get("u_max_abs") or 0) - c.u_abs_max) / max(c.u_abs_max, 1e-9)
    if c.steady_error_max is not None:
        pen += max(0.0, abs(m.get("steady_error") or 0) - c.steady_error_max) / max(c.steady_error_max, 1e-9)
    if m.get("linear_stable") is False:
        pen += 5.0
    return j * (1.0 + 10.0 * pen) + 100.0 * pen


def optimize_pid(lp: Loop, base: SimParams, structure: str, criterion: str, constraints: Constraints,
                 x0: dict | None = None, max_evals: int = 140) -> dict:
    keys = STRUCTURES[structure]
    if criterion not in ("iae", "itae", "ise"):
        criterion = "iae"
    start = {k: max(abs((x0 or {}).get(k, 0.0)), 1e-3) for k in keys}
    if not x0 or all((x0 or {}).get(k, 0.0) == 0 for k in keys):
        start = {k: 1.0 for k in keys}
    z0 = np.log10([start[k] for k in keys])
    evals = {"n": 0}
    best = {"J": math.inf, "gains": None, "metrics": None}

    def gains_of(z):
        return {k: (10 ** float(v) if k in keys else 0.0) for k, v in zip(keys, z)}

    def f(z):
        z = np.clip(z, -4, 5)
        g = gains_of(z)
        m = metrics_for(lp, base, g)
        evals["n"] += 1
        J = cost(m, criterion, constraints)
        if J < best["J"]:
            best.update(J=J, gains=g, metrics=m)
        return J

    def run(z_start, budget):
        simplex = np.vstack([z_start] + [z_start + 0.5 * np.eye(len(keys))[i] for i in range(len(keys))])
        minimize(f, z_start, method="Nelder-Mead",
                 options={"maxfev": budget, "initial_simplex": simplex, "xatol": 1e-3, "fatol": 1e-4})

    run(z0, max_evals)
    if violations(best["metrics"], constraints):
        # segunda partida com ganhos 5x menores (evita mínimos locais com esforço de controle alto)
        run(z0 - math.log10(5.0), max_evals // 2)
    gains = {k: best["gains"].get(k, 0.0) for k in ("kp", "ki", "kd")}
    final = metrics_for(lp, base, gains, fast=False)  # verificação com o passo fino
    return {
        "estrutura": structure,
        "criterio": criterion,
        "ganhos": gains,
        "metricas": final,
        "violacoes": violations(final, constraints),
        "avaliacoes": evals["n"],
    }
