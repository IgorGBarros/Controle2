"""Malha de controle genérica.

    r ──►(Σ)──► K·C(s) ──► G(s)·e^{-θs} ──┬──► y
          ▲∓                               │
          └──────────── H(s) ◄─────────────┘

O ganho K multiplica o controlador C(s). A realimentação pode ser negativa ou positiva.
A malha aberta é L(s) = C(s) G(s) H(s); para as análises de estabilidade (lugar das raízes,
margens, Routh) usa-se a malha "equivalente" L_eq = ±L, de modo que a equação característica
seja sempre 1 + K L_eq(s) = 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from scipy import signal

from .parsing import ParseError, parse_complex_list, parse_matrix, parse_polynomial
from .tf import TF, padd, pmul

MAX_ORDER = 12


class InputError(ValueError):
    pass


def pade(theta: float, n: int) -> TF:
    """Aproximação de Padé (n, n) para e^{-θs}."""
    f = math.factorial
    c = [f(2 * n - k) * f(n) / (f(2 * n) * f(k) * f(n - k)) for k in range(n + 1)]
    num = [c[k] * (-theta) ** k for k in range(n + 1)][::-1]
    den = [c[k] * theta ** k for k in range(n + 1)][::-1]
    return TF(num, den)


def pid_tf(kp: float, ki: float = 0.0, kd: float = 0.0, g: TF | None = None, n_filter: float = 100.0) -> TF:
    """C(s) = Kp + Ki/s + Kd s (derivada filtrada Kd·N·s/(s+N) se C·G ficaria imprópria)."""
    if kd and g is not None and g.relative_degree < 1:
        num = padd(pmul([kp], [1, n_filter]), [kd * n_filter, 0])
        c = TF(num, [1.0, n_filter])
        if ki:
            c = TF(padd(pmul(c.num, [1, 0]), pmul([ki], c.den)), pmul(c.den, [1, 0]))
        return c
    if ki:
        return TF([kd, kp, ki], [1.0, 0.0])
    return TF([kd, kp], [1.0])


def is_unity(g: TF) -> bool:
    return len(g.num) == 1 and len(g.den) == 1 and abs(g.num[0] - 1) < 1e-12


@dataclass
class Loop:
    plant: TF                    # G(s) efetiva (inclui Padé se houver atraso)
    controller: TF = field(default_factory=lambda: TF([1.0], [1.0]))
    sensor: TF = field(default_factory=lambda: TF([1.0], [1.0]))
    sign: int = -1               # -1: realimentação negativa · +1: positiva
    plant_raw: TF | None = None  # G(s) sem o atraso
    delay: float = 0.0
    pade_order: int = 0
    controller_pid: dict | None = None

    def __post_init__(self):
        if self.plant_raw is None:
            self.plant_raw = self.plant

    # --- funções de transferência da malha ----------------------------------
    @property
    def forward(self) -> TF:
        """Caminho direto C(s) G(s)."""
        return self.controller * self.plant

    @property
    def open_loop(self) -> TF:
        """Malha aberta L(s) = C(s) G(s) H(s)."""
        return self.forward * self.sensor

    @property
    def loop_eq(self) -> TF:
        """L equivalente: equação característica 1 + K L_eq = 0 (L_eq = -L para realimentação positiva)."""
        L = self.open_loop
        return L if self.sign < 0 else TF(-L.num, L.den)

    def closed(self, k: float = 1.0) -> TF:
        """T(s) = K C G / (1 ∓ K C G H)."""
        F, H = self.forward, self.sensor
        num = k * pmul(F.num, H.den)
        den = padd(pmul(F.den, H.den), (-self.sign) * k * pmul(F.num, H.num))
        return TF(num, den)

    def equivalent_unity(self, k: float = 1.0) -> TF:
        """G_eq(s) com realimentação unitária que produz o mesmo T(s): G_eq = T / (1 - T)."""
        T = self.closed(k)
        return TF(T.num, padd(T.den, -T.num))

    def process(self) -> TF:
        """Processo visto pelo controlador: P(s) = G(s) H(s)."""
        return self.plant * self.sensor

    def process_eq(self) -> TF:
        P = self.process()
        return P if self.sign < 0 else TF(-P.num, P.den)

    def with_controller(self, c: TF) -> "Loop":
        return replace(self, controller=c, controller_pid=None)

    @property
    def standard(self) -> bool:
        """Malha do trabalho original: C = 1, H = 1, realimentação negativa, sem atraso."""
        return is_unity(self.controller) and is_unity(self.sensor) and self.sign < 0 and self.delay == 0

    @property
    def unity_feedback(self) -> bool:
        return is_unity(self.sensor) and self.sign < 0


# --- construção a partir da requisição ----------------------------------------

def _tf_from_text(num: str, den: str, label: str) -> TF:
    n = parse_polynomial(num, f"numerador de {label}")
    d = parse_polynomial(den, f"denominador de {label}")
    if np.allclose(n, 0):
        raise InputError(f"O numerador de {label} não pode ser nulo.")
    if np.allclose(d, 0):
        raise InputError(f"O denominador de {label} não pode ser nulo.")
    return TF(n, d)


def build_plant(spec: dict) -> TF:
    mode = spec.get("mode", "tf")
    if mode == "tf":
        return _tf_from_text(spec.get("num", ""), spec.get("den", ""), "G(s)")
    if mode == "zpk":
        zeros = parse_complex_list(spec.get("zeros"), "zeros")
        poles = parse_complex_list(spec.get("poles"), "polos")
        if poles.size == 0:
            raise InputError("Informe pelo menos um polo.")
        try:
            k = float(spec.get("gain", 1) or 0)
        except (TypeError, ValueError) as exc:
            raise InputError("Ganho inválido.") from exc
        if k == 0:
            raise InputError("O ganho não pode ser zero.")
        num = k * np.real(np.poly(zeros)) if zeros.size else np.array([k])
        return TF(num, np.real(np.poly(poles)))
    if mode == "ss":
        A = parse_matrix(spec.get("A"), "A")
        B = parse_matrix(spec.get("B"), "B")
        C = parse_matrix(spec.get("C"), "C")
        D = parse_matrix(spec.get("D") or "0", "D")
        n = A.shape[0]
        if A.shape != (n, n):
            raise InputError("A matriz A deve ser quadrada.")
        if B.shape == (1, n) and n > 1:
            B = B.T
        if C.shape == (n, 1) and n > 1:
            C = C.T
        if B.shape != (n, 1):
            raise InputError(f"B deve ser uma coluna com {n} elementos (sistema SISO).")
        if C.shape != (1, n):
            raise InputError(f"C deve ser uma linha com {n} elementos (sistema SISO).")
        if D.shape != (1, 1):
            raise InputError("D deve ser um escalar (sistema SISO).")
        num, den = signal.ss2tf(A, B, C, D)
        num = np.where(np.abs(num[0]) < 1e-10 * max(1, np.max(np.abs(num[0]))), 0.0, num[0])
        if np.allclose(num, 0):
            raise InputError("A função de transferência resultante é nula (sistema não observável/controlável).")
        return TF(num, den)
    raise InputError(f"Modo de entrada da planta desconhecido: {mode}")


def build_loop(spec: dict) -> Loop:
    try:
        plant_raw = build_plant(spec.get("plant") or {})
        ctrl_spec = spec.get("controller") or {}
        pid = None
        delay = float(spec.get("delay") or 0.0)
        pade_order = int(spec.get("pade_order") or 2)
        plant = plant_raw * pade(delay, pade_order) if delay > 0 else plant_raw
        if ctrl_spec.get("mode") == "pid":
            pid = {k: float(ctrl_spec.get(k) or 0.0) for k in ("kp", "ki", "kd")}
            if not any(pid.values()):
                raise InputError("Informe pelo menos um ganho do PID.")
            controller = pid_tf(pid["kp"], pid["ki"], pid["kd"], plant)
        else:
            controller = _tf_from_text(ctrl_spec.get("num") or "1", ctrl_spec.get("den") or "1", "C(s)")
        sens = spec.get("sensor") or {}
        sensor = _tf_from_text(sens.get("num") or "1", sens.get("den") or "1", "H(s)")
    except ParseError as exc:
        raise InputError(str(exc)) from exc
    sign = 1 if spec.get("feedback") == "positive" else -1
    lp = Loop(plant=plant, controller=controller, sensor=sensor, sign=sign, plant_raw=plant_raw,
              delay=delay if delay > 0 else 0.0, pade_order=pade_order if delay > 0 else 0, controller_pid=pid)

    for g, name in ((plant_raw, "A planta G(s)"), (sensor, "O sensor H(s)"), (lp.forward, "C(s)·G(s)"), (lp.open_loop, "A malha aberta L(s)")):
        if not g.is_proper:
            raise InputError(f"{name} deve ser própria (grau do numerador ≤ grau do denominador).")
        if not (np.all(np.isfinite(g.num)) and np.all(np.isfinite(g.den))):
            raise InputError("Coeficientes inválidos.")
    if plant_raw.order < 1:
        raise InputError("A planta deve ter ao menos um polo (grau do denominador ≥ 1).")
    if lp.open_loop.order > MAX_ORDER:
        raise InputError(f"Ordem máxima suportada para a malha aberta L(s): {MAX_ORDER}.")
    T = lp.closed(1.0)
    if np.allclose(padd(T.den, -T.num), 0):
        raise InputError("A malha fechada resulta em T(s) = 1 — verifique a malha.")
    return lp
