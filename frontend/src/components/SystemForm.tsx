import { useState, type FormEvent } from 'react'
import { DEFAULT_REQUEST } from '../lib/defaults'
import type { AnalyzeRequest, Example } from '../lib/types'


interface Props {
  examples: Example[]
  loading: boolean
  onSubmit: (req: AnalyzeRequest) => void
  fieldErrors: Record<string, string[]>
}

type NumField = Exclude<keyof AnalyzeRequest, 'num' | 'den' | 'zn_include_gain'>

export function SystemForm({ examples, loading, onSubmit, fieldErrors }: Props) {
  const [req, setReq] = useState<AnalyzeRequest>(DEFAULT_REQUEST)
  const [raw, setRaw] = useState<Record<string, string>>({})

  const set = <K extends keyof AnalyzeRequest>(k: K, v: AnalyzeRequest[K]) => setReq((r) => ({ ...r, [k]: v }))

  const numInput = (key: NumField, label: string, opts: { optional?: boolean; scale?: number; suffix?: string; step?: string } = {}) => {
    const scale = opts.scale ?? 1
    const current = req[key]
    const shown = raw[key] ?? (current === null || current === undefined ? '' : String(Number(((current as number) * scale).toPrecision(10))))
    return (
      <label className="field">
        <span>{label}</span>
        <div className="input-suffix">
          <input
            type="number"
            inputMode="decimal"
            step={opts.step ?? 'any'}
            value={shown}
            placeholder={opts.optional ? 'automático' : undefined}
            onChange={(e) => {
              setRaw((r) => ({ ...r, [key]: e.target.value }))
              const v = e.target.value === '' ? null : Number(e.target.value) / scale
              if (v === null && opts.optional) set(key, null as never)
              else if (v !== null && Number.isFinite(v)) set(key, v as never)
            }}
          />
          {opts.suffix && <em>{opts.suffix}</em>}
        </div>
        {fieldErrors[key] && <small className="field-error">{fieldErrors[key].join(' ')}</small>}
      </label>
    )
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit(req)
  }

  const loadExample = (ex: Example) => {
    const next = { ...req, num: ex.num, den: ex.den }
    setReq(next)
    onSubmit(next)
  }

  return (
    <form className="system-form" onSubmit={submit}>
      <div className="tf-inputs">
        <label className="field">
          <span>Numerador N(s)</span>
          <input value={req.num} onChange={(e) => set('num', e.target.value)} placeholder="ex.: 1   ou   2(s+3)" spellCheck={false} />
        </label>
        <div className="frac-bar" aria-hidden />
        <label className="field">
          <span>Denominador D(s)</span>
          <input value={req.den} onChange={(e) => set('den', e.target.value)} placeholder="ex.: 1 11.3 14 10   ou   (s+10)(s^2+1.3s+1)" spellCheck={false} />
        </label>
        {fieldErrors.system && <small className="field-error">{fieldErrors.system.join(' ')}</small>}
        {(fieldErrors.num || fieldErrors.den) && <small className="field-error">{[...(fieldErrors.num ?? []), ...(fieldErrors.den ?? [])].join(' ')}</small>}
        <p className="hint">
          Coeficientes no formato do MATLAB (maior potência primeiro) ou uma expressão em <code>s</code>.
        </p>
      </div>

      <div className="params">
        {numInput('k', 'Ganho K (itens e, g, i)')}
        {numInput('ess_target', 'Erro em regime (item n)', { scale: 100, suffix: '%' })}
        {numInput('ts_spec', 'Ts máximo (item o)', { suffix: 's' })}
        {numInput('mp_spec', 'Mp máximo (item o)', { suffix: '%' })}
      </div>

      <details className="advanced">
        <summary>Parâmetros avançados</summary>
        <div className="params">
          {numInput('k_step', 'K para degrau (item i)', { optional: true })}
          {numInput('k_ramp', 'K para rampa (item i)', { optional: true })}
          {numInput('k_impulse', 'K para impulso (item i)', { optional: true })}
          {numInput('sine_freq', 'Frequência da senoide (item r)', { suffix: 'rad/s' })}
          {numInput('sine_amp', 'Amplitude da senoide (item r)')}
          {numInput('tfinal', 'Tempo de simulação', { optional: true, suffix: 's' })}
          <label className="field check">
            <input type="checkbox" checked={req.zn_include_gain} onChange={(e) => set('zn_include_gain', e.target.checked)} />
            <span>Ziegler-Nichols (1º método): normalizar pelo ganho do processo</span>
          </label>
        </div>
      </details>

      <div className="actions">
        <button type="submit" className="primary" disabled={loading}>
          {loading ? 'Calculando…' : 'Analisar sistema'}
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
