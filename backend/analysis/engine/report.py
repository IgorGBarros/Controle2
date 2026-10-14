"""Orquestra todos os itens do trabalho e converte o resultado para JSON."""

from __future__ import annotations

import math
import traceback

import numpy as np

from . import items
from .items import Params
from .parsing import parse_polynomial
from .tf import TF

ITEMS = [
    ("a", "Modelagem e função de transferência", items.item_a),
    ("b", "Constantes do sistema", items.item_b),
    ("c", "Frequência natural (ωn) e amortecimento (ζ)", items.item_c),
    ("d", "Polos da função de transferência em malha aberta", items.item_d),
    ("e", "Fechamento da malha com ganho K", items.item_e),
    ("f", "Diagrama de Bode por assíntotas", items.item_f),
    ("g", "Diagrama de Bode com margem de ganho e de fase", items.item_g),
    ("h", "Saída para degrau, impulso e rampa", items.item_h),
    ("i", "Ganho do sistema para cada entrada", items.item_i),
    ("j", "Lugar das raízes (Root Locus)", items.item_j),
    ("k", "Desempenho transitório — malha aberta", items.item_k),
    ("l", "Desempenho transitório — malha fechada (K = 1)", items.item_l),
    ("m", "Comparação malha aberta × malha fechada", items.item_m),
    ("n", "Ação proporcional para erro em regime especificado", items.item_n),
    ("o", "Ganho proporcional para Ts e Mp especificados", items.item_o),
    ("p", "Ziegler-Nichols — 1º método (curva de reação)", items.item_p),
    ("q", "Ziegler-Nichols — 2º método (ganho crítico)", items.item_q),
    ("r", "Média dos parâmetros e simulação (degrau, rampa e senoide)", None),
]

MAX_ORDER = 10


class InputError(ValueError):
    pass


def build_system(num_text: str, den_text: str) -> TF:
    num = parse_polynomial(num_text, "numerador")
    den = parse_polynomial(den_text, "denominador")
    if np.allclose(num, 0):
        raise InputError("O numerador não pode ser nulo.")
    g = TF(num, den)
    if g.order < 1:
        raise InputError("O denominador deve ter grau maior ou igual a 1.")
    if g.order > MAX_ORDER:
        raise InputError(f"Ordem máxima suportada: {MAX_ORDER}.")
    if not g.is_proper:
        raise InputError("A função de transferência deve ser própria (grau do numerador ≤ grau do denominador).")
    if not np.all(np.isfinite(g.num)) or not np.all(np.isfinite(g.den)):
        raise InputError("Coeficientes inválidos.")
    return g


def sanitize(obj):
    if isinstance(obj, dict):
        return {str(k): sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    if isinstance(obj, np.ndarray):
        if np.iscomplexobj(obj):
            return [sanitize(complex(v)) for v in obj.ravel()] if obj.ndim == 1 else sanitize(obj.tolist())
        return sanitize(obj.tolist())
    if isinstance(obj, (complex, np.complexfloating)):
        return {"re": sanitize(float(obj.real)), "im": sanitize(float(obj.imag))}
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        x = float(obj)
        if math.isnan(x):
            return None
        if math.isinf(x):
            return "inf" if x > 0 else "-inf"
        return round(x, 8) if abs(x) >= 1e-6 or x == 0 else x
    return obj


def analyze(num_text: str, den_text: str, params: Params) -> dict:
    g = build_system(num_text, den_text)
    results: dict = {}
    for key, title, fn in ITEMS:
        try:
            if key == "r":
                data = items.item_r(g, params, results["p"]["data"] or {}, results["q"]["data"] or {})
            else:
                data = fn(g, params)
            results[key] = {"key": key, "title": title, "data": data, "error": None}
        except Exception as exc:  # noqa: BLE001 - um item com erro não derruba os demais
            traceback.print_exc()
            results[key] = {"key": key, "title": title, "data": None, "error": str(exc)}
    payload = {
        "system": items.tf_info(g),
        "params": params.__dict__,
        "items": [results[k] for k, _, _ in ITEMS],
    }
    return sanitize(payload)
