"""Itens a) a r) do Trabalho de Controle II, generalizados para qualquer planta G(s)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal
from scipy.optimize import brentq

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


def pid_tf(kp: float, ki: float = 0.0, kd: float = 0.0, g: TF | None = None, n_filter: float = 100.0) -> TF:
    """C(s) = Kp + Ki/s + Kd s (derivada filtrada se a malha fechada ficaria imprópria)."""
    if kd and g is not None and g.relative_degree < 1:
        # Kd N s/(s+N)
        num = padd(pmul([kp], [1, n_filter]), [kd * n_filter, 0])
        den = np.array([1.0, n_filter])
        c = TF(num, den)
        if ki:
            c = TF(padd(pmul(c.num, [1, 0]), pmul([ki], c.den)), pmul(c.den, [1, 0]))
        return c
    if ki:
        return TF([kd, kp, ki], [1.0, 0.0])
    return TF([kd, kp], [1.0])


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

def item_a(g: TF, p: Params) -> dict:
    A, B, C, D = signal.tf2ss(g.num, g.den)
    n = g.order
    a_sym = " + ".join(
        [f"s^{{{n}}}"] + [f"a_{{{i}}}" + (f"s^{{{n - i}}}" if n - i > 1 else ("s" if n - i == 1 else "")) for i in range(1, n + 1)]
    )
    return {
        "order": n,
        "ode_generic": rf"y^{{({n})}} + a_1 y^{{({n - 1})}} + \dots + a_{{{n}}} y = u" if n > 3 else None,
        "tf_generic": rf"\frac{{Y(s)}}{{U(s)}} = \frac{{N(s)}}{{{a_sym}}}",
        "ode": f"{ode_side(g.den, 'y')} = {ode_side(g.num, 'u')}",
        "laplace": rf"\left({poly_latex(g.den)}\right) Y(s) = "
        + ("U(s)" if len(g.num) == 1 and abs(g.num[0] - 1) < 1e-12 else rf"\left({poly_latex(g.num)}\right) U(s)"),
        "tf": rf"G(s) = \frac{{Y(s)}}{{U(s)}} = {tf_latex(g.num, g.den)}",
        "state_space": {"A": A, "B": B, "C": C, "D": D},
        "matlab": [f"num = [{' '.join(fmt_plain(c, 8) for c in g.num)}];", f"den = [{' '.join(fmt_plain(c, 8) for c in g.den)}];", "G = tf(num, den)"],
    }


# --- b) constantes do sistema ---------------------------------------------

def item_b(g: TF, p: Params) -> dict:
    poles = g.poles()
    n_complex = int(np.sum(np.abs(poles.imag) > 0))
    ordinal = {1: "primeira", 2: "segunda", 3: "terceira", 4: "quarta", 5: "quinta"}.get(g.order, f"{g.order}ª")
    roots_kind = "com raízes complexas" if n_complex else "com raízes reais"
    t = tgrid(p, g)
    y = step(g, t)
    return {
        "den_coeffs": [{"name": f"a_{{{i}}}", "power": g.order - i, "value": float(c)} for i, c in enumerate(g.den) if i > 0],
        "num_coeffs": [{"name": f"b_{{{i}}}", "power": g.num_order - i, "value": float(c)} for i, c in enumerate(g.num)],
        "classification": f"Sistema de {ordinal} ordem {roots_kind}",
        "system_type": g.system_type,
        "relative_degree": g.relative_degree,
        "dc_gain": g.dc_gain(),
        "tf": tf_latex(g.num, g.den),
        "step": {"t": t, "series": {"step": clip_series(y)}},
        "step_behaviour": describe(output_behaviour(g, 1)),
    }


# --- c) wn e zeta ------------------------------------------------------------

def item_c(g: TF, p: Params) -> dict:
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
        "factored": rf"G(s) = \frac{{{factored_latex(g.zeros(), g.zpk_gain)}}}{{{factored_latex(poles)}}}",
        "factors": factors,
        "second_order": second_order,
        "dominant": dom,
        "matlab": ["wn = sqrt(c)", "qsi = b/(2*wn)"],
    }


# --- d) polos -------------------------------------------------------------

def item_d(g: TF, p: Params) -> dict:
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
        "verdict": "Planta estável em malha aberta: todos os polos no semiplano esquerdo."
        if stable
        else "Planta NÃO estável em malha aberta: há polos sobre o eixo imaginário ou no semiplano direito.",
        "matlab": ["[Zero, Polo, Ganho] = tf2zp(num, den)"],
    }


# --- e) fechar a malha com K -----------------------------------------------

def item_e(g: TF, p: Params) -> dict:
    T = (g * p.k).feedback(1)
    t = tgrid(p, T, g)
    y = step(T, t)
    return {
        "K": p.k,
        "closed_loop": tf_info(T),
        "tf": rf"T(s) = \frac{{K G(s)}}{{1 + K G(s)}} = {tf_latex(T.num, T.den)}",
        "step": {"t": t, "series": {"step": clip_series(y)}},
        "info": measured_info(T),
        "behaviour": describe(output_behaviour(T, 1)),
        "ess_step": steady_error(T, 1),
        "matlab": [f"K = {fmt_plain(p.k, 8)};", "FTMF = feedback(K*G, 1)", "step(FTMF)"],
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


def item_f(g: TF, p: Params) -> dict:
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
        "bode_form": bode_form_latex(g, kb, N),
        "w": w,
        "series": {"mag_asym": mag, "mag": exact_mag, "phase_asym": phase, "phase": exact_phase},
    }


def bode_form_latex(g: TF, kb: float, N: int) -> str:
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
    return rf"G(s) = {fmt(kb)}\,\frac{{{num}}}{{{den}}}"


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


def item_g(g: TF, p: Params) -> dict:
    w = freq_grid(g)
    kg = g * p.k
    return {
        "K": p.k,
        "w": w,
        "series": {
            "mag": 20 * np.log10(np.abs(g.freq(w))),
            "mag_k": 20 * np.log10(np.abs(kg.freq(w))),
            "phase": g.phase_deg(w),
        },
        "margins": margins(g),
        "margins_k": margins(kg),
        "matlab": ["margin(G)", "[Gm, Pm, Wcg, Wcp] = margin(G)"],
    }


# --- h) degrau, impulso e rampa ----------------------------------------------------

def item_h(g: TF, p: Params) -> dict:
    T = g.feedback(1)
    t = tgrid(p, g, T)
    ol = response_set(g, t)
    cl = response_set(T, t)
    for kind, q in (("step", 1), ("ramp", 2), ("impulse", 0)):
        cl["analysis"][kind]["error"] = steady_error(T, q)
    return {"open_loop": ol, "closed_loop": cl, "closed_loop_tf": tf_latex(T.num, T.den)}


# --- i) ganho para cada entrada -----------------------------------------------------

def error_constants(g: TF, k: float = 1.0) -> dict:
    kg = g * k
    return {"Kp": kg.limit_s_power(0), "Kv": kg.limit_s_power(1), "Ka": kg.limit_s_power(2)}


def item_i(g: TF, p: Params) -> dict:
    intervals = stable_k_intervals(g.num, g.den)
    gains = {"step": p.k_step or p.k, "ramp": p.k_ramp or p.k, "impulse": p.k_impulse or p.k}
    out = {"stable_intervals": intervals, "inputs": {}}
    q_of = {"step": 1, "ramp": 2, "impulse": 0}
    for kind, k in gains.items():
        T = (g * k).feedback(1)
        t = tgrid(p, T)
        rs = response_set(T, t, kinds=(kind,))
        rs["analysis"][kind]["error"] = steady_error(T, q_of[kind])
        out["inputs"][kind] = {
            "K": k,
            "tf": tf_latex(T.num, T.den),
            "stable": T.is_stable(),
            "constants": error_constants(g, k),
            **rs,
        }
    out["constants_unit"] = error_constants(g, 1.0)
    out["system_type"] = g.system_type
    return out


# --- j) lugar das raízes ----------------------------------------------------------------

def item_j(g: TF, p: Params) -> dict:
    rl = root_locus(g)
    rl["stable_intervals"] = stable_k_intervals(g.num, g.den)
    rl["routh_k"] = routh_symbolic(g.num, g.den)
    rl["critical"] = critical_gain(g.num, g.den)
    knum = "K" if len(g.num) == 1 and abs(g.num[0] - 1) < 1e-12 else rf"K\left({poly_latex(g.num)}\right)"
    rl["characteristic"] = rf"{poly_latex(g.den)} + {knum} = 0"
    rl["matlab"] = ["rlocus(G)"]
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


def item_k(g: TF, p: Params) -> dict:
    return transient(g)


def item_l(g: TF, p: Params) -> dict:
    return transient(g.feedback(1))


# --- m) comparação ---------------------------------------------------------------------

def item_m(g: TF, p: Params) -> dict:
    T = g.feedback(1)
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


def item_n(g: TF, p: Params) -> dict:
    e = p.ess_target
    N = max(g.system_type, 0)
    names = {0: "degrau", 1: "rampa", 2: "parábola"}
    if N > 2:
        return {"applicable": False, "reason": "Sistema de tipo maior que 2: erro nulo para degrau, rampa e parábola."}
    const = g.limit_s_power(N)
    if N == 0:
        k = (1.0 / e - 1.0) / const
        formula = rf"e_{{ss}} = \frac{{1}}{{1 + K\,G(0)}} \Rightarrow {fmt(e)} = \frac{{1}}{{1 + K \cdot {fmt(const)}}} \Rightarrow K = {fmt(k)}"
        limit = rf"\lim_{{s\to 0}} G(s) = {fmt(const)}"
    else:
        k = 1.0 / (e * const)
        cname = "K_v" if N == 1 else "K_a"
        formula = rf"e_{{ss}} = \frac{{1}}{{{cname}}} = \frac{{1}}{{K \lim_{{s\to0}} s^{N} G(s)}} \Rightarrow K = {fmt(k)}"
        limit = rf"\lim_{{s\to 0}} s^{{{N}}} G(s) = {fmt(const)}"
    intervals = stable_k_intervals(g.num, g.den)
    stable = k > 0 and k_stable(intervals, k)
    T = (g * k).feedback(1)
    t = tgrid(p, T) if stable else time_grid(p.tfinal or 10.0)
    q = N + 1
    u = t ** N / math.factorial(N)
    y = simulate(T, t, u)
    out = {
        "applicable": True,
        "input": names[N],
        "target": e,
        "K": k,
        "limit": limit,
        "formula": formula,
        "stable": stable,
        "stable_intervals": intervals,
        "tf": tf_latex(T.num, T.den),
        "t": t,
        "series": {"input": u, "output": clip_series(y)},
        "error": steady_error(T, q),
    }
    if N == 0 and k < 0:
        out["warning"] = "O ganho calculado é negativo: o ganho DC da planta é negativo ou o erro alvo é maior que o erro com K=0."
    if not stable and k > 0:
        first = intervals[0] if intervals and intervals[0][0] == 0 else None
        if first and first[1] is not None:
            kmax = first[1]
            if N == 0:
                emin = 1.0 / (1.0 + kmax * const)
            else:
                emin = 1.0 / (kmax * const)
            out["warning"] = (
                f"Com K = {fmt_txt(k)} a malha fechada é INSTÁVEL (estável apenas para 0 < K < {fmt_txt(kmax)}). "
                f"O menor erro alcançável só com ação proporcional é ≈ {fmt_txt(emin * 100)}%. "
                "É necessário um controlador com ação integral (PI/PID) ou compensação."
            )
            out["k_max"] = kmax
            out["e_min"] = emin
    return out


# --- o) K para Ts e Mp ------------------------------------------------------------------

def item_o(g: TF, p: Params) -> dict:
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
        T = (g * k).feedback(1)
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
        T = (g * best["K"]).feedback(1)
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


def controllers_response(g: TF, table: list[dict], p: Params) -> dict:
    closed = {}
    systems = []
    for row in table:
        c = pid_tf(row["Kp"], row["Ki"] or 0.0, row["Kd"] or 0.0, g)
        T = (c * g).feedback(1)
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


def item_p(g: TF, p: Params) -> dict:
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
        **controllers_response(g, table, p),
    }


# --- q) Ziegler-Nichols 2º método -----------------------------------------------------

def item_q(g: TF, p: Params) -> dict:
    crit = critical_gain(g.num, g.den)
    if not crit or not crit.get("Pu"):
        return {"applicable": False, "rules": ZN2_RULES,
                "reason": "O sistema não apresenta oscilação sustentada para nenhum ganho proporcional "
                          "(o lugar das raízes não cruza o eixo imaginário), então não existe Ku."}
    ku, pu, wu = crit["Ku"], crit["Pu"], crit["wu"]
    table = pid_rows(0.5 * ku, 0.45 * ku, pu / 1.2, 0.6 * ku, 0.5 * pu, 0.125 * pu)
    Tku = (g * ku).feedback(1)
    t = time_grid(p.tfinal or max(10 * pu, 10.0))
    return {
        "applicable": True,
        "rules": ZN2_RULES,
        "Ku": ku,
        "Pu": pu,
        "wu": wu,
        "oscillation": {"t": t, "series": {"step": clip_series(step(Tku, t))}},
        "table": table,
        **controllers_response(g, table, p),
    }


# --- r) média dos parâmetros ------------------------------------------------------------

def item_r(g: TF, p: Params, zn1: dict, zn2: dict) -> dict:
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
    c = pid_tf(pid["Kp"], pid["Ki"], pid["Kd"], g)
    T = (c * g).feedback(1)
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
        **resp,
    }
