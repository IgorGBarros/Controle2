"""Simulação temporal da malha com efeitos não lineares e práticos.

Diferente das respostas lineares dos itens a)–r), aqui a malha é integrada passo a passo,
o que permite incluir:

- saturação do atuador e anti-windup (condicional ou por back-calculation);
- perturbação de carga na entrada da planta;
- ruído de medição no sensor;
- controlador discreto com período de amostragem próprio;
- atraso de transporte exato (buffer de amostras, sem aproximação de Padé);
- perfis de referência (degrau, onda quadrada, rampa, senoide).

A planta e o sensor são discretizados por segurador de ordem zero (exato para entrada
constante em cada passo).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

from .loop import Loop
from .tf import TF, auto_tfinal

MAX_STEPS = 40_000
OUT_POINTS = 1500


@dataclass
class SimParams:
    controller: str = "pid"          # "pid" | "loop" (usa K·C(s) da malha)
    kp: float = 1.0
    ki: float = 0.0
    kd: float = 0.0
    n_filter: float = 100.0          # coeficiente do filtro derivativo N (padrão do bloco PID do Simulink)
    derivative_on: str = "error"     # "error" (padrão do Simulink) | "measurement" (sem "chute" na referência)
    k: float = 1.0                   # ganho K que multiplica C(s) no modo "loop"
    anti_windup: str = "clamping"    # "none" | "clamping" | "back_calculation"
    ts_ctrl: float = 0.0             # período de amostragem do controlador (0 = "contínuo")
    u_min: float | None = None
    u_max: float | None = None
    ref_type: str = "step"           # "step" | "square" | "ramp" | "sine"
    ref_amp: float = 1.0
    ref_period: float = 10.0
    ref_t0: float = 0.0              # instante de início da referência (o bloco Step do Simulink usa 1 s)
    dist_time: float | None = None
    dist_amp: float = 0.0
    noise_std: float = 0.0
    seed: int = 1
    tfinal: float | None = None
    fast: bool = False               # passo mais grosso (usado pelo otimizador); a planta continua exata (ZOH)
    extra: dict = field(default_factory=dict)


def _ss_discrete(g: TF, dt: float):
    A, B, C, D = signal.tf2ss(g.num, g.den)
    if A.size == 0:  # ganho estático
        return np.zeros((0, 0)), np.zeros((0, 1)), np.zeros((1, 0)), np.atleast_2d(D)
    Ad, Bd, Cd, Dd, _ = signal.cont2discrete((A, B, C, D), dt, method="zoh")
    return Ad, Bd, Cd, Dd


class _Block:
    """Sistema linear discretizado: x[k+1] = A x + B u, y = C x + D u."""

    def __init__(self, g: TF, dt: float):
        self.A, self.B, self.C, self.D = _ss_discrete(g, dt)
        self.x = np.zeros(self.A.shape[0])

    def output(self, u: float) -> float:
        y = float(self.D[0, 0]) * u
        if self.x.size:
            y += float(self.C[0] @ self.x)
        return y

    def advance(self, u: float) -> None:
        if self.x.size:
            self.x = self.A @ self.x + self.B[:, 0] * u


def _proper_controller(c: TF, n: float) -> TF:
    """Torna C(s) própria acrescentando polos rápidos em −N, se necessário."""
    extra = -c.relative_degree
    if extra <= 0:
        return c
    den = np.array([1.0])
    for _ in range(extra):
        den = np.polymul(den, [1.0 / n, 1.0])
    return TF(c.num, np.polymul(c.den, den))


def reference(p: SimParams, t: np.ndarray) -> np.ndarray:
    a = p.ref_amp
    tau = t - p.ref_t0
    on = tau >= 0
    if p.ref_type == "ramp":
        r = a * tau
    elif p.ref_type == "sine":
        r = a * np.sin(2 * math.pi * tau / p.ref_period)
    elif p.ref_type == "square":
        r = np.where(np.floor(tau / (p.ref_period / 2)) % 2 == 0, a, 0.0)
    else:
        r = np.full_like(t, a)
    return np.where(on, r, 0.0)


def simulate(lp: Loop, p: SimParams) -> dict:
    plant = lp.plant_raw  # atraso tratado à parte, de forma exata
    sensor = lp.sensor

    # --- passo de integração e horizonte ------------------------------------
    T_ref = lp.closed(1.0) if p.controller == "loop" else lp.plant_raw
    tfinal = float(p.tfinal or max(auto_tfinal(T_ref, lp.plant_raw) * 1.5, 10.0 + (lp.delay or 0) * 5) + p.ref_t0)
    if p.ref_type in ("square", "sine"):
        tfinal = max(tfinal, 2 * p.ref_period)
    poles = np.concatenate([plant.poles(), sensor.poles()])
    fastest = max([abs(x) for x in poles if abs(x) > 1e-9] + [1e-3, p.n_filter if p.kd else 0])
    dt = tfinal / 2000 if p.fast else min(tfinal / 4000, 0.1 / fastest)
    if p.ts_ctrl and p.ts_ctrl > 0:
        dt = min(dt, p.ts_ctrl / 5)
        # o período do controlador deve ser múltiplo do passo
        dt = p.ts_ctrl / max(1, math.ceil(p.ts_ctrl / dt))
    n = int(min(MAX_STEPS, math.ceil(tfinal / dt))) + 1
    dt = tfinal / (n - 1)
    t = np.linspace(0.0, tfinal, n)

    G = _Block(plant, dt)
    H = _Block(sensor, dt)
    delay_n = int(round(lp.delay / dt)) if lp.delay else 0
    buf = [0.0] * delay_n

    # --- controlador ----------------------------------------------------------
    ctrl_every = max(1, int(round(p.ts_ctrl / dt))) if p.ts_ctrl and p.ts_ctrl > 0 else 1
    h = dt * ctrl_every
    sign = -1.0 if lp.sign < 0 else 1.0  # e = r − ym (negativa) ou r + ym (positiva)
    C_block = None
    if p.controller == "loop":
        c = _proper_controller(lp.controller * p.k, max(p.n_filter, 10.0))
        Cd = signal.cont2discrete(signal.tf2ss(c.num, c.den), h, method="bilinear") if c.order else None
        if Cd is None:
            C_block = ("gain", float(c.num[-1] / c.den[-1]))
        else:
            A, B, Cm, D, _ = Cd
            C_block = ("ss", A, B, Cm, D, np.zeros(A.shape[0]))

    lo = -np.inf if p.u_min is None else p.u_min
    hi = np.inf if p.u_max is None else p.u_max
    rng = np.random.default_rng(p.seed)
    r = reference(p, t)
    d = np.zeros(n)
    if p.dist_time is not None and p.dist_amp:
        d[t >= p.dist_time] = p.dist_amp

    y = np.zeros(n)
    ym = np.zeros(n)
    u = np.zeros(n)
    u_raw = np.zeros(n)
    integ = 0.0
    dterm = 0.0
    prev_meas = 0.0  # todos os sinais são nulos antes de t = 0
    u_hold = 0.0
    u_raw_hold = 0.0
    diverged_at = None
    limit = 1e4 * max(1.0, abs(p.ref_amp), abs(p.dist_amp))
    tt = math.sqrt(abs(p.kd / p.ki)) if p.ki and p.kd else (abs(p.kp / p.ki) if p.ki else 1.0)  # back-calculation

    for k in range(n):
        # saída da planta com a entrada aplicada no passo anterior
        y[k] = G.output(buf[0] if delay_n else (u[k - 1] + d[k - 1] if k else 0.0))
        meas = H.output(y[k]) + (rng.normal(0.0, p.noise_std) if p.noise_std > 0 else 0.0)
        ym[k] = meas

        if k % ctrl_every == 0:
            e = r[k] + sign * meas
            if p.controller == "pid":
                # derivada sobre o erro (como o bloco PID do Simulink) ou sobre a medição (sem "chute")
                v = e if p.derivative_on == "error" else sign * meas
                if p.kd:
                    dterm = (dterm + p.kd * p.n_filter * (v - prev_meas)) / (1.0 + p.n_filter * h)
                prev_meas = v
                raw = p.kp * e + integ + dterm
                sat = min(max(raw, lo), hi)
                if p.ki:
                    if p.anti_windup == "clamping":
                        pushing_out = (raw > hi and e > 0) or (raw < lo and e < 0)
                        if not pushing_out:
                            integ += p.ki * e * h
                    elif p.anti_windup == "back_calculation":
                        integ += p.ki * e * h + (sat - raw) * h / tt
                    else:
                        integ += p.ki * e * h
            else:
                if C_block[0] == "gain":
                    raw = C_block[1] * e
                else:
                    _, A, B, Cm, D, xc = C_block
                    raw = float(Cm[0] @ xc) + float(D[0, 0]) * e if xc.size else float(D[0, 0]) * e
                    if xc.size:
                        C_block = ("ss", A, B, Cm, D, A @ xc + B[:, 0] * e)
                sat = min(max(raw, lo), hi)
            u_hold, u_raw_hold = sat, raw
        u[k], u_raw[k] = u_hold, u_raw_hold

        # avança a planta e o sensor
        u_in = u[k] + d[k]
        if delay_n:
            buf.append(u_in)
            G.advance(buf.pop(0))
        else:
            G.advance(u_in)
        H.advance(y[k])
        if not np.isfinite(y[k]) or abs(y[k]) > limit:
            diverged_at = float(t[k])
            y[k:] = np.nan
            ym[k:] = np.nan
            u[k:] = np.nan
            u_raw[k:] = np.nan
            break

    metrics = compute_metrics(t, r, y, u, u_raw, d, p, lo, hi, dt, diverged_at)
    metrics["linear_stable"] = linear_stability(lp, p)
    idx = np.unique(np.linspace(0, n - 1, min(n, OUT_POINTS)).astype(int))
    return {
        "t": t[idx],
        "series": {
            "r": r[idx], "y": y[idx], "ym": ym[idx], "u": u[idx], "u_raw": u_raw[idx],
            "e": (r - y)[idx], "d": d[idx],
        },
        "metrics": metrics,
        "dt": dt,
        "h": h,
        "delay_samples": delay_n,
        "tfinal": tfinal,
        "saturation": {"u_min": p.u_min, "u_max": p.u_max},
    }


def compute_metrics(t, r, y, u, u_raw, d, p: SimParams, lo, hi, dt, diverged_at) -> dict:
    if diverged_at is not None:
        return {"diverged": True, "diverged_at": diverged_at}
    e = r - y
    out = {
        "diverged": False,
        "iae": float(np.trapezoid(np.abs(e), t)),
        "ise": float(np.trapezoid(e ** 2, t)),
        "itae": float(np.trapezoid(t * np.abs(e), t)),
        "u_max_abs": float(np.max(np.abs(u))),
        "u_energy": float(np.trapezoid(u ** 2, t)),
        "u_total_variation": float(np.sum(np.abs(np.diff(u)))),
        "sat_time": float(np.sum((u_raw > hi + 1e-12) | (u_raw < lo - 1e-12)) * dt),
    }
    n_tail = max(1, len(t) // 10)
    t_end_window = t >= (p.dist_time if p.dist_time is not None and p.dist_amp else t[-1] + 1)
    # resposta ao degrau inicial (antes de qualquer perturbação)
    if p.ref_type == "step" and abs(p.ref_amp) > 1e-12:
        seg = ~t_end_window & (t >= p.ref_t0)
        ts_, ys_ = t[seg] - p.ref_t0, y[seg]  # tempos medidos a partir do instante do degrau
        if ts_.size > 10:
            final = float(np.mean(ys_[-max(1, ys_.size // 10):]))
            ref = final if abs(final) > 1e-9 else p.ref_amp
            out["overshoot"] = float(max(0.0, (np.max(ys_ * np.sign(ref)) - abs(ref)) / abs(ref) * 100))
            band = 0.02 * abs(ref)
            outside = np.flatnonzero(np.abs(ys_ - ref) > band)
            out["settling_time"] = (float(ts_[outside[-1] + 1]) if outside.size and outside[-1] + 1 < ts_.size
                                    else (None if outside.size else 0.0))
            out["final_before_disturbance"] = final
        out["steady_error"] = float(np.mean(e[-n_tail:]))
    if p.dist_time is not None and p.dist_amp:
        after = t >= p.dist_time
        if np.any(after) and np.any(~after):
            base = float(y[~after][-1])
            dev = y[after] - base
            k_peak = int(np.argmax(np.abs(dev)))
            out["dist_peak"] = float(dev[k_peak])
            band = max(0.02 * max(abs(p.ref_amp), 1e-9), 1e-9)
            outside = np.flatnonzero(np.abs(dev) > band)
            if outside.size and outside[-1] + 1 < dev.size:
                out["dist_recovery"] = float(t[after][outside[-1] + 1] - p.dist_time)
            elif not outside.size:
                out["dist_recovery"] = 0.0
            else:
                out["dist_recovery"] = None
    return out


def linear_stability(lp: Loop, p: SimParams) -> bool:
    """Estabilidade da malha linear equivalente (sem saturação, controlador contínuo)."""
    if p.controller == "loop":
        c = lp.controller * p.k
    elif p.kd:
        n = p.n_filter
        num = np.polyadd(np.polymul([p.kp, p.ki], [1.0, n]), [p.kd * n, 0.0, 0.0])
        c = TF(num, np.polymul([1.0, 0.0], [1.0, n])) if p.ki else TF(np.polyadd(np.polymul([p.kp], [1.0, n]), [p.kd * n, 0.0]), [1.0, n])
    else:
        c = TF([p.kp, p.ki], [1.0, 0.0]) if p.ki else TF([p.kp], [1.0])
    try:
        return lp.with_controller(c).closed(1.0).is_stable()
    except ValueError:
        return False


def suggested_pid(lp: Loop) -> dict:
    """Ponto de partida: PID do controlador da malha, se houver; senão um P conservador."""
    if lp.controller_pid:
        return dict(lp.controller_pid)
    g0 = lp.plant_raw.dc_gain()
    kp = 1.0 / abs(g0) if np.isfinite(g0) and abs(g0) > 1e-9 else 1.0
    return {"kp": float(kp), "ki": 0.0, "kd": 0.0}
