"""Cliente mínimo da API nativa do Ollama (/api/chat), só com a biblioteca padrão.

Permite usar um modelo local (por exemplo, ``qwen3.5``) no lugar do Claude nos recursos de IA
(o tutor e o assistente de sintonia usam o Ollama por padrão):
tutor (streaming), entrada em linguagem natural (saída estruturada por JSON Schema) e
assistente de sintonia (chamada de ferramentas).

Configuração (variáveis de ambiente):
    OLLAMA_HOST       endereço do servidor (padrão: http://localhost:11434)
    OLLAMA_MODEL      modelo (padrão: qwen3.5)
    OLLAMA_NUM_CTX    janela de contexto em tokens (padrão: 8192; o contexto enxuto da análise ocupa
                      ~4 mil). Se faltar memória, o cliente tenta de novo com MIN_CTX.
    OLLAMA_THINK      1 para habilitar o modo de raciocínio do modelo (mais lento; padrão: 0)
    OLLAMA_TIMEOUT    tempo máximo de uma requisição, em segundos (padrão: 600)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Iterator


MIN_CTX = 6144  # menor janela que ainda comporta o contexto enxuto da análise e a resposta
MEMORY_HINTS = ("out of memory", "out-of-memory", "failed to allocate", "requires more system memory",
                "insufficient memory", "not enough memory")


class OllamaError(RuntimeError):
    def __init__(self, message: str, memory: bool = False):
        super().__init__(message)
        self.memory = memory


def host() -> str:
    h = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    return h if h.startswith(("http://", "https://")) else f"http://{h}"


def model() -> str:
    return os.environ.get("OLLAMA_MODEL", "qwen3.5")


def _options() -> dict:
    return {"num_ctx": int(os.environ.get("OLLAMA_NUM_CTX", "8192")), "temperature": 0.3}


def _think() -> bool:
    return os.environ.get("OLLAMA_THINK", "0").lower() in {"1", "true", "yes", "sim"}


def _post(path: str, body: dict, timeout: float | None = None):
    req = urllib.request.Request(f"{host()}{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=timeout or float(os.environ.get("OLLAMA_TIMEOUT", "600")))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode()).get("error", "")
        except Exception:  # noqa: BLE001
            pass
        if exc.code == 404 and "not found" in detail:
            raise OllamaError(f"Modelo '{model()}' não encontrado no Ollama. Rode: ollama pull {model()}") from exc
        if any(h in detail.lower() for h in MEMORY_HINTS):
            raise OllamaError(memory_message(), memory=True) from exc
        raise OllamaError(f"Erro do Ollama ({exc.code}): {detail or exc.reason}") from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        raise OllamaError(unreachable_message()) from exc


def _open_chat(body: dict):
    """POST /api/chat; se o modelo não couber na memória, tenta de novo com uma janela de contexto menor."""
    try:
        return _post("/api/chat", body)
    except OllamaError as exc:
        if not exc.memory or body["options"]["num_ctx"] <= MIN_CTX:
            raise
    body["options"]["num_ctx"] = MIN_CTX
    return _post("/api/chat", body)


def memory_message() -> str:
    return (f"Memória insuficiente para carregar o modelo '{model()}' no Ollama, mesmo com a janela de contexto "
            f"reduzida. Feche outros programas pesados ou use uma variante menor do modelo (por exemplo, "
            f"ollama pull qwen3.5:4b e OLLAMA_MODEL=qwen3.5:4b; veja as variantes em ollama.com/library/qwen3.5).")


def unreachable_message() -> str:
    return (f"Não foi possível conectar ao Ollama em {host()}. Verifique se ele está rodando (ollama serve) "
            f"e se o modelo foi baixado (ollama pull {model()}).")


def tools_schema(tools: list[dict]) -> list[dict]:
    """Converte ferramentas no formato da API do Claude para o formato do Ollama."""
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in tools]


def chat(messages: list[dict], system: str | None = None, *, fmt: dict | None = None,
         tools: list[dict] | None = None) -> dict:
    """Uma rodada sem streaming. Devolve a mensagem do assistente ({content, tool_calls?})."""
    body = {"model": model(), "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "stream": False, "think": _think(), "options": _options()}
    if fmt is not None:
        body["format"] = fmt
    if tools:
        body["tools"] = tools_schema(tools)
    with _open_chat(body) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise OllamaError(str(data["error"]))
    msg = data.get("message") or {}
    msg["done_reason"] = data.get("done_reason")
    return msg


def chat_stream(messages: list[dict], system: str | None = None) -> Iterator[str]:
    """Rodada com streaming: produz pedaços de texto da resposta (o raciocínio, se houver, é descartado)."""
    body = {"model": model(), "messages": ([{"role": "system", "content": system}] if system else []) + messages,
            "stream": True, "think": _think(), "options": _options()}
    with _open_chat(body) as resp:
        for line in resp:
            if not line.strip():
                continue
            data = json.loads(line.decode())
            if data.get("error"):
                raise OllamaError(str(data["error"]))
            text = (data.get("message") or {}).get("content")
            if text:
                yield text
            if data.get("done"):
                if data.get("done_reason") == "length":
                    yield "\n\n(Resposta interrompida por tamanho.)"
                break


def reachable(timeout: float = 1.5) -> bool:
    try:
        req = urllib.request.Request(f"{host()}/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False
