import type { AnalysisResult, AnalyzeRequest, Example } from './types'

const BASE = import.meta.env.VITE_API_URL ?? ''

export class ApiError extends Error {
  details: Record<string, string[]>
  constructor(message: string, details: Record<string, string[]> = {}) {
    super(message)
    this.details = details
  }
}

async function handle<T>(resp: Response): Promise<T> {
  if (resp.ok) return resp.json() as Promise<T>
  let details: Record<string, string[]> = {}
  try {
    const body = await resp.json()
    details = body.errors ?? {}
  } catch {
    /* corpo não-JSON */
  }
  const first = Object.values(details).flat()[0]
  throw new ApiError(first ?? `Erro ${resp.status} ao consultar o servidor.`, details)
}

export async function analyze(req: AnalyzeRequest, signal?: AbortSignal): Promise<AnalysisResult> {
  const resp = await fetch(`${BASE}/api/analyze/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
    signal,
  })
  return handle<AnalysisResult>(resp)
}

export async function fetchExamples(): Promise<Example[]> {
  return handle<Example[]>(await fetch(`${BASE}/api/examples/`))
}

/* ---- IA (Claude) ---- */

export interface LlmStatus {
  enabled: boolean
  model: string
}

export interface DescribeResult {
  spec: import('./types').LoopSpec
  validation_error: string | null
  summary: string
  derivation: string[]
  assumptions: string[]
  questions: string[]
  model: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export async function fetchLlmStatus(): Promise<LlmStatus> {
  return handle<LlmStatus>(await fetch(`${BASE}/api/llm/status/`))
}

export async function describeSystem(text: string, signal?: AbortSignal): Promise<DescribeResult> {
  const resp = await fetch(`${BASE}/api/describe/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
    signal,
  })
  return handle<DescribeResult>(resp)
}

/** Envia a conversa ao tutor e repassa cada trecho de texto recebido (Server-Sent Events). */
export async function askTutor(request: AnalyzeRequest, messages: ChatMessage[], onDelta: (text: string) => void, signal?: AbortSignal): Promise<void> {
  const resp = await fetch(`${BASE}/api/tutor/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request, messages }),
    signal,
  })
  if (!resp.ok || !resp.body) {
    await handle(resp)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const line = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      if (!line.startsWith('data: ')) continue
      const event = JSON.parse(line.slice(6)) as { delta?: string; done?: boolean; error?: string }
      if (event.error) throw new ApiError(event.error)
      if (event.delta) onDelta(event.delta)
    }
  }
}
