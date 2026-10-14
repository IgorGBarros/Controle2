import { useState } from 'react'
import { ApiError, describeSystem, type DescribeResult } from '../lib/api'
import type { LoopSpec } from '../lib/types'
import { RichText } from './RichText'

const EXAMPLES = [
  'Motor CC com J = 0,01 kg·m², b = 0,1 N·m·s, Kt = Ke = 0,01, R = 1 Ω e L = 0,5 H; saída é a velocidade, com sensor de ganho 1.',
  'Massa-mola-amortecedor com m = 2 kg, b = 4 N·s/m e k = 20 N/m, controlado por um PID com Kp = 50, Ki = 30 e Kd = 5.',
  'Forno com constante de tempo de 120 s, ganho 3 °C/% e atraso de 20 s, com realimentação unitária.',
]

interface Props {
  enabled: boolean
  onApply: (spec: LoopSpec) => void
}

/** Entrada em linguagem natural: descreve o sistema e o Claude propõe G(s), C(s) e H(s). */
export function DescribePanel({ enabled, onApply }: Props) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<DescribeResult | null>(null)

  const run = async () => {
    if (!text.trim() || busy) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await describeSystem(text)
      setResult(r)
      if (!r.validation_error) onApply(r.spec)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Não foi possível consultar a IA.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <details className="describe" open={enabled ? undefined : false}>
      <summary>
        <span className="ai-badge">IA</span> Descrever o sistema em linguagem natural
      </summary>
      {!enabled ? (
        <p className="muted small">
          Desabilitado neste servidor: defina <code>ANTHROPIC_API_KEY</code> no backend para usar.
        </p>
      ) : (
        <div className="describe-body">
          <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Descreva o sistema físico, o controlador e o sensor…" disabled={busy} />
          <div className="describe-actions">
            <button type="button" className="primary" onClick={() => void run()} disabled={busy || text.trim().length < 3}>
              {busy ? 'Modelando…' : 'Gerar malha'}
            </button>
            <span className="muted small">Exemplos:</span>
            {EXAMPLES.map((ex, i) => (
              <button key={i} type="button" className="chip" title={ex} onClick={() => setText(ex)} disabled={busy}>
                {['Motor CC', 'Massa-mola + PID', 'Forno com atraso'][i]}
              </button>
            ))}
          </div>
          {error && <p className="field-error">{error}</p>}
          {result && (
            <div className="describe-result">
              {result.validation_error ? (
                <p className="field-error">A malha proposta pela IA foi rejeitada pelo motor de cálculo: {result.validation_error}</p>
              ) : (
                <p className="ok-text">✓ Malha preenchida no formulário abaixo. Confira os blocos e clique em “Analisar malha”.</p>
              )}
              <p>
                <strong>{result.summary}</strong>
              </p>
              {result.derivation.length > 0 && (
                <>
                  <span className="sub">Modelagem</span>
                  <ol>
                    {result.derivation.map((d, i) => (
                      <li key={i}>
                        <RichText text={d} />
                      </li>
                    ))}
                  </ol>
                </>
              )}
              {result.assumptions.length > 0 && (
                <>
                  <span className="sub">Hipóteses e valores assumidos</span>
                  <ul>
                    {result.assumptions.map((a, i) => (
                      <li key={i}>
                        <RichText text={a} />
                      </li>
                    ))}
                  </ul>
                </>
              )}
              {result.questions.length > 0 && (
                <>
                  <span className="sub">Informações que faltaram</span>
                  <ul>
                    {result.questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </>
              )}
              <p className="muted small">Gerado por IA ({result.model}) — revise a modelagem antes de usar os resultados.</p>
            </div>
          )}
        </div>
      )}
    </details>
  )
}
