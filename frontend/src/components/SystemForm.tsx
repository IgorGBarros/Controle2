import { useState, type FormEvent, type ReactNode } from 'react'
import { completeLoop, DEFAULT_LOOP, DEFAULT_PARAMS } from '../lib/defaults'
import type { AnalyzeParams, AnalyzeRequest, ControllerSpec, Example, Feedback, LoopSpec, PlantSpec } from '../lib/types'
import { LoopDiagram } from './LoopDiagram'

interface Props {
  examples: Example[]
  loading: boolean
  onSubmit: (req: AnalyzeRequest) => void
  fieldErrors: Record<string, string[]>
}

type ParamField = Exclude<keyof AnalyzeParams, 'zn_include_gain'>

function errorsOf(fieldErrors: Record<string, unknown>, ...keys: string[]): string[] {
  const out: string[] = []
  const walk = (v: unknown) => {
    if (typeof v === 'string') out.push(v)
    else if (Array.isArray(v)) v.forEach(walk)
    else if (v && typeof v === 'object') Object.values(v).forEach(walk)
  }
  keys.forEach((k) => walk(fieldErrors[k]))
  return out
}

function Tabs<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="tabs" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} className={value === v ? 'tab active' : 'tab'} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  )
}

function TextField({ label, value, onChange, placeholder, mono = true, multiline = false }: { label: ReactNode; value: string; onChange: (v: string) => void; placeholder?: string; mono?: boolean; multiline?: boolean }) {
  return (
    <label className={`field ${mono ? 'mono' : ''}`}>
      <span>{label}</span>
      {multiline ? (
        <textarea rows={2} value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} spellCheck={false} />
      ) : (
        <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} spellCheck={false} />
      )}
    </label>
  )
}

function NumberField({ label, value, onChange, optional, suffix, scale = 1, step = 'any', min }: { label: ReactNode; value: number | null | undefined; onChange: (v: number | null) => void; optional?: boolean; suffix?: string; scale?: number; step?: string; min?: number }) {
  const [raw, setRaw] = useState<string | null>(null)
  const shown = raw ?? (value === null || value === undefined ? '' : String(Number((value * scale).toPrecision(10))))
  return (
    <label className="field">
      <span>{label}</span>
      <div className="input-suffix">
        <input
          type="number"
          inputMode="decimal"
          step={step}
          min={min}
          value={shown}
          placeholder={optional ? 'automático' : undefined}
          onChange={(e) => {
            setRaw(e.target.value)
            if (e.target.value === '') {
              if (optional) onChange(null)
              return
            }
            const v = Number(e.target.value) / scale
            if (Number.isFinite(v)) onChange(v)
          }}
          onBlur={() => setRaw(null)}
        />
        {suffix && <em>{suffix}</em>}
      </div>
    </label>
  )
}

export function SystemForm({ examples, loading, onSubmit, fieldErrors }: Props) {
  const [loop, setLoop] = useState<Required<LoopSpec>>(completeLoop(DEFAULT_LOOP))
  const [params, setParams] = useState<AnalyzeParams>(DEFAULT_PARAMS)
  const [formKey, setFormKey] = useState(0)

  const plant = loop.plant
  const ctrl = loop.controller
  const setPlant = (patch: Partial<PlantSpec>) => setLoop((l) => ({ ...l, plant: { ...l.plant, ...patch } }))
  const setCtrl = (patch: Partial<ControllerSpec>) => setLoop((l) => ({ ...l, controller: { ...l.controller, ...patch } }))
  const setSensor = (patch: { num?: string; den?: string }) => setLoop((l) => ({ ...l, sensor: { ...l.sensor, ...patch } }))
  const setParam = <K extends keyof AnalyzeParams>(k: K, v: AnalyzeParams[K]) => setParams((p) => ({ ...p, [k]: v }))

  const paramField = (key: ParamField, label: string, opts: { optional?: boolean; scale?: number; suffix?: string } = {}) => (
    <NumberField label={label} value={params[key] as number | null} onChange={(v) => setParam(key, v as never)} {...opts} />
  )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit({ ...params, ...loop })
  }

  const loadExample = (ex: Example) => {
    const next = completeLoop(ex.spec)
    setLoop(next)
    setFormKey((k) => k + 1)
    onSubmit({ ...params, ...next })
  }

  const ctrlLabel = ctrl.mode === 'pid' ? 'K·PID(s)' : ctrl.num === '1' && ctrl.den === '1' ? 'K' : 'K·C(s)'
  const sensorUnity = (loop.sensor.num ?? '1').trim() === '1' && (loop.sensor.den ?? '1').trim() === '1'
  const plantErrors = errorsOf(fieldErrors, 'plant', 'system', 'num', 'den')

  return (
    <form className="system-form" onSubmit={submit} key={formKey}>
      <div className="form-grid">
        <fieldset className="block">
          <legend>Planta G(s)</legend>
          <Tabs
            label="Forma de entrada da planta"
            value={plant.mode}
            onChange={(mode) => setPlant({ mode })}
            options={[
              ['tf', 'Função de transferência'],
              ['zpk', 'Zeros / polos / ganho'],
              ['ss', 'Espaço de estados'],
            ]}
          />
          {plant.mode === 'tf' && (
            <div className="tf-inputs">
              <TextField label="Numerador" value={plant.num ?? ''} onChange={(num) => setPlant({ num })} placeholder="ex.: 1   ou   2(s+3)" />
              <div className="frac-bar" aria-hidden />
              <TextField label="Denominador" value={plant.den ?? ''} onChange={(den) => setPlant({ den })} placeholder="ex.: 1 11.3 14 10   ou   (s+10)(s^2+1.3s+1)" />
              <p className="hint">
                Coeficientes no formato do MATLAB (maior potência primeiro) ou uma expressão em <code>s</code>.
              </p>
            </div>
          )}
          {plant.mode === 'zpk' && (
            <div className="tf-inputs">
              <TextField label="Zeros" value={plant.zeros ?? ''} onChange={(zeros) => setPlant({ zeros })} placeholder="ex.: -3   (vazio = sem zeros)" />
              <TextField label="Polos" value={plant.poles ?? ''} onChange={(poles) => setPlant({ poles })} placeholder="ex.: -10, -0.65+0.76j, -0.65-0.76j" />
              <NumberField label="Ganho k" value={plant.gain ?? 1} onChange={(gain) => setPlant({ gain: gain ?? 1 })} />
              <p className="hint">Separe por vírgula. Polos e zeros complexos devem vir com o conjugado.</p>
            </div>
          )}
          {plant.mode === 'ss' && (
            <div className="ss-inputs">
              <TextField label="A" value={plant.A ?? ''} onChange={(A) => setPlant({ A })} placeholder="[0 1; -2 -3]" />
              <TextField label="B" value={plant.B ?? ''} onChange={(B) => setPlant({ B })} placeholder="[0; 1]" />
              <TextField label="C" value={plant.C ?? ''} onChange={(C) => setPlant({ C })} placeholder="[1 0]" />
              <TextField label="D" value={plant.D ?? ''} onChange={(D) => setPlant({ D })} placeholder="0" />
              <p className="hint">Formato do MATLAB: linhas separadas por “;”. Sistema SISO (uma entrada, uma saída).</p>
            </div>
          )}
          <div className="row-2">
            <NumberField label="Atraso de transporte θ" value={loop.delay} onChange={(v) => setLoop((l) => ({ ...l, delay: Math.max(0, v ?? 0) }))} suffix="s" min={0} />
            <NumberField label="Ordem de Padé" value={loop.pade_order} onChange={(v) => setLoop((l) => ({ ...l, pade_order: Math.min(6, Math.max(1, Math.round(v ?? 2))) }))} step="1" min={1} />
          </div>
          {plantErrors.length > 0 && <small className="field-error">{plantErrors.join(' ')}</small>}
        </fieldset>

        <fieldset className="block">
          <legend>Malha</legend>
          <LoopDiagram controller={ctrlLabel} plant={loop.delay ? 'G(s)·e^(−θs)' : 'G(s)'} sensor={sensorUnity ? 'H = 1' : 'H(s)'} feedback={loop.feedback} delay={loop.delay || undefined} />
          <div className="loop-fields">
            <div>
              <span className="sub">Controlador C(s)</span>
              <Tabs
                label="Tipo de controlador"
                value={ctrl.mode}
                onChange={(mode) => setCtrl({ mode })}
                options={[
                  ['tf', 'Função de transferência'],
                  ['pid', 'PID'],
                ]}
              />
              {ctrl.mode === 'tf' ? (
                <div className="row-2">
                  <TextField label="Numerador" value={ctrl.num ?? '1'} onChange={(num) => setCtrl({ num })} placeholder="1" />
                  <TextField label="Denominador" value={ctrl.den ?? '1'} onChange={(den) => setCtrl({ den })} placeholder="1" />
                </div>
              ) : (
                <div className="row-3">
                  <NumberField label="Kp" value={ctrl.kp ?? 0} onChange={(kp) => setCtrl({ kp: kp ?? 0 })} />
                  <NumberField label="Ki" value={ctrl.ki ?? 0} onChange={(ki) => setCtrl({ ki: ki ?? 0 })} />
                  <NumberField label="Kd" value={ctrl.kd ?? 0} onChange={(kd) => setCtrl({ kd: kd ?? 0 })} />
                </div>
              )}
              {errorsOf(fieldErrors, 'controller').length > 0 && <small className="field-error">{errorsOf(fieldErrors, 'controller').join(' ')}</small>}
            </div>
            <div>
              <span className="sub">Sensor / realimentação H(s)</span>
              <div className="row-2">
                <TextField label="Numerador" value={loop.sensor.num ?? '1'} onChange={(num) => setSensor({ num })} placeholder="1" />
                <TextField label="Denominador" value={loop.sensor.den ?? '1'} onChange={(den) => setSensor({ den })} placeholder="1" />
              </div>
              <Tabs<Feedback>
                label="Sinal da realimentação"
                value={loop.feedback}
                onChange={(feedback) => setLoop((l) => ({ ...l, feedback }))}
                options={[
                  ['negative', 'Realimentação negativa (−)'],
                  ['positive', 'Positiva (+)'],
                ]}
              />
            </div>
          </div>
          <p className="hint">
            O ganho K dos itens e, i, j, n e o multiplica C(s). Nos itens p, q e r o controlador C(s) é substituído pelo P/PI/PID de Ziegler-Nichols.
          </p>
        </fieldset>
      </div>

      <div className="params">
        {paramField('k', 'Ganho K (itens e, g, i)')}
        {paramField('ess_target', 'Erro em regime (item n)', { scale: 100, suffix: '%' })}
        {paramField('ts_spec', 'Ts máximo (item o)', { suffix: 's' })}
        {paramField('mp_spec', 'Mp máximo (item o)', { suffix: '%' })}
      </div>

      <details className="advanced">
        <summary>Parâmetros avançados</summary>
        <div className="params">
          {paramField('k_step', 'K para degrau (item i)', { optional: true })}
          {paramField('k_ramp', 'K para rampa (item i)', { optional: true })}
          {paramField('k_impulse', 'K para impulso (item i)', { optional: true })}
          {paramField('sine_freq', 'Frequência da senoide (item r)', { suffix: 'rad/s' })}
          {paramField('sine_amp', 'Amplitude da senoide (item r)')}
          {paramField('tfinal', 'Tempo de simulação', { optional: true, suffix: 's' })}
          <label className="field check">
            <input type="checkbox" checked={params.zn_include_gain} onChange={(e) => setParam('zn_include_gain', e.target.checked)} />
            <span>Ziegler-Nichols (1º método): normalizar pelo ganho do processo</span>
          </label>
        </div>
      </details>

      <div className="actions">
        <button type="submit" className="primary" disabled={loading}>
          {loading ? 'Calculando…' : 'Analisar malha'}
        </button>
        {examples.length > 0 && (
          <div className="examples">
            <span>Exemplos:</span>
            {examples.map((ex) => (
              <button type="button" key={ex.name} className="chip" title={ex.description} onClick={() => loadExample(ex)} disabled={loading}>
                {ex.name}
              </button>
            ))}
          </div>
        )}
      </div>
    </form>
  )
}
