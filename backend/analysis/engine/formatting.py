"""Formatação de números e polinômios em LaTeX (renderizados com KaTeX no frontend)."""

from __future__ import annotations

import numpy as np


def fmt_plain(x: float, digits: int = 4) -> str:
    """Número com ponto decimal e notação 1e-05 (usado nos trechos de código MATLAB)."""
    if x is None:
        return "-"
    if not np.isfinite(x):
        return "Inf" if x > 0 else "-Inf"
    if abs(x) < 1e-12:
        return "0"
    return f"{x:.{digits}g}"


def fmt(x: float, digits: int = 4) -> str:
    """Número em LaTeX com vírgula decimal (padrão brasileiro)."""
    if x is not None and not np.isfinite(x):
        return r"\infty" if x > 0 else r"-\infty"
    s = fmt_plain(x, digits)
    if "e" in s:
        mant, exp = s.split("e")
        s = f"{mant}\\times 10^{{{int(exp)}}}"
    return s.replace(".", "{,}")


def fmt_txt(x: float, digits: int = 4) -> str:
    """Número para texto corrido (vírgula decimal, sem LaTeX)."""
    if x is not None and not np.isfinite(x):
        return "∞" if x > 0 else "-∞"
    return fmt_plain(x, digits).replace(".", ",")


def poly_latex(coeffs, var: str = "s", digits: int = 4) -> str:
    coeffs = np.asarray(coeffs, dtype=float)
    n = len(coeffs) - 1
    terms: list[str] = []
    for i, c in enumerate(coeffs):
        if abs(c) < 1e-12:
            continue
        power = n - i
        mag = abs(c)
        if power == 0:
            body = fmt(mag, digits)
        else:
            coef = "" if abs(mag - 1) < 1e-12 else fmt(mag, digits)
            body = f"{coef}{var}" + (f"^{{{power}}}" if power > 1 else "")
        sign = "-" if c < 0 else "+"
        terms.append((sign, body))
    if not terms:
        return "0"
    first_sign, first = terms[0]
    out = ("-" if first_sign == "-" else "") + first
    for sign, body in terms[1:]:
        out += f" {sign} {body}"
    return out


def tf_latex(num, den, digits: int = 4) -> str:
    return rf"\frac{{{poly_latex(num, digits=digits)}}}{{{poly_latex(den, digits=digits)}}}"


def factored_latex(roots, gain: float = 1.0, digits: int = 4) -> str:
    """Forma fatorada: (s + a)(s^2 + b s + c)..."""
    roots = list(np.asarray(roots, dtype=complex))
    factors: list[str] = []
    used = [False] * len(roots)
    for i, r in enumerate(roots):
        if used[i]:
            continue
        used[i] = True
        if abs(r.imag) < 1e-9:
            if abs(r.real) < 1e-12:
                factors.append("s")
            else:
                factors.append(f"({poly_latex([1, -r.real], digits=digits)})")
        else:
            for j in range(i + 1, len(roots)):
                if not used[j] and abs(roots[j] - np.conj(r)) < 1e-6:
                    used[j] = True
                    break
            b = -2 * r.real
            c = abs(r) ** 2
            factors.append(f"({poly_latex([1, b, c], digits=digits)})")
    body = "".join(factors) if factors else "1"
    if abs(gain - 1) < 1e-12:
        return body
    return f"{fmt(gain, digits)}\\,{body}"


def complex_str(z: complex, digits: int = 4) -> str:
    z = complex(z)
    if abs(z.imag) < 1e-12:
        return fmt_txt(z.real, digits)
    sign = "+" if z.imag >= 0 else "−"
    return f"{fmt_txt(z.real, digits)} {sign} {fmt_txt(abs(z.imag), digits)}j"
