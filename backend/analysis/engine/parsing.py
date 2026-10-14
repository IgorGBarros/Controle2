"""Leitura de polinômios em s.

Aceita tanto o formato vetorial do MATLAB ("[1 11.3 14 10]", "1, 11.3, 14, 10")
quanto expressões em s ("(s+10)(s^2+1.3s+1)", "s^3 + 11.3 s^2 + 14 s + 10").
"""

from __future__ import annotations

import re

import numpy as np
import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)

S = sp.Symbol("s")
_NUMBER_LIST = re.compile(r"^\s*\[?\s*[-+0-9.eE\s,;]+\]?\s*$")
_ALLOWED = re.compile(r"^[0-9sS.+\-*/^()\[\]\s,eE]*$")
_TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor)


class ParseError(ValueError):
    pass


def parse_polynomial(text: str, label: str = "polinômio") -> np.ndarray:
    if text is None or not str(text).strip():
        raise ParseError(f"Informe o {label}.")
    text = str(text).strip()
    if len(text) > 300:
        raise ParseError(f"O {label} é muito longo.")

    if _NUMBER_LIST.match(text) and "s" not in text.lower():
        parts = [p for p in re.split(r"[\s,;\[\]]+", text) if p]
        try:
            coeffs = [float(p) for p in parts]
        except ValueError as exc:
            raise ParseError(f"Coeficientes inválidos no {label}: {text}") from exc
        if not coeffs:
            raise ParseError(f"Informe o {label}.")
        return np.array(coeffs, dtype=float)

    if not _ALLOWED.match(text):
        raise ParseError(
            f"O {label} só pode conter números, a variável s e os operadores + - * / ^ ( )."
        )
    for exp in re.findall(r"(?:\^|\*\*)\s*\(?\s*([0-9.]+)", text):
        if float(exp) > 20:
            raise ParseError(f"Expoente muito alto no {label} (máximo 20).")
    try:
        expr = parse_expr(
            text.replace("S", "s"),
            local_dict={"s": S},
            global_dict={"__builtins__": {}, "Integer": sp.Integer, "Float": sp.Float,
                         "Rational": sp.Rational, "Symbol": sp.Symbol},
            transformations=_TRANSFORMS,
            evaluate=True,
        )
    except Exception as exc:  # noqa: BLE001 - sympy lança vários tipos
        raise ParseError(f"Não foi possível interpretar o {label}: {text}") from exc
    expr = sp.expand(expr)
    if expr.free_symbols - {S}:
        raise ParseError(f"O {label} deve depender apenas de s.")
    try:
        poly = sp.Poly(expr, S)
    except sp.PolynomialError as exc:
        raise ParseError(f"O {label} deve ser um polinômio em s.") from exc
    return np.array([float(c) for c in poly.all_coeffs()], dtype=float)


_COMPLEX_TOKEN = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?([-+](\d+\.?\d*|\.\d+)([eE][-+]?\d+)?)?j?$|^[-+]?(\d+\.?\d*|\.\d+)?j$")


def parse_complex_list(text: str | None, label: str) -> np.ndarray:
    """Lista de números complexos: "-1, -2+3j, -2-3j" (aceita i ou j)."""
    if text is None or not str(text).strip():
        return np.array([], dtype=complex)
    text = str(text).strip().strip("[]").replace("−", "-").replace("i", "j")
    if len(text) > 400:
        raise ParseError(f"A lista de {label} é muito longa.")
    parts = re.split(r"[,;]", text) if re.search(r"[,;]", text) else text.split()
    out = []
    for raw in parts:
        tok = raw.replace(" ", "")
        if not tok:
            continue
        if not _COMPLEX_TOKEN.match(tok):
            raise ParseError(f"Valor inválido em {label}: {raw.strip()}")
        try:
            out.append(complex(tok))
        except ValueError as exc:
            raise ParseError(f"Valor inválido em {label}: {raw.strip()}") from exc
    vals = np.array(out, dtype=complex)
    for v in vals[np.abs(vals.imag) > 1e-12]:
        if not np.any(np.abs(vals - np.conj(v)) < 1e-9 * max(1.0, abs(v))):
            raise ParseError(f"Em {label}, o valor complexo {raw_str(v)} precisa do seu conjugado {raw_str(np.conj(v))}.")
    return vals


def raw_str(z: complex) -> str:
    sign = "+" if z.imag >= 0 else "-"
    return f"{z.real:g}{sign}{abs(z.imag):g}j"


def parse_matrix(text: str | None, label: str) -> np.ndarray:
    """Matriz no formato do MATLAB: "[0 1; -2 -3]" (linhas separadas por ; ou quebra de linha)."""
    if text is None or not str(text).strip():
        raise ParseError(f"Informe a matriz {label}.")
    text = str(text).strip().replace("−", "-")
    if len(text) > 2000:
        raise ParseError(f"A matriz {label} é muito grande.")
    text = text.strip("[]")
    rows = [r for r in re.split(r"[;\n]", text) if r.strip()]
    data = []
    for r in rows:
        try:
            data.append([float(v) for v in re.split(r"[\s,]+", r.strip()) if v])
        except ValueError as exc:
            raise ParseError(f"Valor inválido na matriz {label}.") from exc
    if not data or any(len(r) != len(data[0]) for r in data):
        raise ParseError(f"A matriz {label} deve ter todas as linhas com o mesmo número de elementos.")
    return np.array(data, dtype=float)
