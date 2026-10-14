import { useMemo } from 'react'
import { CartesianGrid, ReferenceDot, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from 'recharts'
import { niceAxis } from '../lib/axis'
import { fmt } from '../lib/format'
import type { Report as ReportData, ReportSection } from '../lib/types'
import { RichText } from './RichText'

const axisStyle = { fontSize: 12, fill: 'var(--text-secondary)' }

function NyquistTooltip({ active, payload }: { active?: boolean; payload?: { payload: { x: number; y: number; w: number } }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="chart-tooltip">
      <div className="tt-x">ω = {fmt(p.w)} rad/s</div>
      <div>
        L(jω) = {fmt(p.x)} {p.y >= 0 ? '+' : '−'} {fmt(Math.abs(p.y))}j
      </div>
    </div>
  )
}

/** Diagrama polar (Nyquist): ω > 0 em linha cheia e o espelho (ω < 0) tracejado. */
function NyquistChart({ chart, k }: { chart: NonNullable<ReportSection['chart']>; k: number }) {
  const pos = useMemo(() => chart.re.map((x, i) => ({ x, y: chart.im[i], w: chart.w[i] })), [chart])
  const neg = useMemo(() => pos.map((p) => ({ ...p, y: -p.y, w: -p.w })).reverse(), [pos])
  const posK = useMemo(() => pos.map((p) => ({ x: p.x * k, y: p.y * k, w: p.w })), [pos, k])
  const negK = useMemo(() => neg.map((p) => ({ x: p.x * k, y: p.y * k, w: p.w })), [neg, k])
  const axis = useMemo(() => {
    const all = [...pos, ...(k !== 1 ? posK : [])].flatMap((p) => [Math.abs(p.x), Math.abs(p.y)])
    const lim = Math.min(Math.max(1.2, ...all) * 1.05, 50)
    return niceAxis([-lim, lim])
  }, [pos, posK, k])
  const dom: [number, number] = axis?.domain ?? [-1.5, 1.5]
  return (
    <figure className="chart nyquist">
      <figcaption>Diagrama polar (Nyquist) de L(jω)</figcaption>
      <ResponsiveContainer width="100%" aspect={1.25}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 20, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis type="number" dataKey="x" domain={dom} ticks={axis?.ticks} tickFormatter={(v) => fmt(v, 2)} tick={axisStyle} stroke="var(--axis)" allowDataOverflow
            label={{ value: 'Re L(jω)', position: 'insideBottom', offset: -12, style: axisStyle }} />
          <YAxis type="number" dataKey="y" domain={dom} ticks={axis?.ticks} tickFormatter={(v) => fmt(v, 2)} tick={axisStyle} stroke="var(--axis)" allowDataOverflow width={56}
            label={{ value: 'Im L(jω)', angle: -90, position: 'insideLeft', style: { ...axisStyle, textAnchor: 'middle' } }} />
          <ReferenceLine x={0} stroke="var(--axis)" />
          <ReferenceLine y={0} stroke="var(--axis)" />
          <Tooltip content={<NyquistTooltip />} />
          <Scatter data={neg} line={{ stroke: 'var(--series-1)', strokeWidth: 1.5, strokeDasharray: '5 4' }} shape={() => <g />} isAnimationActive={false} />
          <Scatter data={pos} line={{ stroke: 'var(--series-1)', strokeWidth: 2 }} shape={() => <g />} isAnimationActive={false} />
          {k !== 1 && <Scatter data={negK} line={{ stroke: 'var(--series-3)', strokeWidth: 1.5, strokeDasharray: '5 4' }} shape={() => <g />} isAnimationActive={false} />}
          {k !== 1 && <Scatter data={posK} line={{ stroke: 'var(--series-3)', strokeWidth: 2 }} shape={() => <g />} isAnimationActive={false} />}
          <ReferenceDot x={-1} y={0} r={6} fill="var(--series-2)" stroke="var(--surface-1)" strokeWidth={2}
            label={{ value: '−1', position: 'top', style: { ...axisStyle, fill: 'var(--text-primary)' } }} />
        </ScatterChart>
      </ResponsiveContainer>
      <p className="legend-inline">
        <span><i className="sw sw-line" /> L(jω), ω &gt; 0</span>
        {k !== 1 && <span><i className="sw sw-line3" /> K·L(jω), K = {fmt(k)}</span>}
        <span><i className="sw sw-dash" /> tracejado: ω &lt; 0 (espelho)</span>
        <span><i className="sw sw-dot2" /> ponto crítico −1</span>
      </p>
    </figure>
  )
}

export function Report({ report, k }: { report: ReportData; k: number }) {
  return (
    <section id="relatorio" className="section report">
      <div className="report-head">
        <h2>Relatório final explicativo</h2>
        <button type="button" className="chip no-print" onClick={() => window.print()}>
          Imprimir / salvar PDF
        </button>
      </div>
      <p className="muted">
        Interpretação dos resultados desta malha com base em Ogata (Engenharia de Controle Moderno) e Meza (Sistemas de Controle com Python: Resposta em
        Frequência). Os números vêm dos cálculos acima; o texto é gerado a partir deles.
      </p>
      {report.sections.map((s) => (
        <article key={s.key} className="report-section">
          <h3>{s.title}</h3>
          {s.paragraphs.map((p, i) => (p.startsWith('$$') ? <RichText key={i} text={p} /> : <p key={i}><RichText text={p} /></p>))}
          {s.bullets.length > 0 && (
            <ul>
              {s.bullets.map((b, i) => (
                <li key={i}>
                  <RichText text={b} />
                </li>
              ))}
            </ul>
          )}
          {s.chart?.kind === 'nyquist' && <NyquistChart chart={s.chart} k={k} />}
        </article>
      ))}
      <article className="report-section">
        <h3>Referências</h3>
        <ol className="refs">
          {report.references.map((r) => (
            <li key={r.key}>{r.text}</li>
          ))}
        </ol>
      </article>
    </section>
  )
}
