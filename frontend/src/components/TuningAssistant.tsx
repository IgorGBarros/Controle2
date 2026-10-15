import { useEffect, useRef, useState } from 'react'
import { ApiError, tuneController, type SimMetrics, type SimParams, type TuneEvent, type TuneRecommendation } from '../lib/api'
import { fmt } from '../lib/format'
import type { AnalyzeRequest } from '../lib/types'
import { ChatText } from './ChatText'
import { Note, Stats, Table } from './ui'

const GOALS = [
  'Quero sobressinal abaixo de 5%, mesmo que a resposta fique mais lenta.',
  'O atuador satura em ±10: minimize o tempo de acomodação sem windup.',
  'Rejeitar rápido uma perturbação de carga, com pouco ruído no sinal de controle.',
  'Resposta mais rápida possível com sobressinal até 10% e |u| ≤ 50.',
]

type Applied = { kp: number; ki: number; kd: number; anti_windup: SimParams['anti_windup']; derivative_on: SimParams['derivative_on'] }

interface Props {
  request: AnalyzeRequest
  sim: SimParams
  enabled: boolean
  onApply: (g: Applied) => void
}

type LogItem =
  | { kind: 'text'; text: string }
  | { kind: 'tool'; name: string; input: Record<string, number | string>; gains: { kp: number; ki: number; kd: number }; metrics: SimMetrics; violations?: Record<string, unknown> }

const sec = (v: number | null | undefined) => (v === null || v === undefined ? 'não acomodou' : `${fmt(v)} s`)
const ESTRUTURA_DESC: Record<string, string> = { P: 'P', PI: 'PI', PD: 'PD', PID: 'PID' }

/** Assistente de sintonia: o Claude define a especificação e usa o simulador e o otimizador como ferramentas. */
export function TuningAssistant({ request, sim, enabled, onApply }: Props) {
  const [goal, setGoal] = useState('')
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState<LogItem[]>([])
  const [final, setFinal] = useState<{ rec: TuneRecommendation; metrics: SimMetrics } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  const run = async () => {
    if (busy || goal.trim().length < 3) return
    setBusy(true)
    setLog([])
    setFinal(null)
    setError(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await tuneController(
        request,
        sim,
        goal,
        (e: TuneEvent) => {
          if (e.type === 'text') setLog((l) => [...l, { kind: 'text', text: e.text }])
          else if (e.type === 'tool')
            setLog((l) => [...l, { kind: 'tool', name: e.name, input: e.input, gains: e.result.ganhos, metrics: e.result.metricas, violations: e.result.violacoes }])
          else if (e.type === 'final') setFinal({ rec: e.recommendation, metrics: e.metrics })
          else if (e.type === 'error') setError(e.error)
        },
        ctrl.signal,
      )
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(e instanceof ApiError ? e.message : 'Não foi possível consultar o assistente.')
    } finally {
      setBusy(false)
    }
  }

  const tools = log.filter((x): x is Extract<LogItem, { kind: 'tool' }> => x.kind === 'tool')

  return (
    <div className="tuner">
      <h3>
        <span className="ai-badge">IA</span> Assistente de sintonia
      </h3>
      {!enabled ? (
        <p className="muted small">
          Desabilitado neste servidor: defina <code>ANTHROPIC_API_KEY</code> no backend para usar.
        </p>
      ) : (
        <>
          <p className="muted small">
            Descreva o que você quer da resposta. O assistente transforma o objetivo em especificações, escolhe a estrutura do controlador e usa o simulador e
            um otimizador numérico para encontrar os ganhos, no cenário configurado acima (saturação, perturbação, ruído). Os números vêm sempre do motor de
            cálculo.
          </p>
          <textarea rows={2} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Ex.: sobressinal abaixo de 5% sem saturar o atuador" disabled={busy} />
          <div className="describe-actions">
            <button type="button" className="primary" onClick={() => void run()} disabled={busy || goal.trim().length < 3}>
              {busy ? 'Sintonizando…' : 'Sintonizar'}
            </button>
            {busy && (
              <button type="button" className="chip" onClick={() => abortRef.current?.abort()}>
                Cancelar
              </button>
            )}
            {GOALS.map((g) => (
              <button key={g} type="button" className="chip" onClick={() => setGoal(g)} disabled={busy} title={g}>
                {g.length > 48 ? `${g.slice(0, 46)}…` : g}
              </button>
            ))}
          </div>

          {log.length > 0 && (
            <div className="tuner-log" aria-live="polite">
              {log.map((item, i) =>
                item.kind === 'text' ? (
                  <div key={i} className="bubble assistant">
                    <ChatText text={item.text} />
                  </div>
                ) : (
                  <div key={i} className="tuner-tool">
                    <strong>{item.name === 'otimizar' ? `Otimizador (${ESTRUTURA_DESC[String(item.input.estrutura)] ?? ''}, ${String(item.input.criterio).toUpperCase()})` : 'Simulação'}</strong>
                    <span>
                      Kp = {fmt(item.gains.kp)}, Ki = {fmt(item.gains.ki)}, Kd = {fmt(item.gains.kd)} · derivada sobre {item.input.derivative_on === 'error' ? 'o erro' : 'a medição'} ·
                      anti-windup {String(item.input.anti_windup) === 'none' ? 'desligado' : 'ligado'}
                    </span>
                    <span className="muted small">
                      {item.metrics.diverged
                        ? 'divergiu'
                        : `Mp ${fmt(item.metrics.overshoot)} % · ts ${sec(item.metrics.settling_time)} · IAE ${fmt(item.metrics.iae)} · máx |u| ${fmt(item.metrics.u_max_abs)}`}
                      {item.violations && Object.keys(item.violations).length > 0 ? ` · não atendeu: ${Object.keys(item.violations).join(', ')}` : ''}
                    </span>
                  </div>
                ),
              )}
              {busy && <p className="typing">trabalhando…</p>}
            </div>
          )}

          {error && <Note tone="bad">{error}</Note>}

          {final && (
            <div className="tuner-final">
              <Note tone={final.rec.atendeu ? 'ok' : 'warn'}>
                {final.rec.atendeu ? 'Especificação atendida.' : 'Nem todas as especificações foram atendidas — veja o compromisso abaixo.'}{' '}
                {final.rec.especificacao && <>Especificação: {final.rec.especificacao}</>}
              </Note>
              <p>
                <strong>
                  Recomendação: {final.rec.estrutura} com Kp = {fmt(final.rec.kp)}, Ki = {fmt(final.rec.ki)}, Kd = {fmt(final.rec.kd)}
                </strong>{' '}
                (derivada sobre {final.rec.derivative_on === 'error' ? 'o erro' : 'a medição'}, anti-windup {final.rec.anti_windup === 'none' ? 'desligado' : 'ligado'}).
              </p>
              <ChatText text={final.rec.resumo} />
              {final.rec.compromissos && <ChatText text={`**Compromissos:** ${final.rec.compromissos}`} />}
              {!final.metrics.diverged && (
                <Stats
                  items={[
                    { label: 'Sobressinal', value: `${fmt(final.metrics.overshoot)} %` },
                    { label: 'Acomodação (2%)', value: sec(final.metrics.settling_time) },
                    { label: 'IAE', value: fmt(final.metrics.iae) },
                    { label: 'Máx |u|', value: fmt(final.metrics.u_max_abs) },
                    { label: 'Tempo saturado', value: `${fmt(final.metrics.sat_time)} s` },
                  ]}
                />
              )}
              <p className="muted small">Métricas re-simuladas pelo motor de cálculo com o passo fino.</p>
              <button
                type="button"
                className="primary"
                onClick={() => onApply({ kp: final.rec.kp, ki: final.rec.ki, kd: final.rec.kd, anti_windup: final.rec.anti_windup, derivative_on: final.rec.derivative_on })}
              >
                Aplicar ao simulador
              </button>
            </div>
          )}

          {tools.length > 1 && (
            <details className="matlab">
              <summary>Tabela das {tools.length} tentativas</summary>
              <Table
                head={['#', 'Ferramenta', 'Kp', 'Ki', 'Kd', 'Mp (%)', 'ts (s)', 'IAE', 'máx |u|']}
                rows={tools.map((t, i) => [
                  i + 1,
                  t.name,
                  fmt(t.gains.kp),
                  fmt(t.gains.ki),
                  fmt(t.gains.kd),
                  t.metrics.diverged ? '—' : fmt(t.metrics.overshoot),
                  t.metrics.diverged ? '—' : sec(t.metrics.settling_time),
                  t.metrics.diverged ? 'divergiu' : fmt(t.metrics.iae),
                  t.metrics.diverged ? '—' : fmt(t.metrics.u_max_abs),
                ])}
              />
            </details>
          )}
          <p className="muted small">Gerado por IA a partir de simulações do motor de cálculo — revise antes de usar em um sistema real.</p>
        </>
      )}
    </div>
  )
}
