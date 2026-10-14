"""Relatório final explicativo.

Gera um texto interpretando os resultados numéricos da malha analisada, com a
fundamentação teórica de duas referências:

- OGATA, K. Engenharia de Controle Moderno (5ª ed.) — modelagem, resposta transitória,
  erro em regime, Routh, lugar das raízes, resposta em frequência e PID.
- MEZA, M. E. M. Sistemas de Controle com Python: Resposta em Frequência — Laplace,
  diagramas de Bode e polar, margens, ressonância/largura de banda e projeto na frequência.

Todos os números vêm do motor de cálculo; o texto apenas os interpreta.
Fórmulas em LaTeX ficam entre $...$ e são renderizadas pelo frontend.
"""

from __future__ import annotations

import math

import numpy as np

from .formatting import complex_str, fmt, fmt_txt, tf_latex
from .loop import Loop, is_unity
from .tf import TF

REFERENCES = [
    {
        "key": "ogata",
        "cite": "OGATA, 2011",
        "text": "OGATA, Katsuhiko. Engenharia de Controle Moderno. 5. ed. São Paulo: Pearson Prentice Hall, 2011. "
                "ISBN 978-85-7605-810-6.",
    },
    {
        "key": "meza",
        "cite": "MEZA, 2024",
        "text": "MEZA, Magno Enrique Mendoza. Sistemas de Controle com Python: Resposta em Frequência. "
                "1. ed. São Paulo: Blucher, 2024. ISBN 978-85-212-2112-8.",
    },
]

OG = "OGATA, 2011"
MZ = "MEZA, 2024"


def t(x, digits: int = 4) -> str:
    """Número para texto corrido."""
    if x is None:
        return "—"
    if isinstance(x, str):
        return "∞" if x == "inf" else x
    return fmt_txt(float(x), digits)


def m(x, digits: int = 4) -> str:
    """Número para dentro de $...$."""
    if isinstance(x, str):
        return r"\infty"
    return fmt(float(x), digits)


def section(key: str, title: str, paragraphs: list[str], bullets: list[str] | None = None,
            cites: list[str] | None = None, chart: dict | None = None) -> dict:
    return {"key": key, "title": title, "paragraphs": paragraphs, "bullets": bullets or [],
            "cites": cites or [], "chart": chart}


# --- indicadores de resposta em frequência (MEZA, cap. 3) --------------------------------

def closed_loop_frequency(T: TF) -> dict | None:
    """Largura de banda (−3 dB em relação a |T(0)|), pico de ressonância Mr e ωr."""
    if not T.is_stable():
        return None
    t0 = abs(T.dc_gain()) if np.isfinite(T.dc_gain()) else 0.0
    if t0 < 1e-12:
        return None
    roots = np.concatenate([T.poles(), T.zeros()])
    mags = [abs(r) for r in roots if abs(r) > 1e-9] or [1.0]
    w = np.geomspace(min(mags) / 1000, max(mags) * 1000, 6000)
    mag = np.abs(T.freq(w)) / t0
    k = int(np.argmax(mag))
    mr = float(mag[k])
    below = np.flatnonzero(mag < 1 / math.sqrt(2))
    wb = None
    if below.size:
        i = below[0]
        if i > 0:
            # interpolação em escala log
            x0, x1 = math.log10(w[i - 1]), math.log10(w[i])
            y0, y1 = mag[i - 1], mag[i]
            wb = 10 ** (x0 + (1 / math.sqrt(2) - y0) * (x1 - x0) / (y1 - y0))
    return {
        "bandwidth": wb,
        "mr": mr if mr > 1.0001 else 1.0,
        "mr_db": 20 * math.log10(mr) if mr > 1.0001 else 0.0,
        "wr": float(w[k]) if mr > 1.0001 else None,
    }


def polar_data(L: TF) -> dict:
    """Diagrama polar (Nyquist) de L(jω) para ω > 0, com o espelho para ω < 0."""
    roots = np.concatenate([L.poles(), L.zeros()])
    mags = [abs(r) for r in roots if abs(r) > 1e-9] or [1.0]
    w = np.geomspace(min(mags) / 100, max(mags) * 100, 700)
    h = L.freq(w)
    keep = np.abs(h) < 1e3 * max(1.0, float(np.median(np.abs(h))))
    return {"re": h.real[keep], "im": h.imag[keep], "w": w[keep]}


# --- seções -----------------------------------------------------------------------------

def sec_system(lp: Loop, d: dict) -> dict:
    L, T = lp.open_loop, lp.closed(1.0)
    ps = [
        "Este relatório interpreta os resultados calculados pela ferramenta para a malha descrita abaixo, "
        "relacionando cada resultado à teoria clássica de controle. Os números são obtidos por simulação e "
        "cálculo exato; as fórmulas analíticas servem para explicar e validar esses números.",
    ]
    if lp.standard:
        ps.append(f"A planta é controlada por um ganho proporcional K em malha fechada com realimentação unitária "
                  f"negativa, exatamente como no trabalho original: $G(s) = {tf_latex(lp.plant_raw.num, lp.plant_raw.den)}$.")
    else:
        parts = [f"planta $G(s) = {tf_latex(lp.plant_raw.num, lp.plant_raw.den)}$"]
        if not is_unity(lp.controller):
            parts.append(f"controlador $C(s) = {tf_latex(lp.controller.num, lp.controller.den)}$")
        if not is_unity(lp.sensor):
            parts.append(f"sensor $H(s) = {tf_latex(lp.sensor.num, lp.sensor.den)}$")
        ps.append("A malha é composta por " + ", ".join(parts) +
                  f", com realimentação {'positiva' if lp.sign > 0 else 'negativa'}. "
                  f"A malha aberta é $L(s) = C(s)G(s)H(s) = {tf_latex(L.num, L.den)}$ e a malha fechada, "
                  f"com K = 1, é $T(s) = {tf_latex(T.num, T.den)}$.")
    if lp.delay:
        ps.append(f"O atraso de transporte $e^{{-{m(lp.delay)}s}}$ não é racional; ele foi substituído por uma "
                  f"aproximação de Padé de ordem {lp.pade_order}, válida para frequências abaixo de aproximadamente "
                  f"{t(lp.pade_order / lp.delay, 3)} rad/s. Atrasos reduzem a fase sem alterar o módulo e, por isso, "
                  f"diminuem a margem de fase ({OG}, cap. 7).")
    return section("sistema", "1. Sistema analisado", ps, cites=[OG])


def sec_model(lp: Loop, d: dict) -> dict:
    a = d.get("a") or {}
    ps = [
        "A função de transferência relaciona a transformada de Laplace da saída com a da entrada, considerando "
        "condições iniciais nulas. Ela é obtida aplicando a transformada de Laplace à equação diferencial do sistema "
        f"({OG}, cap. 2; {MZ}, cap. 2):",
        f"$${a.get('ode', '')}\\;\\xrightarrow{{\\mathcal{{L}}}}\\;{a.get('tf', '')}$$",
        "A mesma dinâmica pode ser escrita no espaço de estados, $\\dot x = Ax + Bu$, $y = Cx + Du$; a conversão para "
        "função de transferência é $G(s) = C(sI - A)^{-1}B + D$, e os polos de G(s) são os autovalores de A "
        f"({OG}, cap. 2 e cap. 9).",
    ]
    return section("modelagem", "2. Modelagem matemática", ps, cites=[OG, MZ])


def sec_stability(lp: Loop, d: dict) -> dict:
    dd, j = d.get("d") or {}, d.get("j") or {}
    L = lp.open_loop
    poles = L.poles()
    rhp = int(np.sum(poles.real > 1e-9))
    axis = int(np.sum(np.abs(poles.real) <= 1e-9))
    T1 = lp.closed(1.0)
    ps = [
        "Um sistema linear é estável quando todos os polos de malha fechada estão no semiplano esquerdo do plano s. "
        "O critério de Routh-Hurwitz permite verificar isso sem calcular as raízes: o número de trocas de sinal na "
        f"primeira coluna da tabela é igual ao número de raízes no semiplano direito ({OG}, cap. 5).",
    ]
    ol = (f"A malha aberta tem {len(poles)} polo(s): {', '.join(complex_str(p) for p in poles)}. ")
    if rhp:
        ol += f"{rhp} deles está(ão) no semiplano direito — a malha aberta é instável e só a realimentação pode estabilizá-la."
    elif axis:
        ol += f"{axis} polo(s) sobre o eixo imaginário (por exemplo, integradores): a malha aberta é marginalmente estável."
    else:
        ol += "Todos estão no semiplano esquerdo: a malha aberta é estável."
    ps.append(ol)
    intervals = j.get("stable_intervals") or []
    if intervals:
        txt = " ∪ ".join(f"{t(lo)} < K < {'∞' if hi is None else t(hi)}" for lo, hi in intervals)
        ps.append(f"Aplicando Routh à equação característica $1 + K\\,L(s) = 0$, a malha fechada é estável para {txt}. "
                  f"Com K = 1 ela é {'estável' if T1.is_stable() else 'instável'}.")
    else:
        ps.append("Nenhum ganho K > 0 torna a malha fechada estável com esta estrutura: é preciso mudar o controlador.")
    crit = j.get("critical")
    if crit and crit.get("Pu"):
        ps.append(f"No limite de estabilidade, $K_u = {m(crit['Ku'])}$, dois polos cruzam o eixo imaginário em "
                  f"$s = \\pm j{m(crit['wu'])}$ e a saída oscila com período $P_u = 2\\pi/\\omega_u = {m(crit['Pu'])}$ s. "
                  "Esse é exatamente o ponto usado pelo 2º método de Ziegler-Nichols e corresponde à margem de ganho "
                  f"vista no diagrama de Bode ({OG}, caps. 6 e 7).")
    return section("estabilidade", "3. Polos e estabilidade", ps, cites=[OG])


def sec_transient(lp: Loop, d: dict) -> dict:
    l_ = d.get("l") or {}
    dom = l_.get("dominant")
    meas = l_.get("measured") or {}
    T1 = lp.closed(1.0)
    ps = [
        "A resposta transitória de um sistema de 2ª ordem $\\frac{\\omega_n^2}{s^2 + 2\\zeta\\omega_n s + \\omega_n^2}$ é "
        "caracterizada pela frequência natural $\\omega_n$ e pelo coeficiente de amortecimento $\\zeta$. Para "
        "$0 < \\zeta < 1$ (subamortecido) valem as relações clássicas, em que $\\sigma = \\zeta\\omega_n$ e "
        f"$\\omega_d = \\omega_n\\sqrt{{1-\\zeta^2}}$ ({OG}, cap. 5):",
        "$$t_r = \\frac{\\pi - \\beta}{\\omega_d},\\quad t_p = \\frac{\\pi}{\\omega_d},\\quad "
        "M_p = e^{-\\sigma\\pi/\\omega_d},\\quad t_s(2\\%) = \\frac{4}{\\sigma}$$",
    ]
    bullets = []
    if not T1.is_stable() or not dom or not dom.get("stable"):
        ps.append("Com K = 1 a malha fechada não é estável, portanto esses indicadores não se aplicam.")
        return section("transitorio", "4. Resposta transitória", ps, cites=[OG])
    z = dom.get("zeta")
    kind = ("subamortecida (oscilatória)" if z < 0.999 else "criticamente amortecida" if z < 1.001 else "sobreamortecida")
    ps.append(f"Para a malha fechada com K = 1, o polo dominante é {complex_str(dom['pole'])}, com "
              f"$\\omega_n = {m(dom.get('wn'))}$ rad/s e $\\zeta = {m(z)}$: a resposta é {kind}.")
    poles = T1.poles()
    others = [p for p in poles if abs(p - dom["pole"]) > 1e-6 and abs(p - np.conj(dom["pole"])) > 1e-6]
    if others:
        ratio = min(abs(p.real) for p in others) / max(dom["sigma"], 1e-12)
        if ratio >= 5:
            ps.append(f"Os demais polos estão {t(ratio, 3)} vezes mais à esquerda, então a aproximação por polos dominantes "
                      f"é boa (regra prática de pelo menos 5 vezes, {OG}, cap. 5).")
        else:
            ps.append(f"Os demais polos estão apenas {t(ratio, 3)} vezes mais à esquerda (menos de 5 vezes), então as "
                      "fórmulas de 2ª ordem são só uma aproximação; os valores medidos na simulação são os confiáveis.")
    bullets += [
        f"Sobressinal: {t(dom.get('overshoot'))}% pela fórmula, {t(meas.get('overshoot'))}% medido.",
        f"Tempo de pico: {t(dom.get('peak_time'))} s pela fórmula, {t(meas.get('peak_time'))} s medido.",
        f"Tempo de acomodação (2%): {t(dom.get('settling_time_2'))} s pela fórmula, {t(meas.get('settling_time'))} s medido.",
        f"Valor final: {t(meas.get('final_value'))}.",
    ]
    return section("transitorio", "4. Resposta transitória", ps, bullets, cites=[OG])


def sec_steady(lp: Loop, d: dict) -> dict:
    i, n = d.get("i") or {}, d.get("n") or {}
    typ = i.get("system_type", 0)
    c = i.get("constants_unit") or {}
    ps = [
        "O erro em regime permanente depende do tipo do sistema (número de integradores na malha) e das constantes "
        "de erro estático $K_p = \\lim_{s\\to0}G(s)$, $K_v = \\lim_{s\\to0}sG(s)$ e $K_a = \\lim_{s\\to0}s^2G(s)$. "
        "Para realimentação unitária, $e_{degrau} = 1/(1+K_p)$, $e_{rampa} = 1/K_v$ e $e_{parábola} = 1/K_a$ "
        f"({OG}, cap. 5).",
    ]
    if not lp.unity_feedback:
        ps.append("Como a realimentação não é unitária, a ferramenta usa a malha unitária equivalente "
                  "$G_{eq} = T/(1-T)$, que produz o mesmo erro $e = r - y$.")
    ps.append(f"Esta malha é do tipo {typ}: com K = 1, $K_p = {m(c.get('Kp', 0))}$, $K_v = {m(c.get('Kv', 0))}$ e "
              f"$K_a = {m(c.get('Ka', 0))}$. "
              + ("Logo, há erro finito ao degrau e o sistema não acompanha a rampa." if typ == 0 else
                 "Logo, o erro ao degrau é nulo e o erro à rampa é finito." if typ == 1 else
                 "Logo, os erros ao degrau e à rampa são nulos."))
    if n.get("applicable") and n.get("K"):
        prep = {"degrau": "ao degrau", "rampa": "à rampa", "parábola": "à parábola"}.get(n["input"], n["input"])
        msg = (f"Para obter erro de {t(100 * n['target'])}% {prep}, seria necessário K = {t(n['K'])}. ")
        if n.get("stable"):
            msg += "Esse ganho mantém a malha estável, então a especificação é viável só com ação proporcional."
        else:
            msg += ("Porém esse ganho torna a malha instável — aumentar o ganho reduz o erro mas também o amortecimento. "
                    "Esse conflito entre precisão e estabilidade é o motivo para usar ação integral (PI/PID) ou "
                    f"compensação por atraso de fase ({OG}, caps. 6 a 8).")
        ps.append(msg)
    return section("regime", "5. Erro em regime permanente", ps, cites=[OG])


def sec_frequency(lp: Loop, d: dict) -> dict:
    g, f = d.get("g") or {}, d.get("f") or {}
    mg = g.get("margins") or {}
    ps = [
        "Na resposta em frequência, avalia-se $L(j\\omega)$ para uma entrada senoidal em regime. O diagrama de Bode "
        "mostra o módulo em dB e a fase em função de $\\omega$ em escala logarítmica; cada polo ou zero real muda a "
        "inclinação assintótica em ±20 dB/década na sua frequência de canto, e cada par complexo em ±40 dB/década "
        f"({MZ}, cap. 3; {OG}, cap. 7).",
    ]
    corners = f.get("corners") or []
    if corners:
        ps.append("Neste sistema, as frequências de canto são " +
                  ", ".join(f"{t(c['w'])} rad/s ({c['kind']}{' duplo' if c['order'] == 2 else ''})" for c in corners) +
                  f"; a inclinação final é {corners[-1]['slope_after']} dB/década.")
    ps.append("As margens de estabilidade medem a distância ao ponto crítico −1: a margem de ganho é quanto o ganho pode "
              "aumentar até a instabilidade (lida na frequência de cruzamento de fase, onde a fase vale −180°), e a "
              "margem de fase é quanto atraso de fase adicional é tolerado (lida no cruzamento de ganho, onde |L| = 0 dB). "
              f"Valores usuais para bom desempenho são margem de fase entre 30° e 60° e margem de ganho acima de 6 dB "
              f"({OG}, cap. 7; {MZ}, cap. 3).")
    gm, pm = mg.get("gm_db"), mg.get("pm")
    bullets = [
        f"Margem de ganho (K = 1): {'∞' if gm in (None, math.inf) or not np.isfinite(gm) else t(gm) + ' dB'}"
        + (f" em ω = {t(mg.get('wpc'))} rad/s" if mg.get("wpc") else "") + ".",
        f"Margem de fase (K = 1): {'∞ (|L| nunca cruza 0 dB)' if pm in (None, math.inf) or not np.isfinite(pm) else t(pm) + '°'}"
        + (f" em ω = {t(mg.get('wgc'))} rad/s" if mg.get("wgc") else "") + ".",
    ]
    mk = g.get("margins_k") or {}
    if mk:
        pmk = mk.get("pm")
        bullets.append(f"Com K = {t(g.get('K'))}: margem de fase "
                       f"{'∞' if pmk is None or not np.isfinite(pmk) else t(pmk) + '°'}; malha fechada "
                       f"{'estável' if mk.get('closed_loop_stable') else 'instável'}.")
        if pmk is not None and np.isfinite(pmk) and 0 < pmk < 70:
            bullets.append(f"Pela aproximação $\\zeta \\approx MF/100$ (válida para MF < 70°), espera-se ζ ≈ {t(pmk / 100, 2)} "
                           f"na malha fechada com K = {t(g.get('K'))} ({OG}, cap. 7).")
    T1 = lp.closed(1.0)
    cf = closed_loop_frequency(T1)
    if cf:
        txt = (f"Na malha fechada (K = 1), a largura de banda é ω_B ≈ {t(cf['bandwidth'])} rad/s"
               if cf["bandwidth"] else "Na malha fechada (K = 1), o módulo não cai 3 dB na faixa analisada")
        if cf["wr"]:
            txt += (f" e há pico de ressonância $M_r = {m(cf['mr'])}$ ({t(cf['mr_db'])} dB) em ω_r ≈ {t(cf['wr'])} rad/s. "
                    "Para um sistema de 2ª ordem, $M_r = 1/(2\\zeta\\sqrt{1-\\zeta^2})$ (para ζ < 0,707): picos altos indicam "
                    "pouco amortecimento e sobressinal elevado.")
        else:
            txt += ", sem pico de ressonância (resposta bem amortecida)."
        txt += (" Quanto maior a largura de banda, mais rápida a resposta no tempo "
                f"({MZ}, cap. 3; {OG}, cap. 7).")
        ps.append(txt)
    P = int(np.sum(lp.loop_eq.poles().real > 1e-9))
    Z = int(np.sum(T1.poles().real > 1e-9))
    ps.append("O diagrama polar (Nyquist) abaixo traça $L(j\\omega)$ no plano complexo. Pelo critério de Nyquist, "
              "$Z = N + P$, em que P é o número de polos de malha aberta no semiplano direito, N o número de voltas "
              "no sentido horário em torno de −1 e Z o número de polos de malha fechada instáveis "
              f"({OG}, cap. 7; {MZ}, cap. 3). Aqui, P = {P} e Z = {Z} com K = 1, portanto N = {Z - P}.")
    pol = polar_data(lp.loop_eq)
    return section("frequencia", "6. Resposta em frequência", ps, bullets, cites=[MZ, OG],
                   chart={"kind": "nyquist", **pol})


def sec_rootlocus(lp: Loop, d: dict) -> dict:
    j, o = d.get("j") or {}, d.get("o") or {}
    ps = [
        "O lugar das raízes mostra como os polos de malha fechada se movem quando K varia de 0 a ∞. Ele parte dos polos "
        "de malha aberta, termina nos zeros (ou no infinito, ao longo das assíntotas) e é definido pelas condições de "
        f"ângulo $\\angle L(s) = \\pm180^\\circ(2k+1)$ e de módulo $|K\\,L(s)| = 1$ ({OG}, cap. 6).",
    ]
    asy = j.get("asymptotes")
    if asy:
        ps.append(f"Aqui há {len(asy['angles'])} assíntota(s), com centroide em σ = {t(asy['centroid'])} e ângulos "
                  + ", ".join(f"{t(a)}°" for a in asy["angles"]) + ".")
    if o:
        ps.append(f"Para atender Ts < {t(o.get('ts_spec'))} s e Mp < {t(o.get('mp_spec'))}%, os polos dominantes deveriam "
                  f"estar em $s = -{m(o['sigma'])} \\pm j{m(o['wd'])}$ (ζ = {t(o['zeta'])}, ωn = {t(o['wn'])} rad/s).")
        if o.get("on_locus"):
            ps.append(f"Esse ponto pertence ao lugar das raízes, e o ganho que o atinge é K = {t(o.get('k_at_desired'))}.")
        else:
            ps.append(f"Esse ponto não pertence ao lugar das raízes: a condição de ângulo falha por {t(o.get('angle_deficiency'))}°. "
                      "Nenhum ganho proporcional coloca os polos ali; é preciso acrescentar um compensador que forneça "
                      + ("avanço de fase (zero à esquerda do polo)" if (o.get("angle_deficiency") or 0) > 0 else
                         "atraso de fase")
                      + f" com esse ângulo, que pode ser projetado pelo lugar das raízes ({OG}, cap. 6) ou pela resposta em "
                      f"frequência ({MZ}, cap. 4; {OG}, cap. 7).")
        if o.get("feasible"):
            ps.append("A varredura de K na simulação encontrou ganhos que atendem às duas especificações: " +
                      "; ".join(f"{t(a)} ≤ K ≤ {t(b)}" for a, b in o.get("feasible_ranges", [])) + ".")
        elif o.get("best"):
            b = o["best"]
            ps.append(f"Na simulação, nenhum K atende às duas especificações ao mesmo tempo; o melhor compromisso com "
                      f"Mp dentro do limite é K = {t(b['K'])}, com Ts = {t(b['ts'])} s.")
    return section("lgr", "7. Lugar das raízes e projeto do ganho", ps, cites=[OG, MZ])


def sec_pid(lp: Loop, d: dict) -> dict:
    p, q, r = d.get("p") or {}, d.get("q") or {}, d.get("r") or {}
    ps = [
        "O controlador PID, $C(s) = K_p + K_i/s + K_d s$, combina três ações: a proporcional reduz o erro e acelera a "
        "resposta, a integral elimina o erro em regime ao degrau (aumenta o tipo do sistema) e a derivativa antecipa a "
        f"tendência do erro, aumentando o amortecimento ({OG}, cap. 8).",
        "As regras de Ziegler-Nichols fornecem uma sintonia inicial: o 1º método usa o atraso L e a constante de tempo T "
        "da curva de reação em S; o 2º método usa o ganho crítico $K_u$ e o período $P_u$ da oscilação sustentada. "
        "Essas regras costumam gerar sobressinal elevado e servem como ponto de partida para um ajuste fino "
        f"({OG}, cap. 8).",
    ]
    bullets = []
    if p.get("applicable"):
        bullets.append(f"1º método: L = {t(p['L'])} s e T = {t(p['T'])} s (razão L/T = {t(p['L'] / p['T'], 3)}).")
    else:
        bullets.append(f"1º método não aplicável: {p.get('reason', '')}")
    if q.get("applicable"):
        bullets.append(f"2º método: Ku = {t(q['Ku'])} e Pu = {t(q['Pu'])} s.")
    else:
        bullets.append(f"2º método não aplicável: {q.get('reason', '')}")
    best = None
    for src, data in (("1º método", p), ("2º método", q)):
        for ctrl, info in (data.get("closed") or {}).items():
            mi = info.get("info") or {}
            if info.get("stable") and mi.get("settling_time") is not None:
                cand = (mi["settling_time"], f"{ctrl} ({src})", mi)
                if best is None or cand[0] < best[0]:
                    best = cand
    if best:
        bullets.append(f"Menor tempo de acomodação entre os controladores de Ziegler-Nichols: {best[1]}, com "
                       f"Ts = {t(best[0])} s e Mp = {t(best[2].get('overshoot'))}%.")
    if r.get("applicable") and r.get("info"):
        ri = r["info"]
        if r.get("stable"):
            bullets.append(f"PID com a média dos dois métodos: Mp = {t(ri.get('overshoot'))}%, Ts = {t(ri.get('settling_time'))} s; "
                           f"erro à rampa = {t((r.get('analysis') or {}).get('ramp', {}).get('error', {}).get('value'))}.")
        else:
            bullets.append("O PID com a média dos dois métodos resulta em malha fechada instável.")
    return section("pid", "8. Controladores PID e Ziegler-Nichols", ps, bullets, cites=[OG])


def sec_conclusion(lp: Loop, d: dict) -> dict:
    j, n, o, r, g = (d.get(k) or {} for k in "jnorg")
    T1 = lp.closed(1.0)
    bullets = []
    bullets.append(f"Com K = 1 a malha fechada é {'estável' if T1.is_stable() else 'instável'}.")
    iv = j.get("stable_intervals") or []
    if iv and iv[0][1] is not None:
        bullets.append(f"O ganho proporcional deve ficar abaixo de {t(iv[0][1])} para manter a estabilidade.")
    if n.get("applicable") and n.get("K") and not n.get("stable"):
        bullets.append("A especificação de erro em regime não é atingível só com ganho proporcional: use ação integral (PI/PID).")
    if o and not o.get("feasible"):
        bullets.append(f"As especificações de Ts e Mp exigem compensação dinâmica (avanço de fase de cerca de "
                       f"{t(abs(o.get('angle_deficiency') or 0), 3)}° ou ação derivativa).")
    elif o.get("feasible"):
        bullets.append(f"As especificações de Ts e Mp são atendidas com ganho proporcional (melhor K = {t(o['best']['K'])}).")
    mg = g.get("margins") or {}
    pm = mg.get("pm")
    if pm is not None and np.isfinite(pm) and pm < 30:
        bullets.append("A margem de fase está abaixo de 30°: espere resposta muito oscilatória e pouca robustez.")
    if r.get("applicable") and r.get("stable"):
        bullets.append("O PID de Ziegler-Nichols estabiliza a malha e zera o erro ao degrau; um ajuste fino reduz o sobressinal.")
    ps = ["Resumo dos principais resultados e recomendações para esta malha:"]
    return section("conclusao", "9. Conclusões e recomendações", ps, bullets)


BUILDERS = [sec_system, sec_model, sec_stability, sec_transient, sec_steady, sec_frequency, sec_rootlocus, sec_pid, sec_conclusion]


def build_report(lp: Loop, data: dict) -> dict:
    sections = []
    for fn in BUILDERS:
        try:
            sections.append(fn(lp, data))
        except Exception as exc:  # noqa: BLE001 - uma seção com erro não derruba o relatório
            sections.append(section(fn.__name__, fn.__name__, [f"Não foi possível gerar esta seção: {exc}"]))
    return {"sections": sections, "references": REFERENCES}
