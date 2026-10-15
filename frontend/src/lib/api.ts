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

/* ---- Simulação no tempo ---- */

export interface SimParams {
  controller: 'pid' | 'loop'
  kp: number
  ki: number
  kd: number
  n_filter: number
  k: number
  anti_windup: 'none' | 'clamping' | 'back_calculation'
  ts_ctrl: number
  u_min: number | null
  u_max: number | null
  ref_type: 'step' | 'square' | 'ramp' | 'sine'
  ref_amp: number
  ref_period: number
  dist_time: number | null
  dist_amp: number
  noise_std: number
  seed: number
  tfinal: number | null
}

export interface SimMetrics {
  diverged: boolean
  diverged_at?: number
  linear_stable?: boolean
  iae?: number
  ise?: number
  itae?: number
  u_max_abs?: number
  u_energy?: number
  u_total_variation?: number
  sat_time?: number
  overshoot?: number
  settling_time?: number | null
  steady_error?: number
  dist_peak?: number
  dist_recovery?: number | null
}

export interface SimResult {
  t: number[]
  series: Record<'r' | 'y' | 'ym' | 'u' | 'u_raw' | 'e' | 'd', (number | null)[]>
  metrics: SimMetrics
  dt: number
  h: number
  delay_samples: number
  tfinal: number
}

export async function simulateLoop(request: AnalyzeRequest, sim: SimParams, signal?: AbortSignal): Promise<SimResult> {
  const resp = await fetch(`${BASE}/api/simulate/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ request, sim }),
    signal,
  })
  return handle<SimResult>(resp)
}
