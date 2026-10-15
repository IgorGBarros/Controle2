"""Itens a) a r) do Trabalho de Controle II, generalizados para qualquer malha C(s), G(s), H(s)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal
from scipy.optimize import brentq

from .loop import Loop, is_unity, pid_tf
from .formatting import complex_str, factored_latex, fmt, fmt_plain, fmt_txt, poly_latex, tf_latex
from .stability import (
    critical_gain,
    jw_crossings,
    root_locus,
    routh_symbolic,
    routh_table,
    stable_k_intervals,
)
from .tf import (
    TF,
    analytic_second_order,
    auto_tfinal,
    dominant_poles,
    final_value,
    impulse,
    padd,
    pmul,
    ramp,
    simulate,
    step,
    step_info,
    time_grid,
)


@dataclass
class Params:
    k: float = 10.0
    k_step: float | None = None
    k_ramp: float | None = None
    k_impulse: float | None = None
    ess_target: float = 0.05
    ts_spec: float = 3.0
    mp_spec: float = 7.5
    sine_freq: float = 1.0
    sine_amp: float = 1.0
    tfinal: float | None = None
    zn_include_gain: bool = True


# --- utilidades ------------------------------------------------------------

def tf_info(g: TF) -> dict:
    return {
        "num": g.num.tolist(),
        "den": g.den.tolist(),
        "latex": tf_latex(g.num, g.den),
        "poles": g.poles(),
        "zeros": g.zeros(),
        "stable": g.is_stable(),
    }


def tgrid(p: Params, *systems: TF) -> np.ndarray:
    return time_grid(p.tfinal if p.tfinal else auto_tfinal(*systems))


def clip_series(y: np.ndarray, limit: float = 1e6) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    return np.where(np.abs(y) > limit, np.nan, y)


def steady_error(T: TF, q: int) -> dict:
    """Erro em regime (realimentação unitária) para R(s) = 1/s^q."""
    num_e = padd(T.den, -T.num)
    den_e = pmul(T.den, [1.0] + [0.0] * q) if q > 0 else T.den
    return final_value(num_e, den_e)


def output_behaviour(T: TF, q: int) -> dict:
    """Comportamento de y(t) para R(s) = 1/s^q (teorema do valor final)."""
    den_y = pmul(T.den, [1.0] + [0.0] * q) if q > 0 else T.den
    return final_value(T.num, den_y)


BEHAVIOUR_TEXT = {
    "settles": "estabiliza em {v}",
    "unbounded": "cresce sem limite (acompanha a entrada sem estabilizar)",
    "oscillates": "oscila indefinidamente (polos sobre o eixo imaginário)",
    "diverge": "diverge — sistema instável (polos no semiplano direito)",
}


def describe(b: dict) -> str:
    return BEHAVIOUR_TEXT[b["kind"]].format(v=fmt_txt(b["value"]) if b["value"] is not None else "")


def error_limit(T: TF, q: int) -> float:
    """lim s→0 de s·R(s)·[1 − T(s)] com R = 1/s^q, sem verificar estabilidade (erro r − y)."""
    a = padd(T.den, -T.num)
    if np.allclose(a, 0):
        return 0.0

    def low(p):
        p = np.asarray(p)
        z = 0
        while z < len(p) - 1 and abs(p[len(p) - 1 - z]) < 1e-12:
            z += 1
        return z, p[len(p) - 1 - z]

    za, ca = low(a)
    zd, cd = low(T.den)
    order = za - zd - (q - 1)
    if order > 0:
        return 0.0
    if order < 0:
        return math.inf
    return float(ca / cd)


def fb_sign_tex(lp: Loop) -> str:
    return "+" if lp.sign < 0 else "-"


def closed_formula(lp: Loop, k_sym: str = "K") -> str:
    """Expressão simbólica de T(s) para a malha."""
    c = "C(s)" if not is_unity(lp.controller) else ""
    h = "H(s)" if not is_unity(lp.sensor) else ""
    kc = rf"{k_sym}\,{c}" if k_sym else c
    fwd = f"{kc}G(s)".strip() or "G(s)"
    return rf"\frac{{{fwd}}}{{1 {fb_sign_tex(lp)} {fwd}{h}}}"


def response_set(T: TF, t: np.ndarray, kinds=("step", "ramp", "impulse"), sine: tuple | None = None) -> dict:
    out: dict = {"t": t}
    series: dict = {}
    analysis: dict = {}
    for kind in kinds:
        if kind == "step":
            series["step"] = clip_series(step(T, t))
            q = 1
        elif kind == "ramp":
            series["ramp"] = clip_series(ramp(T, t))
            series["ramp_input"] = t
            q = 2
        elif kind == "impulse":
            series["impulse"] = clip_series(impulse(T, t))
            q = 0
        else:
            continue
        b = output_behaviour(T, q)
        analysis[kind] = {"output": b, "output_text": describe(b)}
    if sine:
        amp, w = sine
        u = amp * np.sin(w * t)
        series["sine_input"] = u
        series["sine"] = clip_series(simulate(T, t, u))
        if T.is_stable():
            h = T.freq([w])[0]
            analysis["sine"] = {
                "amplitude_ratio": float(abs(h)),
                "phase_deg": float(T.phase_deg([w])[0]),
                "output_amplitude": float(amp * abs(h)),
            }
        else:
            analysis["sine"] = {"amplitude_ratio": None, "phase_deg": None, "output_amplitude": None}
    out["series"] = series
    out["analysis"] = analysis
    return out


def measured_info(T: TF, t: np.ndarray | None = None) -> dict:
    if not T.is_stable():
        return {"stable": False}
    t = t if t is not None else time_grid(auto_tfinal(T), 2000)
    y = step(T, t)
    info = step_info(t, y, T.dc_gain())
    info["stable"] = True
    return info


def deriv_latex(var: str, k: int) -> str:
    return {0: var, 1: rf"\dot{{{var}}}", 2: rf"\ddot{{{var}}}", 3: rf"\dddot{{{var}}}"}.get(k, f"{var}^{{({k})}}")


def ode_side(coeffs, var: str) -> str:
    n = len(coeffs) - 1
    terms = []
    for i, c in enumerate(coeffs):
        if abs(c) < 1e-12:
            continue
        k = n - i
        mag = "" if abs(abs(c) - 1) < 1e-12 else fmt(abs(c))
        sign = "-" if c < 0 else "+"
        terms.append((sign, f"{mag}{deriv_latex(var, k)}"))
    if not terms:
        return "0"
    s = ("-" if terms[0][0] == "-" else "") + terms[0][1]
    for sign, body in terms[1:]:
        s += f" {sign} {body}"
    return s


# --- a) modelagem ---------------------------------------------------------

def block_info(g: TF) -> dict:
    return {"latex": tf_latex(g.num, g.den), "poles": g.poles(), "zeros": g.zeros(), "unity": is_unity(g)}


def item_a(lp: Loop, p: Params) -> dict:
    g = lp.plant_raw
    A, B, C, D = signal.tf2ss(g.num, g.den)
    n = g.order
    L = lp.open_loop
    T = lp.closed(1.0)
    vec = lambda c: "[" + " ".join(fmt_plain(x, 8) for x in c) + "]"  # noqa: E731
    matlab = [f"G = tf({vec(g.num)}, {vec(g.den)});"]
    if lp.delay:
        matlab += [f"G.InputDelay = {fmt_plain(lp.delay, 8)};", f"G = pade(G, {lp.pade_order});"]
    matlab += [
        f"C = tf({vec(lp.controller.num)}, {vec(lp.controller.den)});",
        f"H = tf({vec(lp.sensor.num)}, {vec(lp.sensor.den)});",
        "L = C*G*H            % malha aberta",
        f"T = feedback(C*G, H{', +1' if lp.sign > 0 else ''})   % malha fechada",
    ]
    out = {
        "order": n,
        "ode": f"{ode_side(g.den, 'y')} = {ode_side(g.num, 'u')}",
        "laplace": rf"\left({poly_latex(g.den)}\right) Y(s) = "
        + ("U(s)" if len(g.num) == 1 and abs(g.num[0] - 1) < 1e-12 else rf"\left({poly_latex(g.num)}\right) U(s)"),
        "tf": rf"G(s) = \frac{{Y(s)}}{{U(s)}} = {tf_latex(g.num, g.den)}" + (rf"\,e^{{-{fmt(lp.delay)}s}}" if lp.delay else ""),
        "state_space": {"A": A, "B": B, "C": C, "D": D},
        "standard": lp.standard,
        "feedback": "negative" if lp.sign < 0 else "positive",
        "blocks": {"plant": block_info(g), "controller": block_info(lp.controller), "sensor": block_info(lp.sensor)},
        "controller_pid": lp.controller_pid,
        "delay": lp.delay,
        "pade": tf_latex(*_pade_parts(lp)) if lp.delay else None,
        "pade_order": lp.pade_order,
        "open_loop": rf"L(s) = C(s)\,G(s)\,H(s) = {tf_latex(L.num, L.den)}",
        "closed_loop": rf"T(s) = {closed_formula(lp, '')} = {tf_latex(T.num, T.den)}",
        "matlab": matlab,
    }
    return out


def _pade_parts(lp: Loop):
    from .loop import pade
    P = pade(lp.delay, lp.pade_order)
    return P.num, P.den


# --- b) constantes do sistema ---------------------------------------------

def item_b(lp: Loop, p: Params) -> dict:
    g = lp.plant_raw
    poles = g.poles()
    n_complex = int(np.sum(np.abs(poles.imag) > 0))
    ordinal = {1: "primeira", 2: "segunda", 3: "terceira", 4: "quarta", 5: "quinta"}.get(g.order, f"{g.order}ª")
    roots_kind = "com raízes complexas" if n_complex else "com raízes reais"
    ge = lp.plant
    t = tgrid(p, ge)
    y = step(ge, t)
    return {
        "delay": lp.delay,
        "den_coeffs": [{"name": f"a_{{{i}}}", "power": g.order - i, "value": float(c)} for i, c in enumerate(g.den) if i > 0],
        "num_coeffs": [{"name": f"b_{{{i}}}", "power": g.num_order - i, "value": float(c)} for i, c in enumerate(g.num)],
        "classification": f"Sistema de {ordinal} ordem {roots_kind}",
        "system_type": g.system_type,
        "relative_degree": g.relative_degree,
        "dc_gain": g.dc_gain(),
        "tf": tf_latex(g.num, g.den),
        "step": {"t": t, "series": {"step": clip_series(y)}},
        "step_behaviour": describe(output_behaviour(ge, 1)),
    }


# --- c) wn e zeta ------------------------------------------------------------

def item_c(lp: Loop, p: Params) -> dict:
    g = lp.open_loop
    poles = g.poles()
    factors = []
    used = [False] * len(poles)
    for i, r in enumerate(poles):
        if used[i]:
            continue
        used[i] = True
        if abs(r.imag) < 1e-12:
            factors.append({
                "kind": "real",
                "pole": float(r.real),
                "latex": "s" if abs(r.real) < 1e-12 else f"({poly_latex([1, -r.real])})",
                "tau": (1.0 / -r.real) if r.real < 0 else None,
            })
        else:
            for j in range(i + 1, len(poles)):
                if not used[j] and abs(poles[j] - np.conj(r)) < 1e-6:
                    used[j] = True
                    break
            wn = abs(r)
            zeta = -r.real / wn
            b, c = 2 * zeta * wn, wn ** 2
            factors.append({
                "kind": "quadratic",
                "poles": [complex(r.real, abs(r.imag)), complex(r.real, -abs(r.imag))],
                "b": b,
                "c": c,
                "wn": wn,
                "zeta": zeta,
                "latex": f"({poly_latex([1, b, c])})",
                "normalized": rf"\frac{{s^2}}{{{fmt(wn)}^2}} + \frac{{2 \cdot {fmt(zeta)}\, s}}{{{fmt(wn)}}} + 1",
            })
    second_order = None
    if g.order == 2:
        a2, a1, a0 = g.den
        if abs(a0) > 1e-12:
            wn = math.sqrt(abs(a0 / a2))
            second_order = {"wn": wn, "zeta": a1 / (2 * math.sqrt(abs(a0 * a2)))}
    dom = dominant_poles(g)
    return {
        "standard": lp.standard,
        "factored": rf"{'G' if lp.standard else 'L'}(s) = \frac{{{factored_latex(g.zeros(), g.zpk_gain)}}}{{{factored_latex(poles)}}}",
        "factors": factors,
        "second_order": second_order,
        "dominant": dom,
        "matlab": ["wn = sqrt(c)", "qsi = b/(2*wn)"],
    }


# --- d) polos -------------------------------------------------------------

def item_d(lp: Loop, p: Params) -> dict:
    g = lp.open_loop
    rows = []
    for r in g.poles():
        wn = abs(r)
        rows.append({
            "value": r,
            "text": complex_str(r),
            "wn": wn,
            "zeta": (-r.real / wn) if wn > 1e-12 else None,
            "tau": (1 / -r.real) if r.real < -1e-12 else None,
            "stable": bool(r.real < -1e-9),
        })
    stable = g.is_stable()
    return {
        "poles": rows,
        "zeros": [{"value": z, "text": complex_str(z)} for z in g.zeros()],
        "gain": g.zpk_gain,
        "stable": stable,
        "routh": routh_table(g.den),
        "standard": lp.standard,
        "blocks": None if lp.standard else {
            "G(s)": [complex_str(x) for x in lp.plant.poles()],
            "C(s)": [complex_str(x) for x in lp.controller.poles()],
            "H(s)": [complex_str(x) for x in lp.sensor.poles()],
        },
        "verdict": "Malha aberta estável: todos os polos no semiplano esquerdo."
        if stable
        else "Malha aberta NÃO estável: há polos sobre o eixo imaginário ou no semiplano direito.",
        "matlab": ["[Zero, Polo, Ganho] = tf2zp(num, den)"],
    }


# --- e) fechar a malha com K -----------------------------------------------

def item_e(lp: Loop, p: Params) -> dict:
    T = lp.closed(p.k)
    t = tgrid(p, T, lp.open_loop)
    y = step(T, t)
    return {
        "K": p.k,
        "closed_loop": tf_info(T),
        "tf": rf"T(s) = {closed_formula(lp)} = {tf_latex(T.num, T.den)}",
        "step": {"t": t, "series": {"step": clip_series(y)}},
        "info": measured_info(T),
        "behaviour": describe(output_behaviour(T, 1)),
        "ess_step": steady_error(T, 1),
        "matlab": [f"K = {fmt_plain(p.k, 8)};", f"FTMF = feedback(K*C*G, H{', +1' if lp.sign > 0 else ''})", "step(FTMF)"],
    }


# --- f) Bode por assíntotas ---------------------------------------------------

def freq_grid(g: TF, extra: list[float] | None = None) -> np.ndarray:
    roots = np.concatenate([g.poles(), g.zeros()])
    mags = [abs(r) for r in roots if abs(r) > 1e-9] + (extra or [])
    lo = min(mags) / 100 if mags else 0.01
    hi = max(mags) * 100 if mags else 100
    lo = 10 ** math.floor(math.log10(lo))
    hi = 10 ** math.ceil(math.log10(hi))
    return np.geomspace(lo, hi, 500)


def bode_corners(g: TF) -> list[dict]:
    corners = []
    for kind, roots, sign in (("zero", g.zeros(), +1), ("polo", g.poles(), -1)):
        used = [False] * len(roots)
        for i, r in enumerate(roots):
            if used[i] or abs(r) < 1e-12:
                continue
            used[i] = True
            if abs(r.imag) < 1e-12:
                corners.append({"w": abs(r.real), "kind": kind, "order": 1, "slope": 20 * sign,
                                "rhp": bool(r.real > 0), "zeta": None,
                                "phase": (90 * sign) * (-1 if r.real > 0 else 1)})
            else:
                for j in range(i + 1, len(roots)):
                    if not used[j] and abs(roots[j] - np.conj(r)) < 1e-6:
                        used[j] = True
                        break
                corners.append({"w": abs(r), "kind": kind, "order": 2, "slope": 40 * sign,
                                "rhp": bool(r.real > 0), "zeta": float(-r.real / abs(r)),
                                "phase": (180 * sign) * (-1 if r.real > 0 else 1)})
    corners.sort(key=lambda c: c["w"])
    return corners


def item_f(lp: Loop, p: Params) -> dict:
    g = lp.open_loop
    N = g.system_type
    kb = g.limit_s_power(N)
    corners = bode_corners(g)
    w = freq_grid(g)
    lw = np.log10(w)
    mag = 20 * math.log10(abs(kb)) - 20 * N * lw
    phase = np.full_like(w, -90.0 * N + (-180.0 if kb < 0 else 0.0))
    for c in corners:
        lc = math.log10(c["w"])
        mag = mag + np.where(lw > lc, c["slope"] * (lw - lc), 0.0)
        if c["order"] == 1:
            frac = np.clip((lw - (lc - 1)) / 2.0, 0.0, 1.0)
        else:
            frac = (lw >= lc).astype(float)
        phase = phase + c["phase"] * frac
    h = g.freq(w)
    exact_mag = 20 * np.log10(np.abs(h))
    exact_phase = g.phase_deg(w)
    low_slope = -20 * N
    rows = []
    slope = low_slope
    for c in corners:
        slope += c["slope"]
        rows.append({**c, "slope_after": slope})
    return {
        "bode_gain": kb,
        "bode_gain_db": 20 * math.log10(abs(kb)),
        "type": N,
        "low_slope": low_slope,
        "corners": rows,
        "bode_form": bode_form_latex(g, kb, N, "G" if lp.standard else "L"),
        "w": w,
        "series": {"mag_asym": mag, "mag": exact_mag, "phase_asym": phase, "phase": exact_phase},
    }


def bode_form_latex(g: TF, kb: float, N: int, name: str = "G") -> str:
    num_f, den_f = [], []
    for kind, roots, target in (("z", g.zeros(), num_f), ("p", g.poles(), den_f)):
        used = [False] * len(roots)
        for i, r in enumerate(roots):
            if used[i]:
                continue
            used[i] = True
            if abs(r) < 1e-12:
                continue
            if abs(r.imag) < 1e-12:
                sgn = "-" if r.real > 0 else "+"
                target.append(rf"\left(1 {sgn} \frac{{s}}{{{fmt(abs(r.real))}}}\right)")
            else:
                for j in range(i + 1, len(roots)):
                    if not used[j] and abs(roots[j] - np.conj(r)) < 1e-6:
                        used[j] = True
                        break
                wn = abs(r)
                z = -r.real / wn
                t1 = "s^2" if abs(wn - 1) < 1e-9 else rf"\frac{{s^2}}{{{fmt(wn ** 2)}}}"
                t2 = rf"{fmt(2 * z)}\,s" if abs(wn - 1) < 1e-9 else rf"\frac{{{fmt(2 * z)}\,s}}{{{fmt(wn)}}}"
                target.append(rf"\left({t1} + {t2} + 1\right)")
    if N > 0:
        den_f.insert(0, "s" if N == 1 else f"s^{{{N}}}")
    elif N < 0:
        num_f.insert(0, "s" if N == -1 else f"s^{{{-N}}}")
    num = "".join(num_f) or "1"
    den = "".join(den_f) or "1"
    return rf"{name}(s) = {fmt(kb)}\,\frac{{{num}}}{{{den}}}"


# --- g) Bode com margens ---------------------------------------------------------

def margins(L: TF) -> dict:
    w = freq_grid(L, [1e-3, 1e3])
    w = np.geomspace(w[0], w[-1], 5000)
    logmag = np.log10(np.abs(L.freq(w)))
    ph = L.phase_deg(w)

    def lm(x):
        return float(np.log10(abs(L.freq([x])[0])))

    def phf(x):
        return float(L.phase_deg([x])[0])

    gc = []
    for i in np.flatnonzero(np.sign(logmag[:-1]) * np.sign(logmag[1:]) < 0):
        gc.append(brentq(lm, w[i], w[i + 1]))
    pc = []
    u = (ph + 180.0) / 360.0
    fl = np.floor(u)
    for i in np.flatnonzero(fl[:-1] != fl[1:]):
        target = -180.0 + 360.0 * max(fl[i], fl[i + 1])
        try:
            pc.append(brentq(lambda x: phf(x) - target, w[i], w[i + 1]))
        except ValueError:
            pass
    pm, wgc = math.inf, None
    for x in gc:
        val = (phf(x) + 180.0 + 180.0) % 360.0 - 180.0
        if abs(val) < abs(pm):
            pm, wgc = val, x
    gm_db, wpc = math.inf, None
    for x in pc:
        val = -20 * lm(x)
        if abs(val) < abs(gm_db):
            gm_db, wpc = val, x
    return {
        "gm_db": gm_db,
        "gm": (10 ** (gm_db / 20)) if np.isfinite(gm_db) else math.inf,
        "wpc": wpc,
        "pm": pm,
        "wgc": wgc,
        "closed_loop_stable": L.feedback(1).is_stable(),
    }


def item_g(lp: Loop, p: Params) -> dict:
    g = lp.open_loop
    geq = lp.loop_eq
    w = freq_grid(g)
    kg = g * p.k
    return {
        "K": p.k,
        "standard": lp.standard,
        "positive_feedback": lp.sign > 0,
        "w": w,
        "series": {
            "mag": 20 * np.log10(np.abs(g.freq(w))),
            "mag_k": 20 * np.log10(np.abs(kg.freq(w))),
            "phase": g.phase_deg(w),
        },
        "margins": margins(geq),
        "margins_k": margins(geq * p.k),
        "matlab": ["L = C*G*H;", "margin(L)", "[Gm, Pm, Wcg, Wcp] = margin(L)"],
    }


# --- h) degrau, impulso e rampa ----------------------------------------------------

def item_h(lp: Loop, p: Params) -> dict:
    g = lp.open_loop
    T = lp.closed(1.0)
    t = tgrid(p, g, T)
    ol = response_set(g, t)
    cl = response_set(T, t)
    for kind, q in (("step", 1), ("ramp", 2), ("impulse", 0)):
        cl["analysis"][kind]["error"] = steady_error(T, q)
    return {"open_loop": ol, "closed_loop": cl, "closed_loop_tf": tf_latex(T.num, T.den), "standard": lp.standard}


# --- i) ganho para cada entrada -----------------------------------------------------

def error_constants(geq: TF) -> dict:
    """Kp, Kv, Ka da malha com realimentação unitária equivalente G_eq."""
    return {"Kp": geq.limit_s_power(0), "Kv": geq.limit_s_power(1), "Ka": geq.limit_s_power(2)}


def item_i(lp: Loop, p: Params) -> dict:
    leq = lp.loop_eq
    intervals = stable_k_intervals(leq.num, leq.den)
    gains = {"step": p.k_step or p.k, "ramp": p.k_ramp or p.k, "impulse": p.k_impulse or p.k}
    out = {"stable_intervals": intervals, "inputs": {}, "unity_feedback": lp.unity_feedback}
    q_of = {"step": 1, "ramp": 2, "impulse": 0}
    for kind, k in gains.items():
        T = lp.closed(k)
        t = tgrid(p, T)
        rs = response_set(T, t, kinds=(kind,))
        rs["analysis"][kind]["error"] = steady_error(T, q_of[kind])
        out["inputs"][kind] = {
            "K": k,
            "tf": tf_latex(T.num, T.den),
            "stable": T.is_stable(),
            "constants": error_constants(lp.equivalent_unity(k)),
            **rs,
        }
    geq1 = lp.equivalent_unity(1.0)
    out["constants_unit"] = error_constants(geq1)
    out["system_type"] = geq1.system_type
    return out


# --- j) lugar das raízes ----------------------------------------------------------------

def item_j(lp: Loop, p: Params) -> dict:
    g = lp.loop_eq
    rl = root_locus(g)
    rl["positive_feedback"] = lp.sign > 0
    rl["stable_intervals"] = stable_k_intervals(g.num, g.den)
    rl["routh_k"] = routh_symbolic(g.num, g.den)
    rl["critical"] = critical_gain(g.num, g.den)
    knum = "K" if len(g.num) == 1 and abs(g.num[0] - 1) < 1e-12 else rf"K\left({poly_latex(g.num)}\right)"
    rl["characteristic"] = rf"{poly_latex(g.den)} + {knum} = 0"
    rl["matlab"] = ["rlocus(C*G*H)" if lp.sign < 0 else "rlocus(-C*G*H)   % realimentação positiva"]
    return rl


# --- k) / l) desempenho transitório --------------------------------------------------------

def transient(T: TF) -> dict:
    dom = dominant_poles(T)
    return {
        "tf": tf_latex(T.num, T.den),
        "poles": T.poles(),
        "dominant": dom,
        "measured": measured_info(T),
        "matlab": [
            "[z, p, k] = tf2zp(num, den);",
            "sigma = abs(real(pd)); wd = abs(imag(pd));",
            "beta = atan(wd/sigma);",
            "Tr = (pi - beta)/wd   % tempo de subida 0-100%",
            "Tp = pi/wd            % tempo de pico",
            "Mp = exp(-sigma*pi/wd)*100   % sobressinal máximo (%)",
            "Ts = 4/sigma          % tempo de acomodação (2%)",
        ],
    }


def item_k(lp: Loop, p: Params) -> dict:
    return transient(lp.open_loop)


def item_l(lp: Loop, p: Params) -> dict:
    return transient(lp.closed(1.0))


# --- m) comparação ---------------------------------------------------------------------

def item_m(lp: Loop, p: Params) -> dict:
    g = lp.open_loop
    T = lp.closed(1.0)
    t = tgrid(p, g, T)
    return {
        "t": t,
        "series": {"open": clip_series(step(g, t)), "closed": clip_series(step(T, t))},
        "open": measured_info(g),
        "closed": measured_info(T),
        "open_dominant": dominant_poles(g),
        "closed_dominant": dominant_poles(T),
    }


# --- n) ação proporcional para erro em regime --------------------------------------

def k_stable(intervals, k: float) -> bool:
    return any(lo <= k and (hi is None or k < hi) for lo, hi in intervals)


def solve_k_for_error(lp: Loop, q: int, target: float, intervals) -> float | None:
    """Menor K > 0 com |e_ss(K)| = alvo, priorizando soluções com malha fechada estável."""
    def f(k):
        v = abs(error_limit(lp.closed(k), q)) - target
        return v if np.isfinite(v) else 1e300

    ks = np.geomspace(1e-6, 1e9, 900)
    fv = np.array([f(k) for k in ks])
    roots = []
    for i in np.flatnonzero(np.sign(fv[:-1]) * np.sign(fv[1:]) < 0):
        if max(abs(fv[i]), abs(fv[i + 1])) >= 1e299:
            continue
        roots.append(float(brentq(f, ks[i], ks[i + 1], xtol=1e-12, rtol=1e-12)))
    if not roots:
        return None
    stable = [k for k in roots if k_stable(intervals, k)]
    return (stable or roots)[0]


def item_n(lp: Loop, p: Params) -> dict:
    e = p.ess_target
    names = {1: "degrau", 2: "rampa", 3: "parábola"}
    # dois ganhos "genéricos" evitam valores de K que anulam o erro por coincidência
    T_a, T_b = lp.closed(0.3719), lp.closed(2.861)
    q = None
    for qq in (1, 2, 3):
        va, vb = error_limit(T_a, qq), error_limit(T_b, qq)
        v = va if np.isfinite(va) and va != 0 else vb
        if va == 0.0 and vb == 0.0:
            continue
        if not np.isfinite(v):
            return {"applicable": False, "reason": f"O erro em regime para entrada {names[qq]} é infinito para qualquer K."}
        q = qq
        break
    if q is None:
        return {"applicable": False, "reason": "Erro nulo para degrau, rampa e parábola (sistema de tipo maior que 2)."}
    N = q - 1
    leq = lp.loop_eq
    intervals = stable_k_intervals(leq.num, leq.den)
    k = None
    if lp.unity_feedback:
        Lf = lp.forward
        const = Lf.limit_s_power(N)
        k = (1.0 / e - 1.0) / const if N == 0 else 1.0 / (e * const)
    if k is not None and k > 0:
        name = "G" if lp.standard else "C G"
        if N == 0:
            formula = rf"e_{{ss}} = \frac{{1}}{{1 + K\,{name}(0)}} \Rightarrow {fmt(e)} = \frac{{1}}{{1 + K \cdot {fmt(const)}}} \Rightarrow K = {fmt(k)}"
            limit = rf"\lim_{{s\to 0}} {name}(s) = {fmt(const)}"
        else:
            cname = "K_v" if N == 1 else "K_a"
            formula = rf"e_{{ss}} = \frac{{1}}{{{cname}}} = \frac{{1}}{{K \lim_{{s\to0}} s^{N} {name}(s)}} \Rightarrow K = {fmt(k)}"
            limit = rf"\lim_{{s\to 0}} s^{{{N}}} {name}(s) = {fmt(const)}"
    else:
        k = solve_k_for_error(lp, q, e, intervals)
        limit = rf"e_{{ss}}(K) = \lim_{{s\to 0}} s\,R(s)\left[1 - T(s)\right],\quad R(s) = \frac{{1}}{{s^{{{q}}}}}"
        formula = (rf"|e_{{ss}}(K)| = {fmt(e)} \Rightarrow K = {fmt(k)}" if k is not None
                   else rf"|e_{{ss}}(K)| = {fmt(e)}\ \text{{não tem solução com }} K > 0")
    out = {
        "applicable": True,
        "input": names[q],
        "target": e,
        "K": k,
        "limit": limit,
        "formula": formula,
        "stable_intervals": intervals,
        "unity_feedback": lp.unity_feedback,
    }
    if k is None or k <= 0:
        out["stable"] = False
        out["warning"] = ("Não existe ganho K > 0 que produza esse erro em regime nesta malha "
                          "(com realimentação não unitária o erro pode ter um limite mínimo).")
        return out
    stable = k_stable(intervals, k)
    T = lp.closed(k)
    t = tgrid(p, T) if stable else time_grid(p.tfinal or 10.0)
    u = t ** N / math.factorial(N)
    y = simulate(T, t, u)
    out.update({
        "stable": stable,
        "tf": tf_latex(T.num, T.den),
        "t": t,
        "series": {"input": u, "output": clip_series(y)},
        "error": steady_error(T, q),
    })
    if not stable:
        first = intervals[0] if intervals and intervals[0][0] == 0 else None
        if first and first[1] is not None:
            kmax = first[1]
            emin = abs(error_limit(lp.closed(kmax * 0.9999), q))
            out["warning"] = (
                f"Com K = {fmt_txt(k)} a malha fechada é INSTÁVEL (estável apenas para 0 < K < {fmt_txt(kmax)}). "
                f"O menor erro alcançável só com ação proporcional é ≈ {fmt_txt(emin * 100)}%. "
                "É necessário um controlador com ação integral (PI/PID) ou compensação."
            )
            out["k_max"] = kmax
            out["e_min"] = emin
        else:
            out["warning"] = f"Com K = {fmt_txt(k)} a malha fechada é INSTÁVEL."
    return out


# --- o) K para Ts e Mp ------------------------------------------------------------------

def item_o(lp: Loop, p: Params) -> dict:
    g = lp.loop_eq
    ts, mp = p.ts_spec, p.mp_spec / 100.0
    lnmp = math.log(mp)
    zeta = -lnmp / math.sqrt(math.pi ** 2 + lnmp ** 2)
    sigma = 4.0 / ts
    wd = -math.pi * sigma / lnmp
    wn = math.sqrt(sigma ** 2 + wd ** 2)
    sd = complex(-sigma, wd)
    gsd = np.polyval(g.num, sd) / np.polyval(g.den, sd)
    angle = math.degrees(np.angle(gsd))
    deficiency = (-180.0 - angle + 180.0) % 360.0 - 180.0
    on_locus = abs(deficiency) < 1.0
    k_at = 1.0 / abs(gsd)

    intervals = stable_k_intervals(g.num, g.den)
    ks_list = []
    for lo, hi in intervals:
        lo_ = max(lo, 1e-4)
        hi_ = hi * 0.999 if hi is not None else max(lo_ * 1e3, 1e3 / max(abs(g.dc_gain()) if np.isfinite(g.dc_gain()) and g.dc_gain() else 1, 1e-6))
        if hi_ > lo_:
            ks_list.append(np.geomspace(lo_, hi_, 120))
    scan = []
    for k in (np.concatenate(ks_list) if ks_list else []):
        T = lp.closed(float(k))
        info = measured_info(T)
        if not info.get("stable"):
            continue
        scan.append({"K": float(k), "ts": info["settling_time"], "mp": info["overshoot"], "tr": info["rise_time"]})
    feasible = [s for s in scan if s["ts"] is not None and s["mp"] is not None and s["ts"] < ts and s["mp"] < p.mp_spec]
    ranges = []
    for s in scan:
        ok = s in feasible
        if ok and (not ranges or ranges[-1][2] is False):
            ranges.append([s["K"], s["K"], True])
        elif ok:
            ranges[-1][1] = s["K"]
        elif ranges and ranges[-1][2]:
            ranges[-1][2] = False
    ranges = [[a, b] for a, b, _ in ranges]
    best = None
    if feasible:
        best = min(feasible, key=lambda s: s["ts"])
    else:
        mp_ok = [s for s in scan if s["mp"] is not None and s["mp"] < p.mp_spec and s["ts"] is not None]
        if mp_ok:
            best = min(mp_ok, key=lambda s: s["ts"])
    resp = None
    if best:
        T = lp.closed(best["K"])
        t = tgrid(p, T)
        resp = {"t": t, "series": {"step": step(T, t)}, "tf": tf_latex(T.num, T.den), "poles": T.poles()}
    return {
        "ts_spec": ts,
        "mp_spec": p.mp_spec,
        "zeta": zeta,
        "sigma": sigma,
        "wd": wd,
        "wn": wn,
        "desired_poles": [sd, sd.conjugate()],
        "desired_poly": poly_latex([1, 2 * sigma, wn ** 2]),
        "desired_tf": rf"\frac{{{fmt(wn ** 2)}}}{{s^2 + {fmt(2 * sigma)}s + {fmt(wn ** 2)}}}",
        "angle_at_desired": angle,
        "angle_deficiency": deficiency,
        "on_locus": on_locus,
        "k_at_desired": k_at if on_locus else None,
        "scan": scan,
        "feasible": bool(feasible),
        "feasible_ranges": ranges,
        "best": best,
        "response": resp,
    }


# --- p) Ziegler-Nichols 1º método ----------------------------------------------------

SIMULINK_N = 100.0  # coeficiente do filtro derivativo padrão do bloco PID do Simulink

ZN1_RULES = [
    {"controller": "P", "Kp": "T/L", "Ti": r"\infty", "Td": "0"},
    {"controller": "PI", "Kp": r"0{,}9\,T/L", "Ti": "L/0{,}3", "Td": "0"},
    {"controller": "PID", "Kp": r"1{,}2\,T/L", "Ti": "2L", "Td": "0{,}5L"},
]
ZN2_RULES = [
    {"controller": "P", "Kp": "0{,}5K_u", "Ti": r"\infty", "Td": "0"},
    {"controller": "PI", "Kp": "0{,}45K_u", "Ti": "P_u/1{,}2", "Td": "0"},
    {"controller": "PID", "Kp": "0{,}6K_u", "Ti": "0{,}5P_u", "Td": "0{,}125P_u"},
]


def controllers_response(lp: Loop, table: list[dict], p: Params) -> dict:
    closed = {}
    systems = []
    for row in table:
        c = pid_tf(row["Kp"], row["Ki"] or 0.0, row["Kd"] or 0.0, lp.plant)
        T = lp.with_controller(c).closed(1.0)
        systems.append(T)
        closed[row["controller"]] = {
            "controller_tf": tf_latex(c.num, c.den),
            "tf": tf_latex(T.num, T.den),
            "stable": T.is_stable(),
            "info": measured_info(T),
        }
    t = tgrid(p, *[s for s in systems if s.is_stable()] or systems)
    series = {}
    for row, T in zip(table, systems):
        series[row["controller"]] = clip_series(step(T, t))
    return {"closed": closed, "t": t, "series": series}


def pid_rows(kp_p, kp_pi, ti_pi, kp_pid, ti_pid, td_pid) -> list[dict]:
    return [
        {"controller": "P", "Kp": kp_p, "Ki": None, "Kd": None, "Ti": None, "Td": None},
        {"controller": "PI", "Kp": kp_pi, "Ki": kp_pi / ti_pi, "Kd": None, "Ti": ti_pi, "Td": None},
        {"controller": "PID", "Kp": kp_pid, "Ki": kp_pid / ti_pid, "Kd": kp_pid * td_pid, "Ti": ti_pid, "Td": td_pid},
    ]


def item_p(lp: Loop, p: Params) -> dict:
    g = lp.process()
    if not g.is_stable() or g.system_type != 0:
        return {"applicable": False, "rules": ZN1_RULES,
                "reason": "O 1º método exige uma planta estável sem integrador (resposta ao degrau em forma de S). "
                          "Use o 2º método (ganho crítico)."}
    dc = g.dc_gain()
    t = time_grid(p.tfinal or auto_tfinal(g), 4000)
    y = step(g, t)
    dy = impulse(g, t) * np.sign(dc)
    i = int(np.argmax(dy))
    m = float(dy[i]) * np.sign(dc)
    if abs(m) < 1e-12:
        return {"applicable": False, "rules": ZN1_RULES, "reason": "Não foi possível determinar a reta tangente."}
    L = float(t[i] - y[i] / m)
    T = float((dc - y[i]) / m + t[i] - L)
    if L <= 1e-4 * t[-1]:
        return {"applicable": False, "rules": ZN1_RULES,
                "reason": "A resposta ao degrau não tem formato de S (atraso L ≈ 0, como em sistemas de 1ª ordem). "
                          "As regras resultariam em ganhos infinitos."}
    kproc = abs(dc) if p.zn_include_gain else 1.0
    base = T / (kproc * L)
    table = pid_rows(base, 0.9 * base, L / 0.3, 1.2 * base, 2 * L, 0.5 * L)
    info = step_info(t, y, dc)
    warnings = []
    if info["overshoot"] and info["overshoot"] > 2:
        warnings.append(
            f"A resposta da planta tem sobressinal de {fmt_txt(info['overshoot'])}% — não é uma curva em S pura, "
            "então o 1º método é apenas uma aproximação."
        )
    return {
        "applicable": True,
        "rules": ZN1_RULES,
        "L": L,
        "T": T,
        "process_gain": dc,
        "gain_included": p.zn_include_gain,
        "inflection": {"t": float(t[i]), "y": float(y[i]), "slope": m},
        "plant": {"t": t[::4], "series": {"step": y[::4]}},
        "tangent": [[L, 0.0], [L + T, dc]],
        "table": table,
        "warnings": warnings,
        "process_is_plant": is_unity(lp.sensor),
        **controllers_response(lp, table, p),
    }


# --- q) Ziegler-Nichols 2º método -----------------------------------------------------

def item_q(lp: Loop, p: Params) -> dict:
    g = lp.process_eq()
    crit = critical_gain(g.num, g.den)
    if not crit or not crit.get("Pu"):
        return {"applicable": False, "rules": ZN2_RULES,
                "reason": "O sistema não apresenta oscilação sustentada para nenhum ganho proporcional "
                          "(o lugar das raízes não cruza o eixo imaginário), então não existe Ku."}
    ku, pu, wu = crit["Ku"], crit["Pu"], crit["wu"]
    table = pid_rows(0.5 * ku, 0.45 * ku, pu / 1.2, 0.6 * ku, 0.5 * pu, 0.125 * pu)
    Tku = lp.with_controller(TF([ku], [1.0])).closed(1.0)
    t = time_grid(p.tfinal or max(10 * pu, 10.0))
    return {
        "applicable": True,
        "rules": ZN2_RULES,
        "Ku": ku,
        "Pu": pu,
        "wu": wu,
        "oscillation": {"t": t, "series": {"step": clip_series(step(Tku, t))}},
        "table": table,
        **controllers_response(lp, table, p),
    }


# --- r) média dos parâmetros ------------------------------------------------------------

def item_r(lp: Loop, p: Params, zn1: dict, zn2: dict) -> dict:
    sources = [s for s in (zn1, zn2) if s.get("applicable")]
    if not sources:
        return {"applicable": False, "reason": "Nenhum dos métodos de Ziegler-Nichols é aplicável a esta planta."}
    avg = {}
    for ctrl in ("P", "PI", "PID"):
        rows = [next(r for r in s["table"] if r["controller"] == ctrl) for s in sources]
        avg[ctrl] = {
            k: (float(np.mean([r[k] for r in rows])) if rows[0][k] is not None else None) for k in ("Kp", "Ki", "Kd")
        }
    pid = avg["PID"]
    # mesma forma do bloco PID Controller do Simulink usado no trabalho: P + I/s + D·N·s/(s+N), N = 100
    c = pid_tf(pid["Kp"], pid["Ki"], pid["Kd"], lp.plant, n_filter=SIMULINK_N, filtered=True)
    T = lp.with_controller(c).closed(1.0)
    t = tgrid(p, T)
    resp = response_set(T, t, kinds=("step", "ramp"), sine=(p.sine_amp, p.sine_freq))
    for kind, q in (("step", 1), ("ramp", 2)):
        resp["analysis"][kind]["error"] = steady_error(T, q)
    return {
        "applicable": True,
        "sources": ["1º método" if s is zn1 else "2º método" for s in sources],
        "average": avg,
        "controller_tf": tf_latex(c.num, c.den),
        "tf": tf_latex(T.num, T.den),
        "stable": T.is_stable(),
        "info": measured_info(T),
        "sine": {"amp": p.sine_amp, "freq": p.sine_freq},
        "n_filter": SIMULINK_N,
        "sensor_unity": is_unity(lp.sensor),
        "sensor_tf": tf_latex(lp.sensor.num, lp.sensor.den),
        "positive_feedback": lp.sign > 0,
        **resp,
    }
