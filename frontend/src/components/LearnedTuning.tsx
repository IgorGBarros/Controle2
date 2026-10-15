import { useEffect, useRef, useState } from 'react'
import { ApiError, learnedTuning, type LearnedTuning as Result, type SimMetrics, type SimParams } from '../lib/api'
import { fmt } from '../lib/format'
import type { AnalyzeRequest } from '../lib/types'
import { Note, Table } from './ui'

type Applied = { kp: number; ki: number; kd: number; anti_windup: SimParams['anti_windup']; derivative_on: SimParams['derivative_on']; n_filter?: number }

interface Props {
  request: AnalyzeRequest
  onApply: (g: Applied) => void
}

const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${fmt(v * 100, 3)} %`)
const sec = (v: number | null | undefined) => (v === null || v === undefined ? 'não acomodou' : `${fmt(v)} s`)

function row(name: string, g: { kp: number; ki: number; kd: number }, m: SimMetrics) {
  return [
    name,
    fmt(g.kp),
    fmt(g.ki),
    fmt(g.kd),
    m.diverged ? '—' : `${fmt(m.overshoot)} %`,
    m.diverged ? '—' : sec(m.settling_time),
    m.diverged ? 'divergiu' : fmt(m.iae),
  ]
}

/** Sintonia por rede neural: um MLP treinado com plantas geradas e rotuladas pela própria ferramenta. */
export function LearnedTuning({ request, onApply }: Props) {
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<Result | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Uma nova malha invalida a sugestão anterior.
  const [reqKey, setReqKey] = useState(request)
  if (reqKey !== request) {
    setReqKey(request)
    setRes(null)
    setError(null)
  }
  useEffect(() => () => abortRef.current?.abort(), [])

  const run = async () => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setBusy(true)
    setError(null)
    try {
      setRes(await learnedTuning(request, ctrl.signal))
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(e instanceof ApiError ? e.message : 'Não foi possível consultar a rede.')
    } finally {
      setBusy(false)
    }
  }

  const ev = res && res.available && res.applicable ? res.model.avaliacao : null

  return (
    <div className="tuner">
      <h3>
        <span className="ai-badge nn-badge">RN</span> Sintonia por rede neural
      </h3>
      <p className="muted small">
        Uma rede neural pequena, treinada com milhares de plantas geradas pela própria ferramenta. Para cada planta foram extraídas as grandezas dos itens do
        trabalho (L e T da curva de reação, Ku e Pu, sobressinal, ordem, polos complexos) e o otimizador encontrou os ganhos de menor IAE com sobressinal ≤ 10 %. A
        rede aprendeu esse mapeamento e responde em milissegundos, sem otimizar e sem chamar nenhuma API.
      </p>
      <div className="describe-actions">
        <button type="button" className="primary" onClick={() => void run()} disabled={busy}>
          {busy ? 'Consultando…' : 'Sugerir ganhos'}
        </button>
      </div>

      {error && <Note tone="bad">{error}</Note>}
      {res && !res.available && <Note tone="warn">{res.reason}</Note>}
      {res && res.available && !res.applicable && <Note tone="warn">{res.reason}</Note>}

      {res && res.available && res.applicable && (
        <div className="tuner-final">
          {res.warnings.length > 0 && (
            <Note tone="warn">
              Planta fora da faixa de treino; a sugestão é uma extrapolação: {res.warnings.join('; ')}.
            </Note>
          )}
          <p>
            <strong>
              Sugestão da rede: Kp = {fmt(res.gains.kp)}, Ki = {fmt(res.gains.ki)}, Kd = {fmt(res.gains.kd)}
            </strong>{' '}
            (derivada sobre a medição, N = {fmt(res.scenario.n_filter, 3)}, anti-windup por clamping).
          </p>
          <Table
            caption={`Degrau unitário em ${fmt(res.scenario.tfinal)} s de simulação, mesmas condições para os dois`}
            head={['Sintonia', 'Kp', 'Ki', 'Kd', 'Sobressinal', 'Acomodação (2%)', 'IAE']}
            rows={[row('Rede neural', res.gains, res.metrics), row('Ziegler-Nichols', res.zn.gains, res.zn.metrics)]}
          />
          <p className="muted small">
            Escalas extraídas da planta: K₀ = {fmt(res.scales.K0)}, L = {fmt(res.scales.L)} s, T = {fmt(res.scales.T)} s. A rede prevê ganhos adimensionais
            (Kp·K₀, Ki·K₀·(L+T), Kd·K₀/(L+T)), por isso serve para sistemas rápidos e lentos.
          </p>
          <button
            type="button"
            className="primary"
            onClick={() =>
              onApply({ ...res.gains, anti_windup: res.scenario.anti_windup, derivative_on: res.scenario.derivative_on, n_filter: Number(res.scenario.n_filter.toPrecision(3)) })
            }
          >
            Aplicar ao simulador
          </button>
        </div>
      )}

      {ev && res && res.available && res.applicable && (
        <details className="matlab">
          <summary>Como a rede foi avaliada</summary>
          <p className="small">
            Rede {res.model.arquitetura.join(' → ')} ({res.model.parametros} parâmetros), treinada com {res.model.n_treino} plantas e testada em {ev.n_teste}{' '}
            plantas que ela nunca viu. Cada planta de teste foi re-simulada com os ganhos previstos e comparada com o ótimo do otimizador e com Ziegler-Nichols.
          </p>
          <Table
            head={['Métrica (conjunto de teste)', 'Rede neural', 'Ziegler-Nichols']}
            rows={[
              ['IAE / IAE ótimo (mediana)', fmt(ev.iae_rel_otimo_mediana, 3), fmt(ev.zn_iae_rel_otimo_mediana, 3)],
              ['Sobressinal (mediana)', `${fmt(ev.sobressinal_mediana, 3)} %`, `${fmt(ev.zn_sobressinal_mediana, 3)} %`],
              ['Atende sobressinal ≤ 12 %', pct(ev.taxa_spec), pct(ev.zn_taxa_spec)],
              ['Malhas instáveis', String(ev.divergiu), String(ev.zn_divergiu)],
            ]}
          />
          <p className="muted small">
            A rede teve IAE menor que o Ziegler-Nichols em {pct(ev.melhor_que_zn)} das plantas de teste; em 90 % delas o IAE ficou até {fmt(ev.iae_rel_otimo_p90, 3)}×
            o ótimo. Especificação de treino: {res.model.especificacao}. Treinada em {res.model.treinado_em}.
          </p>
        </details>
      )}
      <p className="muted small">
        Escopo: realimentação unitária negativa, planta estável, sem integrador e com ganho estático positivo. Revise antes de usar em um sistema real.
      </p>
    </div>
  )
}
