import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Report } from './components/Report'
import { Simulator } from './components/Simulator'
import { SystemForm } from './components/SystemForm'
import { Tex } from './components/Tex'
import { Tutor } from './components/Tutor'
import { Note, StabilityBadge } from './components/ui'
import { ItemAView, ItemBView, ItemCView, ItemDView, ItemEView, ItemFView, ItemGView } from './items/ItemsAtoG'
import { ItemHView, ItemIView, ItemJView, ItemMView, ItemNView, ItemOView, ItemPView, ItemQView, ItemRView, TransientView } from './items/ItemsHtoR'
import { analyze, ApiError, fetchExamples, fetchLlmStatus, modelLabel, type LlmStatus } from './lib/api'
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

const GROUPS: { title: string; keys: string[] }[] = [
  { title: 'Modelagem', keys: ['a', 'b', 'c', 'd'] },
  { title: 'Malha fechada e respostas', keys: ['e', 'h', 'i', 'k', 'l', 'm'] },
  { title: 'Resposta em frequência', keys: ['f', 'g'] },
  { title: 'Lugar das raízes', keys: ['j'] },
  { title: 'Projeto do ganho', keys: ['n', 'o'] },
  { title: 'PID — Ziegler-Nichols', keys: ['p', 'q', 'r'] },
]
const ORDER = GROUPS.flatMap((g) => g.keys)

type Tab = 'malha' | 'analise' | 'simulacao' | 'relatorio' | 'tutor'
const TABS: { id: Tab; label: string; needsResult?: boolean }[] = [
  { id: 'malha', label: 'Malha' },
  { id: 'analise', label: 'Análise', needsResult: true },
  { id: 'simulacao', label: 'Simulação', needsResult: true },
  { id: 'relatorio', label: 'Relatório', needsResult: true },
  { id: 'tutor', label: 'Tutor IA', needsResult: true },
]

/** Navegação pelo hash da URL: #/analise/j — permite voltar no navegador e compartilhar o link. */
function readHash(): { tab: Tab; item: string } {
  const [, tab, item] = window.location.hash.split('/')
  const t = TABS.some((x) => x.id === tab) ? (tab as Tab) : 'malha'
  return { tab: t, item: ORDER.includes(item) ? item : 'a' }
}

function useRoute() {
  const [route, setRoute] = useState(readHash)
  useEffect(() => {
    const on = () => setRoute(readHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  const go = useCallback((tab: Tab, item?: string) => {
    const next = `#/${tab}${tab === 'analise' ? `/${item ?? readHash().item}` : ''}`
    if (window.location.hash !== next) window.location.hash = next
    window.scrollTo({ top: 0 })
  }, [])
  return { ...route, go }
}

function ItemCard({ item }: { item: Item }) {
  return (
    <section id={`item-${item.key}`} className="card item-card">
      <header className="card-head">
        <span className="item-letter">{item.key}</span>
        <h2>{item.title}</h2>
      </header>
      {item.error ? <Note tone="bad">Não foi possível calcular este item: {item.error}</Note> : item.data ? VIEWS[item.key](item.data) : null}
    </section>
  )
}

function SystemStrip({ sys, onEdit, loading }: { sys: AnalysisResult['system']; onEdit: () => void; loading: boolean }) {
  const delay = sys.delay ? `\\,e^{-${String(sys.delay).replace('.', '{,}')}s}` : ''
  return (
    <div className={`system-strip ${loading ? 'is-loading' : ''}`}>
      <div className="strip-tf">
        <Tex>{`\\displaystyle G(s) = ${sys.plant.latex}${delay}`}</Tex>
        {!sys.controller.unity && <Tex>{`\\displaystyle C(s) = ${sys.controller.latex}`}</Tex>}
        {!sys.sensor.unity && <Tex>{`\\displaystyle H(s) = ${sys.sensor.latex}`}</Tex>}
        {sys.feedback === 'positive' && <span className="badge badge-neutral">realimentação positiva</span>}
      </div>
      <div className="strip-status">
        <span title={sys.open_loop.poles.map((p) => fmtCx(p)).join(' ; ')}>
          Malha aberta <StabilityBadge stable={sys.open_loop.stable} />
        </span>
        <span title={sys.closed_loop.poles.map((p) => fmtCx(p)).join(' ; ')}>
          Malha fechada (K = 1) <StabilityBadge stable={sys.closed_loop.stable} />
        </span>
        <button type="button" className="chip" onClick={onEdit}>
          Editar malha
        </button>
      </div>
    </div>
  )
}

function SystemDetails({ sys }: { sys: AnalysisResult['system'] }) {
  return (
    <div className="card system-details">
      {!sys.standard && <Tex block>{`L(s) = C(s)G(s)H(s) = ${sys.open_loop.latex}`}</Tex>}
      <Tex block>{`T(s) = ${sys.closed_loop.latex}\\quad (K = 1)`}</Tex>
      <p className="muted small">
        Polos de malha aberta: {sys.open_loop.poles.map((p) => fmtCx(p)).join(' ; ')} · Polos de malha fechada (K = 1): {sys.closed_loop.poles.map((p) => fmtCx(p)).join(' ; ')}
        {sys.delay > 0 && ` · Atraso aproximado por Padé de ordem ${sys.pade_order} na análise.`}
      </p>
    </div>
  )
}

function Analysis({ result, current, go }: { result: AnalysisResult; current: string; go: (tab: Tab, item?: string) => void }) {
  const [all, setAll] = useState(false)
  const byKey = Object.fromEntries(result.items.map((it) => [it.key, it]))
  const idx = ORDER.indexOf(current)
  const prev = ORDER[idx - 1]
  const next = ORDER[idx + 1]
  return (
    <div className="analysis">
      <nav className="item-nav" aria-label="Itens da análise">
        {GROUPS.map((g) => (
          <div key={g.title} className="nav-group">
            <span className="nav-group-title">{g.title}</span>
            {g.keys.map((k) => (
              <button
                key={k}
                type="button"
                className={`nav-item ${!all && k === current ? 'active' : ''} ${byKey[k]?.error ? 'has-error' : ''}`}
                onClick={() => {
                  setAll(false)
                  go('analise', k)
                }}
              >
                <b>{k}</b>
                <span>{byKey[k]?.title}</span>
              </button>
            ))}
          </div>
        ))}
        <label className="field check nav-all">
          <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
          <span>Mostrar todos os itens</span>
        </label>
      </nav>
      <div className="analysis-main">
        {current === 'a' && !all && <SystemDetails sys={result.system} />}
        {all ? ORDER.map((k) => byKey[k] && <ItemCard key={k} item={byKey[k]} />) : byKey[current] && <ItemCard item={byKey[current]} />}
        {!all && (
          <div className="pager">
            {prev ? (
              <button type="button" className="chip" onClick={() => go('analise', prev)}>
                ← {prev}) {byKey[prev]?.title}
              </button>
            ) : (
              <span />
            )}
            {next ? (
              <button type="button" className="chip" onClick={() => go('analise', next)}>
                {next}) {byKey[next]?.title} →
              </button>
            ) : (
              <button type="button" className="chip" onClick={() => go('simulacao')}>
                Ir para a simulação →
              </button>
            )}
          </div>
        )}
      </div>
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
  const { tab, item, go } = useRoute()

  const run = useCallback(
    async (req: AnalyzeRequest, openAnalysis = false) => {
      abortRef.current?.abort()
      const ctrl = new AbortController()
      abortRef.current = ctrl
      setLoading(true)
      setError(null)
      setFieldErrors({})
      try {
        setResult(await analyze(req, ctrl.signal))
        setLastRequest(req)
        if (openAnalysis) go('analise', 'a')
      } catch (e) {
        if ((e as Error).name === 'AbortError') return
        if (e instanceof ApiError) {
          setFieldErrors(e.details)
          setError(e.message)
        } else setError('Não foi possível conectar ao servidor. Verifique se o backend Django está em execução.')
      } finally {
        if (abortRef.current === ctrl) setLoading(false)
      }
    },
    [go],
  )

  useEffect(() => {
    fetchExamples().then(setExamples).catch(() => setExamples([]))
    fetchLlmStatus().then(setLlm).catch(() => undefined)
    void Promise.resolve().then(() => run({ ...DEFAULT_PARAMS, ...DEFAULT_LOOP }))
  }, [run])

  const activeTab: Tab = result ? tab : 'malha'

  return (
    <div className="shell">
      <header className="topbar no-print">
        <div className="topbar-inner">
          <a className="brand" href="#/malha">
            <svg viewBox="0 0 32 32" aria-hidden width="26" height="26">
              <rect width="32" height="32" rx="7" fill="var(--accent)" />
              <path d="M5 25 C10 25 10 8 15 8 C19 8 19 15 22 13 C25 11 26 12 28 12" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
            </svg>
            <span>Controle II</span>
          </a>
          <nav className="tabs-main" aria-label="Seções">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`tab-main ${activeTab === t.id ? 'active' : ''}`}
                disabled={t.needsResult && !result}
                aria-current={activeTab === t.id ? 'page' : undefined}
                onClick={() => go(t.id)}
              >
                {t.label}
              </button>
            ))}
          </nav>
          {loading && <span className="spinner" aria-label="Calculando" />}
        </div>
      </header>

      <div className="page">
        {result && activeTab !== 'malha' && <SystemStrip sys={result.system} onEdit={() => go('malha')} loading={loading} />}
        {error && <Note tone="bad">{error}</Note>}

        <div hidden={activeTab !== 'malha'} className="no-print">
          <div className="page-intro">
            <h1>Monte a malha de controle</h1>
            <p>
              Informe a planta, o controlador, o sensor e o tipo de realimentação. A ferramenta calcula os 18 itens do trabalho, simula a malha no tempo e gera
              um relatório explicativo.
            </p>
          </div>
          <SystemForm examples={examples} loading={loading} onSubmit={(req) => void run(req, true)} fieldErrors={fieldErrors} llmEnabled={llm.enabled} />
        </div>

        {result && activeTab === 'analise' && <Analysis result={result} current={item} go={go} />}
        {result && lastRequest && (
          <div hidden={activeTab !== 'simulacao'}>
            <Simulator request={lastRequest} result={result} llmEnabled={llm.enabled} />
          </div>
        )}
        {result && activeTab === 'relatorio' && result.report && <Report report={result.report} k={result.params.k} />}
        {result && lastRequest && (
          <div hidden={activeTab !== 'tutor'}>
            <Tutor request={lastRequest} status={llm.tutor ?? llm} model={modelLabel(llm.tutor ?? llm)} onRetry={() => fetchLlmStatus().then(setLlm).catch(() => undefined)} />
          </div>
        )}
      </div>
      <footer className="app-footer no-print">Baseado em um trabalho de Controle II de Engenharia Mecatrônica (2013), originalmente resolvido em MATLAB/SIMULINK.</footer>
    </div>
  )
}
