"""Integração com LLM (Claude ou modelo local via Ollama): provedores, contexto da análise e entrada em
linguagem natural. O Assistente IA (tutor + sintonia) fica em assistant.py.

Princípio: os números vêm sempre do motor de cálculo (NumPy/SciPy). O modelo só
interpreta resultados (tutor) ou propõe uma malha que é validada pelo motor antes de
ser usada (entrada em linguagem natural).

Configuração (variáveis de ambiente):
    LLM_PROVIDER        "anthropic" (padrão) ou "ollama" (modelo local; ver ollama_client.py) para a
                        entrada em linguagem natural
    ASSISTANT_PROVIDER  provedor do Assistente IA: "ollama" (padrão), "anthropic" ou "auto" (segue LLM_PROVIDER)
    ANTHROPIC_API_KEY   chave da API do Claude (habilita os recursos com o provedor anthropic)
    CLAUDE_MODEL        modelo do Claude (padrão: claude-opus-5-5)
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict

import anthropic

from . import ollama_client as ollama
from .engine import InputError, Params, analyze
from .engine.loop import build_loop

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
# Em caso de recusa pelos classificadores de segurança, a API reexecuta a requisição
# em um modelo substituto escolhido pela Anthropic conforme a categoria da recusa.
FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: anthropic.Anthropic | None = None


class LLMUnavailable(RuntimeError):
    pass


DISABLED_MESSAGE = ("Recursos de IA desabilitados: defina ANTHROPIC_API_KEY no backend "
                    "ou use um modelo local com LLM_PROVIDER=ollama.")
# Recursos que rodam no modelo local (Ollama) por padrão, e a variável que troca o provedor.
FEATURE_ENV = {"assistant": "ASSISTANT_PROVIDER"}


def disabled_message(feature: str | None = None) -> str:
    env = FEATURE_ENV.get(feature or "")
    if env:
        return f"Desabilitado: {env}=anthropic exige ANTHROPIC_API_KEY. Remova {env} para usar o modelo local no Ollama."
    return DISABLED_MESSAGE


def _has_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def provider(feature: str | None = None) -> str | None:
    """Provedor de um recurso: "ollama", "anthropic" ou None (IA desabilitada).

    O Assistente IA roda no Ollama por padrão (ASSISTANT_PROVIDER); a entrada em linguagem natural
    segue LLM_PROVIDER.
    """
    if feature in FEATURE_ENV:
        choice = os.environ.get(FEATURE_ENV[feature], "ollama").strip().lower()
        if choice == "ollama":
            return "ollama"
        if choice in {"anthropic", "claude"}:
            return "anthropic" if _has_key() else None
    if os.environ.get("LLM_PROVIDER", "").strip().lower() == "ollama":
        return "ollama"
    return "anthropic" if _has_key() else None


def enabled(feature: str | None = None) -> bool:
    return provider(feature) is not None


def current_model(feature: str | None = None) -> str:
    return ollama.model() if provider(feature) == "ollama" else MODEL


def status() -> dict:
    def one(feature):
        prov = provider(feature)
        out = {"enabled": prov is not None, "provider": prov, "model": current_model(feature)}
        if prov == "ollama":
            out["reachable"] = ollama.reachable()
        return out

    return {**one(None), "assistant": one("assistant")}


def get_client() -> anthropic.Anthropic:
    global _client
    if not _has_key():
        raise LLMUnavailable(DISABLED_MESSAGE)
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, (LLMUnavailable, ollama.OllamaError)):
        return str(exc)
    if isinstance(exc, anthropic.AuthenticationError):
        return "Chave da API inválida (ANTHROPIC_API_KEY)."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "A chave da API não tem permissão para este modelo."
    if isinstance(exc, anthropic.RateLimitError):
        return "Limite de requisições da API atingido. Tente novamente em instantes."
    if isinstance(exc, anthropic.BadRequestError):
        return f"Requisição recusada pela API: {exc.message}"
    if isinstance(exc, anthropic.APIStatusError):
        return f"Erro da API ({exc.status_code}). Tente novamente."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Não foi possível conectar à API do Claude."
    return "Erro inesperado ao consultar o modelo."


# --- contexto da análise --------------------------------------------------------------

_cache: OrderedDict[str, dict] = OrderedDict()


def cached_analysis(spec: dict, params: Params) -> dict:
    """Recalcula a análise no servidor (não confiamos em números vindos do navegador)."""
    key = json.dumps({"spec": spec, "params": params.__dict__}, sort_keys=True, default=str)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    result = analyze(spec, params)
    _cache[key] = result
    if len(_cache) > 32:
        _cache.popitem(last=False)
    return result


def compact(obj, max_list: int = 24):
    """Remove séries temporais/frequenciais longas, mantendo os valores escalares."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in {"series", "t", "w", "branches", "re", "im", "scan", "plant", "oscillation", "step", "response"} and \
                    isinstance(v, (list, dict)):
                continue
            out[k] = compact(v, max_list)
        return out
    if isinstance(obj, list):
        if len(obj) > max_list and all(isinstance(x, (int, float)) or x is None for x in obj):
            return f"[{len(obj)} valores omitidos]"
        return [compact(v, max_list) for v in obj[:max_list]]
    return obj


# Campos que só servem à interface (LaTeX, código MATLAB, construções gráficas): ficam fora do contexto enxuto.
LEAN_DROP = {"matlab", "rules", "tangent", "laplace", "ode", "state_space", "blocks", "controller_tf", "pade",
             "inflection", "latex"}


def lean(obj):
    """Versão enxuta para modelos locais: sem campos de interface, vazios removidos, 4 algarismos significativos."""
    if isinstance(obj, dict):
        return {k: lean(v) for k, v in obj.items() if k not in LEAN_DROP and v not in (None, [], {})}
    if isinstance(obj, list):
        return [lean(v) for v in obj]
    if isinstance(obj, float):
        return float(f"{obj:.4g}")
    return obj


def analysis_context(result: dict, compact_mode: bool = False) -> str:
    """Resultados da análise como contexto para o modelo.

    ``compact_mode`` (modelos locais) omite o relatório em texto — ele é derivado dos itens — e os campos de
    interface, reduzindo o contexto de ~25 mil para ~12 mil caracteres, para caber em janelas de 8 mil tokens.
    """
    if compact_mode:
        data = {
            "sistema": lean(compact(result["system"], 8)),
            "parametros": result["params"],
            "itens": {it["key"]: {"titulo": it["title"], "dados": lean(compact(it["data"], 8)), "erro": it["error"]}
                      for it in result["items"]},
        }
        return ("<resultados_da_ferramenta>\n" + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
                + "\n</resultados_da_ferramenta>")
    report_text = []
    for s in result.get("report", {}).get("sections", []):
        report_text.append(f"## {s['title']}")
        report_text += s["paragraphs"]
        report_text += [f"- {b}" for b in s["bullets"]]
    data = {
        "sistema": compact(result["system"]),
        "parametros": result["params"],
        "itens": {it["key"]: {"titulo": it["title"], "dados": compact(it["data"]), "erro": it["error"]}
                  for it in result["items"]},
    }
    return (
        "<resultados_da_ferramenta>\n"
        + json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n</resultados_da_ferramenta>\n\n<relatorio_gerado>\n"
        + "\n".join(report_text)
        + "\n</relatorio_gerado>"
    )


# --- entrada em linguagem natural ----------------------------------------------------------

DESCRIBE_SYSTEM = """Você converte descrições em linguagem natural de sistemas de controle em uma malha \
para uma ferramenta de análise. A malha é r → Σ → C(s) → G(s)·e^(−θs) → y, com realimentação por H(s).

Como preencher:
- plant.mode = "tf" (num/den como polinômios em s, ex.: "10" e "s^2 + 2s + 4", ou vetores no formato do \
MATLAB "1 11.3 14 10"), "zpk" (zeros e poles como listas separadas por vírgula, ex.: "-1, -2+3j, -2-3j", e gain) \
ou "ss" (A, B, C, D no formato do MATLAB, ex.: "[0 1; -2 -3]"). Prefira "tf" a menos que o usuário forneça \
matrizes de estado ou polos/zeros explicitamente. Campos que não se aplicam ao modo escolhido ficam como "".
- Derive a função de transferência a partir das leis físicas quando o usuário descrever o sistema físico \
(massa-mola-amortecedor, motor CC, circuito RLC, tanque, térmico...). Use valores numéricos; quando um valor não \
for informado, escolha um valor típico e registre-o em "assumptions".
- controller: mode "tf" com num/den (use "1"/"1" se não houver controlador) ou "pid" com kp, ki, kd. \
Use 0 nos campos que não se aplicam.
- sensor: num/den de H(s); use "1"/"1" se a realimentação for unitária ou não mencionada.
- feedback: "negative" salvo menção explícita a realimentação positiva. delay: atraso em segundos (0 se não houver).
- derivation: passos curtos da modelagem (equações em LaTeX entre $...$), em português.
- assumptions: hipóteses e valores assumidos. questions: informações importantes que faltaram (pode ser vazio).
- Polinômios só podem conter números, s, + - * / ^ e parênteses. Polos/zeros complexos sempre com o conjugado.
- Se o texto não descrever um sistema de controle, devolva a planta "1" / "s+1" e explique em questions."""

DESCRIBE_SCHEMA = {
    "type": "object",
    "properties": {
        "plant": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["tf", "zpk", "ss"]},
                "num": {"type": "string"}, "den": {"type": "string"},
                "zeros": {"type": "string"}, "poles": {"type": "string"}, "gain": {"type": "number"},
                "A": {"type": "string"}, "B": {"type": "string"}, "C": {"type": "string"}, "D": {"type": "string"},
            },
            "required": ["mode", "num", "den", "zeros", "poles", "gain", "A", "B", "C", "D"],
            "additionalProperties": False,
        },
        "controller": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["tf", "pid"]},
                "num": {"type": "string"}, "den": {"type": "string"},
                "kp": {"type": "number"}, "ki": {"type": "number"}, "kd": {"type": "number"},
            },
            "required": ["mode", "num", "den", "kp", "ki", "kd"],
            "additionalProperties": False,
        },
        "sensor": {
            "type": "object",
            "properties": {"num": {"type": "string"}, "den": {"type": "string"}},
            "required": ["num", "den"],
            "additionalProperties": False,
        },
        "feedback": {"type": "string", "enum": ["negative", "positive"]},
        "delay": {"type": "number"},
        "summary": {"type": "string"},
        "derivation": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["plant", "controller", "sensor", "feedback", "delay", "summary", "derivation", "assumptions", "questions"],
    "additionalProperties": False,
}


def normalize_spec(raw: dict) -> dict:
    """Converte a saída do modelo no formato aceito por build_loop (somente os campos do modo)."""
    try:
        return _normalize_spec(raw)
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InputError("O modelo devolveu uma malha incompleta. Tente reformular a descrição.") from exc


def _normalize_spec(raw: dict) -> dict:
    p = raw["plant"]
    mode = p["mode"]
    plant = {"mode": mode}
    if mode == "tf":
        plant.update(num=p["num"], den=p["den"])
    elif mode == "zpk":
        plant.update(zeros=p["zeros"], poles=p["poles"], gain=p["gain"] or 1.0)
    else:
        plant.update(A=p["A"], B=p["B"], C=p["C"], D=p["D"] or "0")
    c = raw["controller"]
    controller = ({"mode": "pid", "kp": c["kp"], "ki": c["ki"], "kd": c["kd"]} if c["mode"] == "pid"
                  else {"mode": "tf", "num": c["num"] or "1", "den": c["den"] or "1"})
    return {
        "plant": plant,
        "controller": controller,
        "sensor": {"num": raw["sensor"]["num"] or "1", "den": raw["sensor"]["den"] or "1"},
        "feedback": raw["feedback"],
        "delay": max(0.0, float(raw["delay"] or 0.0)),
        "pade_order": 3 if raw["delay"] else 2,
    }


def _describe_ollama(text: str) -> tuple[str, str]:
    msg = ollama.chat([{"role": "user", "content": text}], DESCRIBE_SYSTEM, fmt=DESCRIBE_SCHEMA)
    if msg.get("done_reason") == "length":
        raise InputError("A resposta do modelo foi interrompida. Tente uma descrição mais curta.")
    return msg.get("content") or "", ollama.model()


def describe(text: str) -> dict:
    """Linguagem natural → malha validada pelo motor de cálculo."""
    if provider() == "ollama":
        payload, model_name = _describe_ollama(text)
    else:
        payload, model_name = _describe_claude(text)
    if not payload:
        raise InputError("O modelo não retornou uma malha.")
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InputError("O modelo não devolveu um JSON válido. Tente novamente.") from exc
    spec = normalize_spec(raw)
    validation_error = None
    try:
        build_loop(spec)  # o motor valida a malha proposta pelo modelo
    except InputError as exc:
        validation_error = str(exc)

    def strings(key):
        v = raw.get(key)
        return [str(x) for x in v] if isinstance(v, list) else []

    return {
        "spec": spec,
        "validation_error": validation_error,
        "summary": str(raw.get("summary") or ""),
        "derivation": strings("derivation"),
        "assumptions": strings("assumptions"),
        "questions": strings("questions"),
        "model": model_name,
    }


def _describe_claude(text: str) -> tuple[str, str]:
    client = get_client()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=[{"type": "text", "text": DESCRIBE_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": text}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": DESCRIBE_SCHEMA}},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise InputError("O modelo não conseguiu interpretar esta descrição. Tente reformulá-la.")
    if response.stop_reason == "max_tokens":
        raise InputError("A resposta do modelo foi interrompida. Tente uma descrição mais curta.")
    payload = next((b.text for b in response.content if b.type == "text"), None)
    return payload or "", response.model
