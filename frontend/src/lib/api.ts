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
