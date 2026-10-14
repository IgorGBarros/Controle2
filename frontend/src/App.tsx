import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { SystemForm } from './components/SystemForm'
import { Tex } from './components/Tex'
import { Note, Section, StabilityBadge } from './components/ui'
import { ItemAView, ItemBView, ItemCView, ItemDView, ItemEView, ItemFView, ItemGView } from './items/ItemsAtoG'
import { ItemHView, ItemIView, ItemJView, ItemMView, ItemNView, ItemOView, ItemPView, ItemQView, ItemRView, TransientView } from './items/ItemsHtoR'
import { analyze, ApiError, fetchExamples } from './lib/api'
import { DEFAULT_REQUEST } from './lib/defaults'
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

export default function App() {
  const [examples, setExamples] = useState<Example[]>([])
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
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
    void Promise.resolve().then(() => run(DEFAULT_REQUEST))
  }, [run])

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>Controle II — Análise de Sistemas</h1>
          <p>
            Informe qualquer planta G(s) e obtenha todos os itens do trabalho: modelagem, polos, Bode, lugar das raízes, desempenho transitório, ganho
            proporcional e sintonia PID por Ziegler-Nichols.
          </p>
        </div>
      </header>

      <SystemForm examples={examples} loading={loading} onSubmit={run} fieldErrors={fieldErrors} />
      {error && <Note tone="bad">{error}</Note>}

      {result && (
        <div className={`layout ${loading ? 'is-loading' : ''}`}>
          <nav className="toc" aria-label="Itens do trabalho">
            <ul>
              {result.items.map((it) => (
                <li key={it.key}>
                  <a href={`#item-${it.key}`}>
                    <b>{it.key})</b> {it.title}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <main>
            <div className="system-summary">
              <Tex block>{`G(s) = ${result.system.latex}`}</Tex>
              <div>
                Polos: {result.system.poles.map((p) => fmtCx(p)).join(' ; ')}
                {result.system.zeros.length > 0 && <> · Zeros: {result.system.zeros.map((z) => fmtCx(z)).join(' ; ')}</>}{' '}
                <StabilityBadge stable={result.system.stable} />
              </div>
            </div>
            {result.items.map((it) => (
              <ItemSection key={it.key} item={it} />
            ))}
          </main>
        </div>
      )}
      <footer className="app-footer">Baseado no Trabalho de Controle II — Engenharia Mecatrônica, UNIFACS (2013).</footer>
    </div>
  )
}
