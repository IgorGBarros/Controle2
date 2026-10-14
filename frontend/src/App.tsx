import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Report } from './components/Report'
import { SystemForm } from './components/SystemForm'
import { Tutor } from './components/Tutor'
import { Tex } from './components/Tex'
import { Note, Section, StabilityBadge } from './components/ui'
import { ItemAView, ItemBView, ItemCView, ItemDView, ItemEView, ItemFView, ItemGView } from './items/ItemsAtoG'
import { ItemHView, ItemIView, ItemJView, ItemMView, ItemNView, ItemOView, ItemPView, ItemQView, ItemRView, TransientView } from './items/ItemsHtoR'
import { analyze, ApiError, fetchExamples, fetchLlmStatus, type LlmStatus } from './lib/api'
import { DEFAULT_LOOP, DEFAULT_PARAMS } from './lib/defaults'
import { fmtCx } from './lib/format'
import type { AnalysisResult, AnalyzeRequest, Example, Item } from './lib/types'

/* eslint-disable @typescript-eslint/no-explicit-any */
const VIEWS: Record<string, (d: any) => ReactNode> = {
  a: (d) => <ItemAView d={d} />,
  b: (d) => <ItemBView d={d} />,
  c: (d) => <ItemCView d={d} />,
  d: (d) => <ItemDView d={d} />,
  e: (d) => <ItemEView d={d} />,
  f: (d) => <ItemFView d={d} />,
  g: (d) => <ItemGView d={d} />,
  h: (d) => <ItemHView d={d} />,
  i: (d) => <ItemIView d={d} />,
  j: (d) => <ItemJView d={d} />,
  k: (d) => <TransientView d={d} />,
  l: (d) => <TransientView d={d} />,
  m: (d) => <ItemMView d={d} />,
  n: (d) => <ItemNView d={d} />,
  o: (d) => <ItemOView d={d} />,
  p: (d) => <ItemPView d={d} />,
  q: (d) => <ItemQView d={d} />,
  r: (d) => <ItemRView d={d} />,
}

function ItemSection({ item }: { item: Item }) {
  return (
    <Section id={`item-${item.key}`} letter={item.key} title={item.title}>
      {item.error ? <Note tone="bad">Não foi possível calcular este item: {item.error}</Note> : item.data ? VIEWS[item.key](item.data) : null}
    </Section>
  )
}

function SystemSummary({ sys }: { sys: AnalysisResult['system'] }) {
  const delay = sys.delay ? `\\,e^{-${String(sys.delay).replace('.', '{,}')}s}` : ''
  return (
    <div className="system-summary">
      <div className="summary-blocks">
        <Tex>{`G(s) = ${sys.plant.latex}${delay}`}</Tex>
        {!sys.standard && (
          <>
            <Tex>{`C(s) = ${sys.controller.latex}`}</Tex>
            <Tex>{`H(s) = ${sys.sensor.latex}`}</Tex>
            <span className="badge badge-neutral">realimentação {sys.feedback === 'positive' ? 'positiva (+)' : 'negativa (−)'}</span>
          </>
        )}
      </div>
      {!sys.standard && <Tex block>{`L(s) = C(s)G(s)H(s) = ${sys.open_loop.latex}`}</Tex>}
      <Tex block>{`T(s) = ${sys.closed_loop.latex}\\quad (K = 1)`}</Tex>
      <div>
        Polos de malha aberta: {sys.open_loop.poles.map((p) => fmtCx(p)).join(' ; ')} <StabilityBadge stable={sys.open_loop.stable} /> · Polos de malha fechada (K = 1):{' '}
        {sys.closed_loop.poles.map((p) => fmtCx(p)).join(' ; ')} <StabilityBadge stable={sys.closed_loop.stable} />
      </div>
      {sys.delay > 0 && <p className="muted small">O atraso e^(−θs) é aproximado por Padé de ordem {sys.pade_order} em todos os cálculos.</p>}
    </div>
  )
}

export default function App() {
  const [examples, setExamples] = useState<Example[]>([])
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [lastRequest, setLastRequest] = useState<AnalyzeRequest | null>(null)
  const [llm, setLlm] = useState<LlmStatus>({ enabled: false, model: '' })
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback(async (req: AnalyzeRequest) => {
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true)
    setError(null)
    setFieldErrors({})
    try {
      setResult(await analyze(req, ctrl.signal))
      setLastRequest(req)
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      if (e instanceof ApiError) {
        setFieldErrors(e.details)
        setError(e.message)
      } else setError('Não foi possível conectar ao servidor. Verifique se o backend Django está em execução.')
    } finally {
      if (abortRef.current === ctrl) setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchExamples().then(setExamples).catch(() => setExamples([]))
    fetchLlmStatus().then(setLlm).catch(() => undefined)
    void Promise.resolve().then(() => run({ ...DEFAULT_PARAMS, ...DEFAULT_LOOP }))
  }, [run])

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Controle II — Análise de Sistemas</h1>
          <p>
            Monte qualquer malha — planta G(s), controlador C(s), sensor H(s), realimentação negativa ou positiva — e obtenha todos os itens do trabalho: modelagem, polos, Bode, lugar das raízes, desempenho transitório, ganho
            proporcional e sintonia PID por Ziegler-Nichols.
          </p>
        </div>
      </header>

      <div className="no-print"><SystemForm examples={examples} loading={loading} onSubmit={run} fieldErrors={fieldErrors} llmEnabled={llm.enabled} /></div>
      {error && <Note tone="bad">{error}</Note>}

      {result && (
        <div className={`layout ${loading ? 'is-loading' : ''}`}>
          <nav className="toc no-print" aria-label="Itens do trabalho">
            <ul>
              {result.items.map((it) => (
                <li key={it.key}>
                  <a href={`#item-${it.key}`}>
                    <b>{it.key})</b> {it.title}
                  </a>
                </li>
              ))}
              <li>
                <a href="#relatorio">
                  <b>★</b> Relatório final explicativo
                </a>
              </li>
              <li>
                <a href="#tutor">
                  <b>IA</b> Tutor
                </a>
              </li>
            </ul>
          </nav>
          <main>
            <SystemSummary sys={result.system} />
            {result.items.map((it) => (
              <ItemSection key={it.key} item={it} />
            ))}
            {result.report && <Report report={result.report} k={result.params.k} />}
            {lastRequest && <Tutor request={lastRequest} enabled={llm.enabled} model={llm.model} />}
          </main>
        </div>
      )}
      <footer className="app-footer">Baseado no Trabalho de Controle II — Engenharia Mecatrônica, UNIFACS (2013).</footer>
    </div>
  )
}
