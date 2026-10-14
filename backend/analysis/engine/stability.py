"""Critério de Routh-Hurwitz, lugar das raízes e faixas de ganho estável."""

from __future__ import annotations

import math

import numpy as np
import sympy as sp
from scipy.optimize import linear_sum_assignment

from .formatting import fmt
from .tf import TF, clean_roots, padd, pmul, trim


# --- Routh-Hurwitz -----------------------------------------------------

def routh_table(coeffs, eps: float = 1e-6) -> dict:
    c = trim(coeffs)
    if c[0] < 0:
        c = -c
    n = len(c) - 1
    cols = n // 2 + 1
    table = np.zeros((n + 1, cols))
    first = c[0::2]
    second = c[1::2]
    table[0, : len(first)] = first
    table[1, : len(second)] = second if n >= 1 else []
    notes: list[str] = []
    for i in range(2, n + 1):
        prev = table[i - 1]
        if np.all(np.abs(prev) < 1e-12):
            order = n - (i - 2)
            aux = table[i - 2]
            for j in range(cols):
                table[i - 1, j] = aux[j] * (order - 2 * j)
            notes.append(
                f"Linha s^{n - i + 1} nula: substituída pela derivada do polinômio auxiliar "
                f"(raízes simétricas em relação à origem)."
            )
        elif abs(prev[0]) < 1e-12:
            table[i - 1, 0] = eps
            notes.append(f"Zero na primeira coluna da linha s^{n - i + 1} substituído por ε.")
        for j in range(cols - 1):
            a, b = table[i - 1, 0], table[i - 2, 0]
            table[i, j] = (a * table[i - 2, j + 1] - b * table[i - 1, j + 1]) / a
    col = table[:, 0]
    signs = np.sign(np.where(np.abs(col) < 1e-12, eps, col))
    changes = int(np.sum(signs[1:] != signs[:-1]))
    return {
        "rows": [
            {"power": n - i, "values": [float(v) for v in table[i]]} for i in range(n + 1)
        ],
        "sign_changes": changes,
        "notes": notes,
        "stable": changes == 0 and not notes,
    }


def routh_symbolic(num, den) -> dict | None:
    """Primeira coluna de Routh para den(s) + K num(s), em função de K."""
    K, s = sp.symbols("K s")
    num = trim(num)
    den = trim(den)
    nn = np.zeros(len(den))
    nn[len(den) - len(num):] = num
    coeffs = [sp.nsimplify(round(float(d), 8), rational=True) + K * sp.nsimplify(round(float(m), 8), rational=True)
              for d, m in zip(den, nn)]
    n = len(coeffs) - 1
    if n < 1 or n > 8:
        return None
    cols = n // 2 + 1
    T = [[sp.Integer(0)] * cols for _ in range(n + 1)]
    for j, cf in enumerate(coeffs[0::2]):
        T[0][j] = cf
    for j, cf in enumerate(coeffs[1::2]):
        T[1][j] = cf
    for i in range(2, n + 1):
        a = T[i - 1][0]
        if sp.simplify(a) == 0:
            return None
        for j in range(cols - 1):
            T[i][j] = sp.factor(sp.cancel((a * T[i - 2][j + 1] - T[i - 2][0] * T[i - 1][j + 1]) / a))
    def tex(e):
        e = sp.nsimplify(e)
        if not e.free_symbols:
            return fmt(float(e))
        e = sp.N(e, 5)
        e = e.xreplace({n: sp.Integer(int(n)) for n in e.atoms(sp.Float) if float(n).is_integer()})
        return sp.latex(e).replace(".", "{,}")

    return {
        "rows": [{"power": n - i, "values": [tex(v) for v in T[i]]} for i in range(n + 1)],
        "first_column": [tex(T[i][0]) for i in range(n + 1)],
    }


# --- cruzamentos com o eixo jw e faixas de K ---------------------------

def _re_im_polys(p):
    """Separa p(jw) = R(w) + j I(w) em polinômios reais de w."""
    p = trim(p)
    n = len(p) - 1
    R = np.zeros(n + 1)
    I = np.zeros(n + 1)
    for idx, c in enumerate(p):
        k = n - idx
        pos = n - k
        jk = 1j ** k
        if abs(jk.imag) < 0.5:
            R[pos] += c * jk.real
        else:
            I[pos] += c * jk.imag
    return trim(R), trim(I)


def jw_crossings(num, den) -> list[dict]:
    """Valores de K>0 em que algum polo de den + K num está sobre o eixo imaginário."""
    Dr, Di = _re_im_polys(den)
    Nr, Ni = _re_im_polys(num)
    F = padd(pmul(Dr, Ni), -pmul(Di, Nr))
    out: list[dict] = []
    if np.allclose(F, 0):
        return out
    roots = np.roots(F) if len(F) > 1 else np.array([])
    cands = {0.0}
    for r in roots:
        if abs(r.imag) < 1e-6 * max(1, abs(r)) and r.real >= -1e-9:
            cands.add(round(abs(r.real), 10))
    for w in sorted(cands):
        nr, ni = np.polyval(Nr, w), np.polyval(Ni, w)
        dr, di = np.polyval(Dr, w), np.polyval(Di, w)
        if abs(nr) > 1e-9:
            k = -dr / nr
        elif abs(ni) > 1e-9:
            k = -di / ni
        else:
            continue
        val = abs(np.polyval(padd(den, k * np.asarray(num)), 1j * w))
        scale = 1 + abs(np.polyval(den, 1j * w))
        if k > 1e-9 and np.isfinite(k) and val < 1e-6 * scale:
            out.append({"K": float(k), "w": float(w)})
    out.sort(key=lambda d: d["K"])
    return out


def closed_loop_poles(num, den, k: float) -> np.ndarray:
    return clean_roots(np.roots(padd(den, k * np.asarray(num))))


def _stable_for(num, den, k: float) -> bool:
    p = closed_loop_poles(num, den, k)
    return bool(np.all(p.real < -1e-9))


def stable_k_intervals(num, den) -> list[list[float | None]]:
    """Intervalos de K>0 para os quais a malha fechada K G/(1+K G) é estável."""
    cross = sorted({round(c["K"], 9) for c in jw_crossings(num, den)})
    edges = [0.0] + cross + [math.inf]
    intervals: list[list[float | None]] = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mid = (lo + hi) / 2 if np.isfinite(hi) else (2 * lo if lo > 0 else 1.0)
        if _stable_for(num, den, mid):
            if intervals and intervals[-1][1] == lo:
                intervals[-1][1] = hi
            else:
                intervals.append([lo, hi])
    return [[lo, (None if not np.isfinite(hi) else hi)] for lo, hi in intervals]


def critical_gain(num, den) -> dict | None:
    """Ganho crítico Ku e frequência de oscilação wu (2º método de Ziegler-Nichols)."""
    intervals = stable_k_intervals(num, den)
    if not intervals or intervals[0][0] != 0.0 or intervals[0][1] is None:
        return None
    ku = intervals[0][1]
    for c in jw_crossings(num, den):
        if abs(c["K"] - ku) < 1e-6 * max(1, ku):
            if c["w"] <= 1e-9:
                return {"Ku": ku, "wu": 0.0, "Pu": None}
            return {"Ku": ku, "wu": c["w"], "Pu": 2 * math.pi / c["w"]}
    return None


# --- lugar das raízes ---------------------------------------------------

def root_locus(g: TF) -> dict:
    num, den = g.num, g.den
    poles, zeros = g.poles(), g.zeros()
    n, m = len(poles), len(zeros)
    cross = jw_crossings(num, den)

    # regras de construção
    asym = None
    if n > m:
        centroid = float((np.sum(poles).real - np.sum(zeros).real) / (n - m))
        angles = [float((2 * q + 1) * 180.0 / (n - m)) for q in range(n - m)]
        asym = {"centroid": centroid, "angles": angles}

    dnum, dden = np.polyder(num) if len(num) > 1 else np.array([0.0]), np.polyder(den)
    bp_poly = padd(pmul(num, dden), -pmul(den, dnum))
    breakaway = []
    if len(bp_poly) > 1:
        for r in np.roots(bp_poly):
            if abs(r.imag) < 1e-6:
                nv = np.polyval(num, r.real)
                if abs(nv) < 1e-12:
                    continue
                k = -np.polyval(den, r.real) / nv
                if k > 1e-9:
                    breakaway.append({"s": float(r.real), "K": float(k)})

    departure = []
    for i, p in enumerate(poles):
        if p.imag > 1e-9:
            ang = 180.0
            for j, q in enumerate(poles):
                if j != i:
                    ang -= math.degrees(np.angle(p - q))
            for z in zeros:
                ang += math.degrees(np.angle(p - z))
            departure.append({"pole": [float(p.real), float(p.imag)], "angle": float((ang + 180) % 360 - 180)})

    # escala de K
    kref = max([1.0] + [c["K"] for c in cross] + [b["K"] for b in breakaway])
    ks = np.concatenate([[0.0], np.geomspace(kref * 1e-4, kref * 1e3, 500)])
    prev = None
    rows = []
    for k in ks:
        r = np.roots(padd(den, k * num))
        if prev is not None and len(r) == len(prev):
            cost = np.abs(prev[:, None] - r[None, :])
            _, col = linear_sum_assignment(cost)
            r = r[col]
        rows.append(r)
        prev = r
    width = max(len(r) for r in rows)
    branches = [[] for _ in range(width)]
    for k, r in zip(ks, rows):
        for b in range(width):
            if b < len(r):
                branches[b].append([float(r[b].real), float(r[b].imag), float(k)])

    # janela de visualização
    pts = [complex(p) for p in poles] + [complex(z) for z in zeros]
    pts += [1j * c["w"] for c in cross] + [b["s"] for b in breakaway]
    if asym:
        pts.append(asym["centroid"])
    pts.append(0)
    re = np.array([p.real for p in pts])
    im = np.array([p.imag for p in pts])
    span = max(np.ptp(re), np.ptp(im), 1.0)
    pad = 0.6 * span
    window = {
        "x": [float(re.min() - pad), float(max(re.max(), 0) + pad)],
        "y": [float(-max(np.abs(im).max(), span / 2) - pad), float(max(np.abs(im).max(), span / 2) + pad)],
    }
    return {
        "poles": [[float(p.real), float(p.imag)] for p in poles],
        "zeros": [[float(z.real), float(z.imag)] for z in zeros],
        "branches": branches,
        "asymptotes": asym,
        "breakaway": breakaway,
        "departure": departure,
        "jw_crossings": cross,
        "window": window,
    }
