import { useEffect, useRef, useState, type FormEvent } from 'react'
import {
  ApiError,
  askAssistant,
  modelLabel,
  type AssistantEvent,
  type ChatMessage,
  type LlmStatus,
  type SimMetrics,
  type SimParams,
  type ToolResult,
  type TuneRecommendation,
} from '../lib/api'
import { fmt } from '../lib/format'
import type { AnalyzeRequest } from '../lib/types'
import { TUNE_GOALS } from '../lib/defaults'
import { ChatText } from './ChatText'
import { Note, OllamaOffline, Stats } from './ui'

const UNDERSTAND = [
  'Explique em palavras simples se esta malha é estável e por quê.',
  'Como interpretar as margens de ganho e de fase deste sistema?',
  'Qual a diferença entre os PIDs do 1º e do 2º método de Ziegler-Nichols aqui?',
]

export type Applied = { kp: number; ki: number; kd: number; anti_windup: SimParams['anti_windup']; derivative_on: SimParams['derivative_on'] }

type Part =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; name: string; input: Record<string, number | string>; result: ToolResult }
  | { kind: 'proposal'; rec: TuneRecommendation; metrics: SimMetrics }

type Msg = { role: 'user'; content: string } | { role: 'assistant'; parts: Part[] }

interface Props {
  request: AnalyzeRequest
  /** Cenário configurado no simulador (saturação, perturbação, ruído...). */
  sim: SimParams | null
  status: Omit<LlmStatus, 'assistant'>
  onRetry?: () => void
  onApply: (g: Applied) => void
  /** Pergunta enviada de outra aba (por exemplo, pelo atalho do simulador). */
  prompt?: { text: string; nonce: number } | null
}

const sec = (v: number | null | undefined) => (v === null || v === undefined ? 'não acomodou' : `${fmt(v)} s`)

/** Resumo de uma proposta para o histórico que volta ao modelo. */
function proposalSummary(p: { rec: TuneRecommendation; metrics: SimMetrics }): string {
  const m = p.metrics
  const res = m.diverged ? 'divergiu' : `Mp ${fmt(m.overshoot)}%, ts ${sec(m.settling_time)}, IAE ${fmt(m.iae)}`
  return `[Sintonia proposta: ${p.rec.estrutura} Kp=${fmt(p.rec.kp)}, Ki=${fmt(p.rec.ki)}, Kd=${fmt(p.rec.kd)} — ${res}]`
}

function toHistory(msgs: Msg[]): ChatMessage[] {
  return msgs.map((m) => {
    if (m.role === 'user') return m
    const text = m.parts
      .map((p) => (p.kind === 'text' ? p.text : p.kind === 'proposal' ? `\n${proposalSummary(p)}\n` : ''))
      .join('')
      .trim()
    return { role: 'assistant', content: (text || '(sem resposta)').slice(0, 5800) }
  })
}

function toolTitle(p: Extract<Part, { kind: 'tool' }>): string {
  if (p.name === 'otimizar') return `Otimizador (${String(p.input.estrutura)}, ${String(p.input.criterio).toUpperCase()})`
  if (p.name === 'sintonia_rede_neural') return 'Rede neural de sintonia'
  return 'Simulação'
}

function ToolRow({ part }: { part: Extract<Part, { kind: 'tool' }> }) {
  const r = part.result
  const m = r.metricas
  if (part.name === 'sintonia_rede_neural' && !r.disponivel) {
    return (
      <div className="tuner-tool">
        <strong>{toolTitle(part)}</strong>
        <span className="muted small">{r.motivo}</span>
      </div>
    )
  }
  return (
    <div className="tuner-tool">
      <strong>{toolTitle(part)}</strong>
      {r.ganhos && (
        <span>
          Kp = {fmt(r.ganhos.kp)}, Ki = {fmt(r.ganhos.ki)}, Kd = {fmt(r.ganhos.kd)}
        </span>
      )}
      {m && (
        <span className="muted small">
          {m.diverged ? 'divergiu' : `Mp ${fmt(m.overshoot)} % · ts ${sec(m.settling_time)} · IAE ${fmt(m.iae)} · máx |u| ${fmt(m.u_max_abs)}`}
          {r.violacoes && Object.keys(r.violacoes).length > 0 ? ` · não atendeu: ${Object.keys(r.violacoes).join(', ')}` : ''}
        </span>
      )}
    </div>
  )
}

function ProposalCard({ part, onApply }: { part: Extract<Part, { kind: 'proposal' }>; onApply: (g: Applied) => void }) {
  const { rec, metrics: m } = part
  return (
    <div className="tuner-final">
      <Note tone={rec.atendeu ? 'ok' : 'warn'}>
        {rec.atendeu ? 'Especificação atendida.' : 'Nem todas as especificações foram atendidas.'}
        {rec.especificacao && <> Especificação: {rec.especificacao}</>}
      </Note>
      <p>
        <strong>
          {rec.estrutura}: Kp = {fmt(rec.kp)}, Ki = {fmt(rec.ki)}, Kd = {fmt(rec.kd)}
        </strong>{' '}
        (derivada sobre {rec.derivative_on === 'error' ? 'o erro' : 'a medição'}, anti-windup {rec.anti_windup === 'none' ? 'desligado' : 'ligado'}).
      </p>
      {rec.resumo && <ChatText text={rec.resumo} />}
      {rec.compromissos && <ChatText text={`**Compromissos:** ${rec.compromissos}`} />}
      {!m.diverged && (
        <Stats
          items={[
            { label: 'Sobressinal', value: `${fmt(m.overshoot)} %` },
            { label: 'Acomodação (2%)', value: sec(m.settling_time) },
            { label: 'IAE', value: fmt(m.iae) },
            { label: 'Máx |u|', value: fmt(m.u_max_abs) },
          ]}
        />
      )}
      <p className="muted small">Métricas re-simuladas pelo motor de cálculo no cenário do simulador.</p>
      <button
        type="button"
        className="primary"
        onClick={() => onApply({ kp: rec.kp, ki: rec.ki, kd: rec.kd, anti_windup: rec.anti_windup, derivative_on: rec.derivative_on })}
      >
        Aplicar ao simulador
      </button>
    </div>
  )
}

/** Assistente IA: explica a malha (tutor) e sintoniza o controlador com o simulador, o otimizador e a rede neural. */
export function Assistant({ request, sim, status, onRetry, onApply, prompt }: Props) {
  const enabled = status.enabled
  const offline = status.provider === 'ollama' && status.reachable === false
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const requestKey = JSON.stringify(request)
  const [convKey, setConvKey] = useState(requestKey)

  // Uma nova análise começa uma nova conversa (o contexto mudou).
  if (convKey !== requestKey) {
    setConvKey(requestKey)
    setMessages([])
    setError(null)
  }

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [messages])

  const pushPart = (part: Part) =>
    setMessages((ms) => {
      const copy = ms.slice()
      const last = copy[copy.length - 1]
      if (last?.role !== 'assistant') return ms
      const parts = last.parts.slice()
      const tail = parts[parts.length - 1]
      if (part.kind === 'text' && tail?.kind === 'text') parts[parts.length - 1] = { kind: 'text', text: tail.text + part.text }
      else parts.push(part)
      copy[copy.length - 1] = { role: 'assistant', parts }
      return copy
    })

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || busy || !enabled || offline) return
    const before = messages
    const history = toHistory([...before, { role: 'user', content: question }])
    setMessages([...before, { role: 'user', content: question }, { role: 'assistant', parts: [] }])
    setInput('')
    setBusy(true)
    setError(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    let failed: string | null = null
    try {
      await askAssistant(
        request,
        sim,
        history,
        (e: AssistantEvent) => {
          if (e.type === 'delta') pushPart({ kind: 'text', text: e.text })
          else if (e.type === 'tool') pushPart({ kind: 'tool', name: e.name, input: e.input, result: e.result })
          else if (e.type === 'proposal') pushPart({ kind: 'proposal', rec: e.recommendation, metrics: e.metrics })
          else if (e.type === 'error') failed = e.error
        },
        ctrl.signal,
      )
    } catch (e) {
      if ((e as Error).name !== 'AbortError') failed = e instanceof ApiError ? e.message : 'Não foi possível falar com o assistente.'
    } finally {
      setBusy(false)
    }
    if (failed) {
      setError(failed)
      // sem resposta: remove a pergunta para manter a alternância usuário/assistente
      setMessages((ms) => {
        const last = ms[ms.length - 1]
        return last?.role === 'assistant' && last.parts.length === 0 ? ms.slice(0, -2) : ms
      })
    }
  }

  // Pergunta vinda de outra aba (atalho do simulador).
  const lastPrompt = useRef<number | null>(null)
  useEffect(() => {
    if (!prompt || prompt.nonce === lastPrompt.current || status.provider === undefined) return
    lastPrompt.current = prompt.nonce
    void send(prompt.text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prompt, status.provider])

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  return (
    <section id="assistente" className="section tutor no-print">
      <div className="report-head">
        <h2>
          <span className="ai-badge">IA</span> Assistente IA
        </h2>
        {messages.length > 0 && (
          <button type="button" className="chip" onClick={() => setMessages([])} disabled={busy}>
            Nova conversa
          </button>
        )}
      </div>
      {status.provider === undefined ? (
        <p className="muted small">Verificando o modelo do assistente…</p>
      ) : !enabled ? (
        <p className="muted">
          O assistente está configurado para o Claude (<code>ASSISTANT_PROVIDER=anthropic</code>), mas não há <code>ANTHROPIC_API_KEY</code> no backend.
          Remova <code>ASSISTANT_PROVIDER</code> para usar o modelo local no Ollama e reinicie o Django.
        </p>
      ) : offline ? (
        <OllamaOffline what="O assistente" model={status.model} onRetry={onRetry} />
      ) : (
        <>
          <p className="muted small">
            Pergunte sobre a malha analisada ou peça uma sintonia. O assistente explica com base em Ogata e Meza e, quando precisa de números, usa as
            ferramentas da própria aplicação: o simulador (no cenário configurado na aba Simulação), o otimizador e a rede neural de sintonia. As sintonias
            propostas são re-simuladas e podem ser aplicadas ao simulador com um clique. Modelo: {modelLabel(status)}.
          </p>
          <div className="chat" aria-live="polite">
            {messages.length === 0 && (
              <div className="suggestion-groups">
                <div>
                  <span className="muted small">Entender</span>
                  <div className="suggestions">
                    {UNDERSTAND.map((s) => (
                      <button key={s} type="button" className="chip" onClick={() => void send(s)} disabled={busy}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="muted small">Sintonizar</span>
                  <div className="suggestions">
                    {TUNE_GOALS.map((s) => (
                      <button key={s} type="button" className="chip" onClick={() => void send(s)} disabled={busy}>
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {messages.map((m, i) =>
              m.role === 'user' ? (
                <div key={i} className="bubble user">
                  <span className="who">Você</span>
                  <p>{m.content}</p>
                </div>
              ) : (
                <div key={i} className="bubble assistant">
                  <span className="who">Assistente</span>
                  {m.parts.length === 0 && busy && i === messages.length - 1 && <span className="typing">pensando…</span>}
                  {m.parts.map((p, j) =>
                    p.kind === 'text' ? (
                      <ChatText key={j} text={p.text} />
                    ) : p.kind === 'tool' ? (
                      <ToolRow key={j} part={p} />
                    ) : (
                      <ProposalCard key={j} part={p} onApply={onApply} />
                    ),
                  )}
                  {busy && i === messages.length - 1 && m.parts.length > 0 && m.parts[m.parts.length - 1].kind !== 'text' && (
                    <span className="typing">trabalhando…</span>
                  )}
                </div>
              ),
            )}
            <div ref={endRef} />
          </div>
          {error && <Note tone="bad">{error}</Note>}
          <form className="chat-input" onSubmit={submit}>
            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send(input)
                }
              }}
              placeholder="Ex.: por que o sobressinal aumenta com K? · sintonize um PI sem saturar o atuador"
              disabled={busy}
            />
            <button type="submit" className="primary" disabled={busy || !input.trim()}>
              {busy ? 'Respondendo…' : 'Enviar'}
            </button>
            {busy && (
              <button type="button" className="chip" onClick={() => abortRef.current?.abort()}>
                Parar
              </button>
            )}
          </form>
          <p className="muted small">Gerado por IA a partir dos resultados e das simulações do motor de cálculo — revise antes de usar em um sistema real.</p>
        </>
      )}
    </section>
  )
}
