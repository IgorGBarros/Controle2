"""Malhas de exemplo exibidas no frontend."""


def _tf(num, den):
    return {"mode": "tf", "num": num, "den": den}


EXAMPLES = [
    {
        "name": "Trabalho de Controle II (2013)",
        "description": "Planta de 3ª ordem do trabalho original: a1 = 11,3; a2 = 14; a3 = 10.",
        "spec": {"plant": _tf("1", "1 11.3 14 10")},
    },
    {
        "name": "Com sensor H(s)",
        "description": "Motor com sensor de 1ª ordem na realimentação: H(s) = 5/(s+5).",
        "spec": {"plant": _tf("10", "s(s+2)"), "sensor": {"num": "5", "den": "s+5"}},
    },
    {
        "name": "PID já projetado",
        "description": "Planta de 3ª ordem com C(s) = PID (Kp=20, Ki=10, Kd=5).",
        "spec": {"plant": _tf("1", "(s+1)(s+2)(s+5)"), "controller": {"mode": "pid", "kp": 20, "ki": 10, "kd": 5}},
    },
    {
        "name": "Processo com atraso",
        "description": "G(s) = e^(−2s)/(10s+1), atraso aproximado por Padé de 3ª ordem.",
        "spec": {"plant": _tf("1", "10s+1"), "delay": 2, "pade_order": 3},
    },
    {
        "name": "Zeros/polos/ganho",
        "description": "Planta informada por zeros, polos e ganho, com compensador de avanço C(s) = (s+1)/(s+10).",
        "spec": {
            "plant": {"mode": "zpk", "zeros": "", "poles": "0, -2, -4", "gain": 8},
            "controller": {"mode": "tf", "num": "s+1", "den": "s+10"},
        },
    },
    {
        "name": "Espaço de estados",
        "description": "Massa-mola-amortecedor: m=1, b=0,5, k=2 em forma de espaço de estados.",
        "spec": {"plant": {"mode": "ss", "A": "[0 1; -2 -0.5]", "B": "[0; 1]", "C": "[1 0]", "D": "0"}},
    },
    {
        "name": "Realimentação positiva",
        "description": "Planta estável com realimentação positiva: estável só para ganhos pequenos.",
        "spec": {"plant": _tf("1", "(s+1)(s+3)"), "feedback": "positive"},
    },
    {
        "name": "Instável em malha aberta",
        "description": "Polo em s = 1, estabilizado pela realimentação.",
        "spec": {"plant": _tf("1", "(s-1)(s+2)")},
    },
]
