"""Função de transferência SISO e utilitários de simulação.

Substitui os comandos do MATLAB usados no trabalho original
(tf, feedback, tf2zp, step, impulse, lsim, ...).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import signal

TOL = 1e-9
N_POINTS = 600


def trim(p) -> np.ndarray:
    """Remove zeros à esquerda de um polinômio (maior potência primeiro)."""
    p = np.atleast_1d(np.asarray(p, dtype=float))
    nz = np.flatnonzero(np.abs(p) > 1e-14)
    if nz.size == 0:
        return np.array([0.0])
    return p[nz[0]:]


def padd(a, b) -> np.ndarray:
    return trim(np.polyadd(trim(a), trim(b)))


def pmul(a, b) -> np.ndarray:
    return trim(np.polymul(trim(a), trim(b)))


def peval(p, s):
    return np.polyval(p, s)


@dataclass
class TF:
    num: np.ndarray
    den: np.ndarray

    def __post_init__(self):
        num = trim(self.num)
        den = trim(self.den)
        if np.allclose(den, 0):
            raise ValueError("O denominador não pode ser nulo.")
        lead = den[0]
        self.num = num / lead
        self.den = den / lead

    # --- construção -----------------------------------------------------
    @classmethod
    def gain(cls, k: float) -> "TF":
        return cls([k], [1.0])

    def __mul__(self, other) -> "TF":
        if isinstance(other, (int, float)):
            return TF(self.num * other, self.den)
        return TF(pmul(self.num, other.num), pmul(self.den, other.den))

    __rmul__ = __mul__

    def feedback(self, h: "TF | float" = 1.0) -> "TF":
        """Malha fechada com realimentação negativa: G / (1 + G H)."""
        if isinstance(h, (int, float)):
            h = TF.gain(float(h))
        num = pmul(self.num, h.den)
        den = padd(pmul(self.den, h.den), pmul(self.num, h.num))
        return TF(num, den)

    # --- propriedades ---------------------------------------------------
    @property
    def order(self) -> int:
        return len(self.den) - 1

    @property
    def num_order(self) -> int:
        return 0 if np.allclose(self.num, 0) else len(self.num) - 1

    @property
    def relative_degree(self) -> int:
        return self.order - self.num_order

    @property
    def is_proper(self) -> bool:
        return self.relative_degree >= 0

    def poles(self) -> np.ndarray:
        return clean_roots(np.roots(self.den)) if self.order > 0 else np.array([])

    def zeros(self) -> np.ndarray:
        return clean_roots(np.roots(self.num)) if self.num_order > 0 else np.array([])

    @property
    def zpk_gain(self) -> float:
        return float(self.num[0])

    @property
    def system_type(self) -> int:
        """Número de polos na origem (tipo do sistema)."""
        n = 0
        for c in self.den[::-1]:
            if abs(c) < 1e-12:
                n += 1
            else:
                break
        z = 0
        for c in self.num[::-1]:
            if abs(c) < 1e-12:
                z += 1
            else:
                break
        return n - z

    def dc_gain(self) -> float:
        """lim s->0 G(s) (inf se houver polo na origem)."""
        t = self.system_type
        if t > 0:
            return math.inf
        if t < 0:
            return 0.0
        return float(self.num[-1] / self.den[-1])

    def limit_s_power(self, k: int) -> float:
        """lim s->0 s^k G(s) — usado nas constantes de erro Kp, Kv, Ka."""
        t = self.system_type
        if t > k:
            return math.inf
        if t < k:
            return 0.0
        n = np.trim_zeros(self.num, "b")
        d = np.trim_zeros(self.den, "b")
        return float(n[-1] / d[-1])

    def freq(self, w) -> np.ndarray:
        s = 1j * np.asarray(w, dtype=float)
        return peval(self.num, s) / peval(self.den, s)

    def phase_deg(self, w) -> np.ndarray:
        """Fase contínua (sem saltos de 360°) a partir das contribuições de polos e zeros."""
        w = np.asarray(w, dtype=float)
        s = 1j * w
        ph = np.zeros_like(w)
        for z in self.zeros():
            ph += np.angle(s - z)
        for p in self.poles():
            ph -= np.angle(s - p)
        ph = np.degrees(ph)
        if self.zpk_gain < 0:
            ph -= 180.0
        return ph

    def is_stable(self) -> bool:
        p = self.poles()
        return bool(np.all(p.real < -1e-9)) if p.size else True

    def strictly_proper(self) -> bool:
        return self.relative_degree >= 1


def clean_roots(r: np.ndarray) -> np.ndarray:
    r = np.asarray(r, dtype=complex)
    re = np.where(np.abs(r.real) < 1e-9, 0.0, r.real)
    im = np.where(np.abs(r.imag) < 1e-7 * np.maximum(1, np.abs(r)), 0.0, r.imag)
    out = re + 1j * im
    return out[np.lexsort((out.imag, -out.real))]


# --- simulação ----------------------------------------------------------

def auto_tfinal(*systems: TF, minimum: float = 5.0, maximum: float = 300.0) -> float:
    t = minimum
    for g in systems:
        p = g.poles()
        stable = p[p.real < -1e-6]
        if stable.size:
            slowest = np.min(np.abs(stable.real))
            t = max(t, 6.0 / slowest)
            osc = np.abs(stable.imag)
            if np.any(osc > 0):
                t = max(t, 3 * 2 * math.pi / np.max(osc))
        if np.any(p.real > 1e-6):
            fastest_unstable = np.max(p.real[p.real > 1e-6])
            t = min(t, max(minimum, 8.0 / fastest_unstable))
    return float(min(t, maximum))


def time_grid(tfinal: float, n: int = N_POINTS) -> np.ndarray:
    return np.linspace(0.0, tfinal, n)


def simulate(g: TF, t: np.ndarray, u: np.ndarray) -> np.ndarray:
    if not g.is_proper:
        raise ValueError("Sistema impróprio (grau do numerador maior que o do denominador).")
    sys = signal.lti(g.num, g.den)
    _, y, _ = signal.lsim(sys, U=u, T=t)
    return np.asarray(y, dtype=float)


def step(g: TF, t: np.ndarray) -> np.ndarray:
    return simulate(g, t, np.ones_like(t))


def ramp(g: TF, t: np.ndarray) -> np.ndarray:
    return simulate(g, t, t.copy())


def impulse(g: TF, t: np.ndarray) -> np.ndarray:
    if g.relative_degree == 0:
        # parte própria: impulso em t=0 não representável; usa a parte estritamente própria
        d0 = g.num[0] if len(g.num) == len(g.den) else 0.0
        rest = TF(padd(g.num, -d0 * g.den), g.den)
        return impulse(rest, t)
    sys = signal.lti(g.num, g.den)
    _, y = signal.impulse(sys, T=t)
    return np.asarray(y, dtype=float)


# --- desempenho --------------------------------------------------------

def step_info(t: np.ndarray, y: np.ndarray, final: float | None, settle: float = 0.02) -> dict:
    """Equivalente ao stepinfo do MATLAB (medido na curva simulada)."""
    info = {
        "final_value": final,
        "rise_time": None,
        "peak_time": None,
        "peak": None,
        "overshoot": None,
        "settling_time": None,
    }
    if final is None or not np.isfinite(final) or abs(final) < 1e-12:
        return info
    yn = y / final
    k_peak = int(np.argmax(yn))
    info["peak"] = float(y[k_peak])
    info["peak_time"] = float(t[k_peak])
    info["overshoot"] = float(max(0.0, (yn[k_peak] - 1.0) * 100.0))

    def cross(level):
        idx = np.flatnonzero(yn >= level)
        if idx.size == 0:
            return None
        i = idx[0]
        if i == 0:
            return float(t[0])
        t0, t1, y0, y1 = t[i - 1], t[i], yn[i - 1], yn[i]
        return float(t0 + (level - y0) * (t1 - t0) / (y1 - y0))

    t10, t90 = cross(0.1), cross(0.9)
    if t10 is not None and t90 is not None:
        info["rise_time"] = t90 - t10
    outside = np.flatnonzero(np.abs(yn - 1.0) > settle)
    if outside.size == 0:
        info["settling_time"] = float(t[0])
    elif outside[-1] < len(t) - 1:
        info["settling_time"] = float(t[outside[-1] + 1])
    if info["overshoot"] is not None and info["overshoot"] < 1e-6:
        info["peak_time"] = None
    return info


def dominant_poles(g: TF) -> dict | None:
    """Polo(s) dominante(s): os mais próximos do eixo imaginário."""
    p = g.poles()
    if p.size == 0:
        return None
    k = int(np.argmax(p.real))
    pd = p[k]
    if abs(pd.imag) > 0:
        pd = complex(pd.real, abs(pd.imag))
    return analytic_second_order(pd)


def analytic_second_order(pd: complex) -> dict:
    """Parâmetros de desempenho pelas fórmulas clássicas (Ogata) a partir do polo dominante."""
    sigma = -pd.real
    wd = abs(pd.imag)
    out: dict = {"pole": pd, "sigma": sigma, "wd": wd, "complex": wd > 0}
    if sigma <= 0:
        out["stable"] = False
        return out
    out["stable"] = True
    if wd > 0:
        wn = abs(pd)
        zeta = sigma / wn
        beta = math.acos(zeta)
        out.update(
            wn=wn,
            zeta=zeta,
            beta=beta,
            rise_time=(math.pi - beta) / wd,
            peak_time=math.pi / wd,
            overshoot=100.0 * math.exp(-sigma * math.pi / wd),
            settling_time_2=4.0 / sigma,
            settling_time_5=3.0 / sigma,
        )
    else:
        tau = 1.0 / sigma
        out.update(
            wn=sigma,
            zeta=1.0,
            tau=tau,
            rise_time=2.197 * tau,
            peak_time=None,
            overshoot=0.0,
            settling_time_2=4.0 * tau,
            settling_time_5=3.0 * tau,
        )
    return out


def final_value(num, den) -> dict:
    """Teorema do valor final aplicado a Y(s)=num/den. Classifica o comportamento."""
    # sY(s)
    num = pmul(num, [1.0, 0.0])
    den = trim(den)
    while len(num) > 1 and len(den) > 1 and abs(num[-1]) < 1e-14 and abs(den[-1]) < 1e-14:
        num, den = num[:-1], den[:-1]
    r = clean_roots(np.roots(den)) if len(den) > 1 else np.array([])
    if np.any(r.real > 1e-7):
        return {"kind": "diverge", "value": None}
    at_origin = np.sum(np.abs(r) < 1e-7)
    if at_origin > 0:
        return {"kind": "unbounded", "value": None}
    if np.any((np.abs(r.real) <= 1e-7) & (np.abs(r.imag) > 1e-7)):
        return {"kind": "oscillates", "value": None}
    return {"kind": "settles", "value": float(peval(num, 0.0) / peval(den, 0.0))}
