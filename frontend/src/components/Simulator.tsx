import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, simulateLoop, type LlmStatus, type SimParams, type SimResult } from '../lib/api'
import { fmt } from '../lib/format'
import type { AnalysisResult, AnalyzeRequest } from '../lib/types'
import { XYChart } from './Charts'
import { SimAnimation } from './SimAnimation'
import { LearnedTuning } from './LearnedTuning'
import { TuningAssistant } from './TuningAssistant'
import { Note, Stats } from './ui'

interface Props {
  request: AnalyzeRequest
  result: AnalysisResult
  tuningStatus: Omit<LlmStatus, 'tutor' | 'tuning'>
  onRetryLlm?: () => void
}

function initialGains(result: AnalysisResult): { kp: number; ki: number; kd: number; source: string } {
  const pid = result.system.controller_pid
  if (pid) return { ...pid, source: 'PID informado na malha' }
  const r = result.items.find((it) => it.key === 'r')?.data as { applicable?: boolean; average?: { PID: { Kp: number; Ki: number | null; Kd: number | null } } } | null
  if (r?.applicable && r.average) {
    const a = r.average.PID
    return { kp: a.Kp, ki: a.Ki ?? 0, kd: a.Kd ?? 0, source: 'PID médio de Ziegler-Nichols (item r)' }
  }
  return { kp: result.params.k, ki: 0, kd: 0, source: `ganho proporcional K = ${fmt(result.params.k)}` }
}

function niceMax(v: number): number {
  const x = Math.max(Math.abs(v) * 3, 1)
  const p = 10 ** Math.floor(Math.log10(x))
  return Math.ceil(x / p) * p
}

function Slider({ label, value, onChange, max, step }: { label: ReactNode; value: number; onChange: (v: number) => void; max: number; step?: number }) {
  return (
    <label className="slider">
      <span className="slider-head">
        <span>{label}</span>
        <input type="number" step="any" value={Number(value.toPrecision(6))} onChange={(e) => Number.isFinite(Number(e.target.value)) && onChange(Number(e.target.value))} />
      </span>
      <input type="range" min={0} max={Math.max(max, value)} step={step ?? Math.max(max, value) / 500} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}

function Num({ label, value, onChange, suffix, optional }: { label: ReactNode; value: number | null; onChange: (v: number | null) => void; suffix?: string; optional?: boolean }) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="input-suffix">
        <input
          type="number"
          step="any"
          value={value ?? ''}
          placeholder={optional ? '—' : undefined}
          onChange={(e) => {
            if (e.target.value === '') return onChange(optional ? null : 0)
            const v = Number(e.target.value)
            if (Number.isFinite(v)) onChange(v)
          }}
        />
        {suffix && <em>{suffix}</em>}
      </div>
    </label>
  )
}

const sec = (v: number | null | undefined) => (v === null || v === undefined ? 'não acomodou' : `${fmt(v)} s`)

/** Simulação no tempo com saturação, anti-windup, perturbação, ruído e controlador discreto. */
export function Simulator({ request, result, tuningStatus, onRetryLlm }: Props) {
  const init = useMemo(() => initialGains(result), [result])
  const [sim, setSim] = useState<SimParams>(() => ({
    controller: 'pid',
    kp: init.kp,
    ki: init.ki,
    kd: init.kd,
    n_filter: 100,
    derivative_on: 'error',
    k: result.params.k,
    anti_windup: 'clamping',
    ts_ctrl: 0,
    u_min: null,
    u_max: null,
    ref_type: 'step',
    ref_amp: 1,
    ref_period: 20,
    ref_t0: 0,
    dist_time: null,
    dist_amp: 0,
    noise_std: 0,
    seed: 1,
    tfinal: null,
  }))
  const [ranges, setRanges] = useState(() => ({ kp: niceMax(init.kp), ki: niceMax(init.ki), kd: niceMax(init.kd) }))
  const [data, setData] = useState<SimResult | null>(null)
  const [pinned, setPinned] = useState<{ label: string; data: SimResult } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const [satOn, setSatOn] = useState(false)
  const [cursor, setCursor] = useState<number | null>(null)
  const [distOn, setDistOn] = useState(false)

  // Uma nova análise redefine os ganhos iniciais do simulador.
  const [initKey, setInitKey] = useState(init)
  if (initKey !== init) {
    setInitKey(init)
    setSim((s) => ({ ...s, kp: init.kp, ki: init.ki, kd: init.kd, k: result.params.k }))
    setRanges({ kp: niceMax(init.kp), ki: niceMax(init.ki), kd: niceMax(init.kd) })
    setPinned(null)
  }

  const set = <K extends keyof SimParams>(k: K, v: SimParams[K]) => setSim((s) => ({ ...s, [k]: v }))

  /** Mesmo diagrama do item r do trabalho: bloco PID paralelo (N = 100), degrau em t = 1 s, H(s) = 1. */
  const reproduceSimulink = () => {
    const g = initialGains(result)
    setSim((s) => ({
      ...s,
      controller: 'pid',
      kp: g.kp,
      ki: g.ki,
      kd: g.kd,
      n_filter: 100,
      derivative_on: 'error',
      ts_ctrl: 0,
      ref_type: 'step',
      ref_amp: 1,
      ref_t0: 1,
      noise_std: 0,
      tfinal: 15,
    }))
    setRanges({ kp: niceMax(g.kp), ki: niceMax(g.ki), kd: niceMax(g.kd) })
    setSatOn(false)
    setDistOn(false)
  }

  const applyTuning = (g: { kp: number; ki: number; kd: number; anti_windup: SimParams['anti_windup']; derivative_on: SimParams['derivative_on']; n_filter?: number }) => {
    setSim((s) => ({ ...s, controller: 'pid', ...g }))
    setRanges((r) => ({ kp: Math.max(r.kp, niceMax(g.kp)), ki: Math.max(r.ki, niceMax(g.ki)), kd: Math.max(r.kd, niceMax(g.kd)) }))
  }
  const effective: SimParams = useMemo(
    () => ({
      ...sim,
      u_min: satOn ? (sim.u_min ?? -10) : null,
      u_max: satOn ? (sim.u_max ?? 10) : null,
      dist_time: distOn ? (sim.dist_time ?? 0) : null,
      dist_amp: distOn ? sim.dist_amp : 0,
    }),
    [sim, satOn, distOn],
  )

  useEffect(() => {
    const timer = setTimeout(() => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setBusy(true)
      simulateLoop(request, effective, ctrl.signal)
        .then((d) => {
          setData(d)
          setCursor(null)
          setError(null)
        })
        .catch((e) => {
          if ((e as Error).name !== 'AbortError') setError(e instanceof ApiError ? e.message : 'Falha na simulação.')
        })
        .finally(() => {
          if (abortRef.current === ctrl) setBusy(false)
        })
    }, 250)
    return () => clearTimeout(timer)
  }, [request, effective])

  useEffect(() => () => abortRef.current?.abort(), [])

  const ySeries = useMemo(() => {
    if (!data) return null
    const s: Record<string, (number | null)[]> = { r: data.series.r, y: data.series.y }
    if (effective.noise_std > 0) s.ym = data.series.ym
    if (pinned) s.pinned = data.t.map((ti) => interp(pinned.data.t, pinned.data.series.y, ti))
    return s
  }, [data, pinned, effective.noise_std])

  const m = data?.metrics
  return (
    <section id="simulador" className="section simulator">
      <h2>
        <span className="letter">s)</span> Simulação no tempo
      </h2>
      <p className="muted">
        Simulação passo a passo da malha com efeitos que a análise linear não mostra: saturação do atuador, anti-windup, perturbação de carga, ruído no
        sensor e controlador discreto. O atraso de transporte é simulado de forma exata. Ganhos iniciais: {init.source}.
      </p>

      <div className="sim-layout">
        <aside className="sim-controls">
      <div className="sim-stack">
        <fieldset className="block">
          <legend>Controlador</legend>
          <div className="tabs" role="radiogroup" aria-label="Controlador da simulação">
            {(
              [
                ['pid', 'PID ajustável'],
                ['loop', 'K·C(s) da malha'],
              ] as const
            ).map(([v, label]) => (
              <button key={v} type="button" role="radio" aria-checked={sim.controller === v} className={sim.controller === v ? 'tab active' : 'tab'} onClick={() => set('controller', v)}>
                {label}
              </button>
            ))}
          </div>
          {sim.controller === 'pid' ? (
            <>
              <Slider label="Kp" value={sim.kp} max={ranges.kp} onChange={(v) => set('kp', v)} />
              <Slider label="Ki" value={sim.ki} max={ranges.ki} onChange={(v) => set('ki', v)} />
              <Slider label="Kd" value={sim.kd} max={ranges.kd} onChange={(v) => set('kd', v)} />
              <div className="row-2">
                <Num label="Filtro derivativo N" value={sim.n_filter} onChange={(v) => set('n_filter', Math.max(0.1, v ?? 20))} suffix="rad/s" />
                <label className="field">
                  <span>Anti-windup</span>
                  <select value={sim.anti_windup} onChange={(e) => set('anti_windup', e.target.value as SimParams['anti_windup'])}>
                    <option value="none">Nenhum</option>
                    <option value="clamping">Integração condicional</option>
                    <option value="back_calculation">Back-calculation</option>
                  </select>
                </label>
              </div>
              <label className="field">
                <span>Ação derivativa sobre</span>
                <select value={sim.derivative_on} onChange={(e) => set('derivative_on', e.target.value as SimParams['derivative_on'])}>
                  <option value="error">o erro (como o bloco PID do Simulink)</option>
                  <option value="measurement">a medição (sem pico na mudança de referência)</option>
                </select>
              </label>
              <div className="sim-actions">
                <button
                  type="button"
                  className="chip"
                  onClick={() => {
                    setSim((s) => ({ ...s, kp: init.kp, ki: init.ki, kd: init.kd }))
                    setRanges({ kp: niceMax(init.kp), ki: niceMax(init.ki), kd: niceMax(init.kd) })
                  }}
                >
                  Restaurar ganhos iniciais
                </button>
                <button type="button" className="chip" onClick={reproduceSimulink} title="PID paralelo com N = 100, derivada sobre o erro, degrau em t = 1 s, sem saturação">
                  Reproduzir o diagrama do Simulink (item r)
                </button>
              </div>
              <p className="muted small">
                O diagrama usa os ganhos do item r desta análise. Para os ganhos exatos do trabalho de 2013, digite Kp = 46,1129, Ki = 53,80365 e Kd = 10,2266
                (pico de 1,49, como no Scope original).
              </p>
            </>
          ) : (
            <Num label="Ganho K (multiplica C(s))" value={sim.k} onChange={(v) => set('k', v ?? 1)} />
          )}
          <Num label="Período de amostragem do controlador (0 = contínuo)" value={sim.ts_ctrl} onChange={(v) => set('ts_ctrl', Math.max(0, v ?? 0))} suffix="s" />
        </fieldset>

        <fieldset className="block">
          <legend>Atuador e sinais</legend>
          <label className="field check">
            <input type="checkbox" checked={satOn} onChange={(e) => setSatOn(e.target.checked)} />
            <span>Saturação do atuador</span>
          </label>
          {satOn && (
            <div className="row-2">
              <Num label="u mínimo" value={sim.u_min ?? -10} onChange={(v) => set('u_min', v)} />
              <Num label="u máximo" value={sim.u_max ?? 10} onChange={(v) => set('u_max', v)} />
            </div>
          )}
          <div className="row-2">
            <label className="field">
              <span>Referência</span>
              <select value={sim.ref_type} onChange={(e) => set('ref_type', e.target.value as SimParams['ref_type'])}>
                <option value="step">Degrau</option>
                <option value="square">Onda quadrada</option>
                <option value="ramp">Rampa</option>
                <option value="sine">Senoide</option>
              </select>
            </label>
            <Num label="Amplitude" value={sim.ref_amp} onChange={(v) => set('ref_amp', v ?? 1)} />
          </div>
          <Num label="Início da referência" value={sim.ref_t0} onChange={(v) => set('ref_t0', Math.max(0, v ?? 0))} suffix="s" />
          {(sim.ref_type === 'square' || sim.ref_type === 'sine') && <Num label="Período da referência" value={sim.ref_period} onChange={(v) => set('ref_period', Math.max(0.01, v ?? 10))} suffix="s" />}
          <label className="field check">
            <input type="checkbox" checked={distOn} onChange={(e) => setDistOn(e.target.checked)} />
            <span>Perturbação de carga (degrau na entrada da planta)</span>
          </label>
          {distOn && (
            <div className="row-2">
              <Num label="Instante" value={sim.dist_time ?? 0} onChange={(v) => set('dist_time', v)} suffix="s" />
              <Num label="Amplitude" value={sim.dist_amp} onChange={(v) => set('dist_amp', v ?? 0)} />
            </div>
          )}
          <div className="row-2">
            <Num label="Ruído no sensor (desvio-padrão)" value={sim.noise_std} onChange={(v) => set('noise_std', Math.max(0, v ?? 0))} />
            <Num label="Tempo de simulação" value={sim.tfinal} onChange={(v) => set('tfinal', v)} suffix="s" optional />
          </div>
        </fieldset>
      </div>

        </aside>
        <div className="sim-main">
      {error && <Note tone="bad">{error}</Note>}
      {data && ySeries && (
        <div className={busy ? 'is-loading' : ''}>
          {m?.diverged && <Note tone="bad">A saída divergiu em t ≈ {fmt(m.diverged_at)} s: a malha é instável com esses parâmetros.</Note>}
          {m && m.linear_stable === false && !m.diverged && (
            <Note tone="warn">A malha linear equivalente (sem saturação) é instável; a saturação pode estar mascarando uma oscilação crescente.</Note>
          )}
          <div className="sim-actions">
            <button type="button" className="chip" onClick={() => setPinned({ label: describePin(effective), data })}>
              Fixar esta resposta para comparar
            </button>
            {pinned && (
              <button type="button" className="chip" onClick={() => setPinned(null)}>
                Remover comparação ({pinned.label})
              </button>
            )}
          </div>
          <SimAnimation data={data} uMin={effective.u_min} uMax={effective.u_max} onTime={setCursor} />
          <XYChart
            x={data.t}
            series={ySeries}
            lines={[
              { key: 'r', label: 'Referência r(t)', color: 'var(--text-muted)', dashed: true },
              ...(effective.noise_std > 0 ? [{ key: 'ym', label: 'Medição com ruído', color: 'var(--series-4)' }] : []),
              { key: 'y', label: 'Saída y(t)', color: 'var(--series-1)' },
              ...(pinned ? [{ key: 'pinned', label: `Fixada: ${pinned.label}`, color: 'var(--series-2)', dashed: true }] : []),
            ]}
            xLabel="Tempo (s)"
            yLabel="Saída"
            title="Saída da planta"
            height={320}
            refs={[...(effective.dist_time !== null ? [{ x: effective.dist_time, label: 'perturbação' }] : []), ...(cursor !== null ? [{ x: cursor }] : [])]}
          />
          <XYChart
            x={data.t}
            series={data.series}
            lines={[
              { key: 'u', label: 'u(t) aplicado', color: 'var(--series-3)' },
              ...(effective.u_max !== null ? [{ key: 'u_raw', label: 'u calculado (antes da saturação)', color: 'var(--series-5)', dashed: true }] : []),
            ]}
            xLabel="Tempo (s)"
            yLabel="Controle"
            title="Sinal de controle"
            height={240}
            refs={[...(effective.u_max !== null ? [{ y: effective.u_max, label: 'u máx' }, { y: effective.u_min ?? -10, label: 'u mín' }] : []), ...(cursor !== null ? [{ x: cursor }] : [])]}
          />
          {m && !m.diverged && (
            <Stats
              items={[
                { label: 'IAE  ∫|e|dt', value: fmt(m.iae), hint: 'menor é melhor' },
                ...(m.overshoot !== undefined ? [{ label: 'Sobressinal', value: `${fmt(m.overshoot)} %` }] : []),
                ...(m.overshoot !== undefined ? [{ label: 'Acomodação (2%)', value: sec(m.settling_time) }] : []),
                ...(m.steady_error !== undefined ? [{ label: 'Erro final', value: fmt(m.steady_error) }] : []),
                ...(m.dist_peak !== undefined ? [{ label: 'Desvio pela perturbação', value: fmt(m.dist_peak) }] : []),
                ...(m.dist_peak !== undefined ? [{ label: 'Recuperação', value: sec(m.dist_recovery) }] : []),
                { label: 'Máx |u|', value: fmt(m.u_max_abs) },
                { label: 'Tempo saturado', value: `${fmt(m.sat_time)} s` },
                { label: 'Variação total de u', value: fmt(m.u_total_variation), hint: 'desgaste do atuador' },
              ]}
            />
          )}
          <p className="muted small">
            Passo de integração {fmt(data.dt)} s{effective.ts_ctrl > 0 ? `, controlador amostrado a cada ${fmt(data.h)} s` : ''}
            {data.delay_samples ? `, atraso exato de ${data.delay_samples} amostras` : ''}. PID na forma paralela do Simulink: Kp + Ki/s + Kd·N·s/(s + N), com a
            derivada sobre {effective.derivative_on === 'error' ? 'o erro' : 'a medição'}.
          </p>
        </div>
      )}
        </div>
      </div>
      <LearnedTuning request={request} onApply={applyTuning} />
      <TuningAssistant request={request} sim={effective} status={tuningStatus} onRetry={onRetryLlm} onApply={applyTuning} />
    </section>
  )
}

function interp(xs: number[], ys: (number | null)[], x: number): number | null {
  if (!xs.length || x < xs[0] || x > xs[xs.length - 1]) return null
  let lo = 0
  let hi = xs.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (xs[mid] <= x) lo = mid
    else hi = mid
  }
  const a = ys[lo]
  const b = ys[hi]
  if (a === null || b === null) return null
  const f = xs[hi] === xs[lo] ? 0 : (x - xs[lo]) / (xs[hi] - xs[lo])
  return a + f * (b - a)
}

function describePin(p: SimParams): string {
  const parts = p.controller === 'pid' ? [`Kp=${fmt(p.kp, 3)}`, `Ki=${fmt(p.ki, 3)}`, `Kd=${fmt(p.kd, 3)}`] : [`K=${fmt(p.k, 3)}`]
  if (p.u_max !== null) parts.push(p.anti_windup === 'none' ? 'sem anti-windup' : 'com anti-windup')
  return parts.join(', ')
}
