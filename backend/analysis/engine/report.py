"""Orquestra todos os itens do trabalho e converte o resultado para JSON."""

from __future__ import annotations

import math
import traceback

import numpy as np

from . import items
from .items import Params
from .loop import InputError, Loop, build_loop

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


def system_info(lp: Loop) -> dict:
    L = lp.open_loop
    return {
        **items.tf_info(lp.plant_raw),
        "plant": items.block_info(lp.plant_raw),
        "controller": items.block_info(lp.controller),
        "sensor": items.block_info(lp.sensor),
        "controller_pid": lp.controller_pid,
        "open_loop": items.tf_info(L),
        "closed_loop": items.tf_info(lp.closed(1.0)),
        "feedback": "negative" if lp.sign < 0 else "positive",
        "delay": lp.delay,
        "pade_order": lp.pade_order,
        "standard": lp.standard,
    }


def analyze(spec: dict, params: Params) -> dict:
    """spec: {plant: {...}, controller: {...}, sensor: {...}, feedback, delay, pade_order}."""
    lp = build_loop(spec)
    results: dict = {}
    for key, title, fn in ITEMS:
        try:
            if key == "r":
                data = items.item_r(lp, params, results["p"]["data"] or {}, results["q"]["data"] or {})
            else:
                data = fn(lp, params)
            results[key] = {"key": key, "title": title, "data": data, "error": None}
        except Exception as exc:  # noqa: BLE001 - um item com erro não derruba os demais
            traceback.print_exc()
            results[key] = {"key": key, "title": title, "data": None, "error": str(exc)}
    payload = {
        "system": system_info(lp),
        "params": params.__dict__,
        "items": [results[k] for k, _, _ in ITEMS],
    }
    return sanitize(payload)


def analyze_tf(num: str, den: str, params: Params | None = None) -> dict:
    """Atalho: planta G(s) = num/den com realimentação unitária negativa."""
    return analyze({"plant": {"mode": "tf", "num": num, "den": den}}, params or Params())
