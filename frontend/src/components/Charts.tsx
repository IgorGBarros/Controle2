import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { fmt } from '../lib/format'
import type { ItemJ, Series } from '../lib/types'

const COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)', 'var(--series-5)']

export interface LineSpec {
  key: string
  label: string
  color?: string
  dashed?: boolean
}

export interface RefSpec {
  y?: number
  x?: number
  label?: string
}

interface ChartProps {
  x: number[]
  series: Series
  lines: LineSpec[]
  xLabel: string
  yLabel?: string
  height?: number
  logX?: boolean
  refs?: RefSpec[]
  yDomain?: [number | 'auto' | 'dataMin' | 'dataMax', number | 'auto' | 'dataMin' | 'dataMax']
  title?: string
}

const axisStyle = { fontSize: 12, fill: 'var(--text-secondary)' }
const tickFmt = (v: number) => fmt(v, 3)

function decadeTicks(xs: number[]): number[] {
  if (!xs.length) return []
  const lo = Math.floor(Math.log10(xs[0]))
  const hi = Math.ceil(Math.log10(xs[xs.length - 1]))
  const out: number[] = []
  for (let e = lo; e <= hi; e++) out.push(10 ** e)
  return out
}

function niceStep(range: number, target = 5): number {
  const raw = range / target
  const mag = 10 ** Math.floor(Math.log10(raw))
  const n = raw / mag
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag
}

/** Domínio e marcas "redondas" para o eixo y. */
function niceAxis(values: (number | null)[]): { domain: [number, number]; ticks: number[] } | undefined {
  const v = values.filter((x): x is number => x !== null && Number.isFinite(x))
  if (!v.length) return undefined
  let lo = Math.min(...v)
  let hi = Math.max(...v)
  if (hi - lo < 1e-12 * Math.max(1, Math.abs(hi))) {
    lo -= 1
    hi += 1
  }
  const step = niceStep(hi - lo)
  lo = Math.floor(lo / step - 1e-9) * step
  hi = Math.ceil(hi / step + 1e-9) * step
  const ticks: number[] = []
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Number(t.toPrecision(12)))
  return { domain: [lo, hi], ticks }
}

function ChartTooltip({ active, payload, label, xLabel }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: number; xLabel: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="chart-tooltip">
      <div className="tt-x">
        {xLabel} = {fmt(label ?? null)}
      </div>
      {payload.map((p) => (
        <div key={p.name} className="tt-row">
          <span className="tt-swatch" style={{ background: p.color }} />
          <span>{p.name}</span>
          <strong>{fmt(p.value)}</strong>
        </div>
      ))}
    </div>
  )
}

/** Gráfico x-y genérico (tempo ou frequência). Uma única escala no eixo y. */
export function XYChart({ x, series, lines, xLabel, yLabel, height = 280, logX = false, refs = [], yDomain, title }: ChartProps) {
  const data = useMemo(
    () =>
      x.map((xi, i) => {
        const row: Record<string, number | null> = { x: xi }
        for (const l of lines) row[l.key] = series[l.key]?.[i] ?? null
        return row
      }),
    [x, series, lines],
  )
  const axis = useMemo(() => niceAxis([...lines.flatMap((l) => series[l.key] ?? []), ...refs.flatMap((r) => (r.y === undefined ? [] : [r.y]))]), [lines, series, refs])
  return (
    <figure className="chart">
      {title && <figcaption>{title}</figcaption>}
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 20, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" strokeDasharray="0" vertical={false} />
          <XAxis
            dataKey="x"
            type="number"
            scale={logX ? 'log' : 'auto'}
            domain={['dataMin', 'dataMax']}
            ticks={logX ? decadeTicks(x) : undefined}
            tickFormatter={tickFmt}
            tick={axisStyle}
            stroke="var(--axis)"
            allowDataOverflow
            label={{ value: xLabel, position: 'insideBottom', offset: -12, style: axisStyle }}
          />
          <YAxis
            tick={axisStyle}
            stroke="var(--axis)"
            tickFormatter={tickFmt}
            domain={yDomain ?? axis?.domain ?? ['auto', 'auto']}
            ticks={yDomain ? undefined : axis?.ticks}
            allowDataOverflow
            width={64}
            label={yLabel ? { value: yLabel, angle: -90, position: 'insideLeft', style: { ...axisStyle, textAnchor: 'middle' } } : undefined}
          />
          <Tooltip content={<ChartTooltip xLabel={xLabel} />} />
          {lines.length > 1 && <Legend verticalAlign="top" height={28} iconType="plainline" wrapperStyle={{ fontSize: 13, color: 'var(--text-secondary)' }} />}
          {refs.map((r, i) =>
            r.y !== undefined ? (
              <ReferenceLine key={i} y={r.y} stroke="var(--text-muted)" strokeDasharray="4 4" label={r.label ? { value: r.label, position: 'insideTopRight', style: axisStyle } : undefined} />
            ) : (
              <ReferenceLine key={i} x={r.x} stroke="var(--text-muted)" strokeDasharray="4 4" label={r.label ? { value: r.label, position: 'insideTopLeft', style: axisStyle } : undefined} />
            ),
          )}
          {lines.map((l, i) => (
            <Line
              key={l.key}
              dataKey={l.key}
              name={l.label}
              stroke={l.color ?? COLORS[i % COLORS.length]}
              strokeWidth={2}
              strokeDasharray={l.dashed ? '6 4' : undefined}
              dot={false}
              isAnimationActive={false}
              connectNulls={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  )
}

/** Diagrama de Bode: dois gráficos empilhados (magnitude e fase), cada um com sua escala. */
export function BodeCharts({ w, series, mag, phase, magRefs, phaseRefs }: { w: number[]; series: Series; mag: LineSpec[]; phase: LineSpec[]; magRefs?: RefSpec[]; phaseRefs?: RefSpec[] }) {
  return (
    <div className="bode">
      <XYChart x={w} series={series} lines={mag} xLabel="ω (rad/s)" yLabel="Magnitude (dB)" logX refs={magRefs} height={260} />
      <XYChart x={w} series={series} lines={phase} xLabel="ω (rad/s)" yLabel="Fase (°)" logX refs={phaseRefs} height={240} />
    </div>
  )
}

const crossShape = (props: { cx?: number; cy?: number }) => {
  const { cx = 0, cy = 0 } = props
  const r = 6
  return (
    <g stroke="var(--series-2)" strokeWidth={2.5}>
      <line x1={cx - r} y1={cy - r} x2={cx + r} y2={cy + r} />
      <line x1={cx - r} y1={cy + r} x2={cx + r} y2={cy - r} />
    </g>
  )
}
const circleShape = (props: { cx?: number; cy?: number }) => (
  <circle cx={props.cx} cy={props.cy} r={6} fill="var(--surface-1)" stroke="var(--series-3)" strokeWidth={2.5} />
)
const dotShape = (props: { cx?: number; cy?: number }) => (
  <circle cx={props.cx} cy={props.cy} r={5} fill="var(--series-4)" stroke="var(--surface-1)" strokeWidth={2} />
)
const noShape = () => <g />

function RlTooltip({ active, payload }: { active?: boolean; payload?: { payload: { x: number; y: number; K?: number; tag?: string } }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="chart-tooltip">
      {p.tag && <div className="tt-x">{p.tag}</div>}
      <div>
        s = {fmt(p.x)} {p.y >= 0 ? '+' : '−'} {fmt(Math.abs(p.y))}j
      </div>
      {p.K !== undefined && <div>K = {fmt(p.K)}</div>}
    </div>
  )
}

/** Lugar das raízes no plano s. */
export function RootLocusChart({ data, height = 420 }: { data: ItemJ; height?: number }) {
  const { window: win } = data
  const xa = useMemo(() => niceAxis(win.x), [win])
  const ya = useMemo(() => niceAxis(win.y), [win])
  const segments = useMemo(() => {
    const segs: { x: number; y: number; K: number }[][] = []
    const inside = (x: number, y: number) => x >= win.x[0] && x <= win.x[1] && y >= win.y[0] && y <= win.y[1]
    for (const br of data.branches) {
      let cur: { x: number; y: number; K: number }[] = []
      for (const [x, y, K] of br) {
        if (inside(x, y)) cur.push({ x, y, K })
        else if (cur.length) {
          segs.push(cur)
          cur = []
        }
      }
      if (cur.length > 1) segs.push(cur)
    }
    return segs
  }, [data, win])
  const poles = data.poles.map(([x, y]) => ({ x, y, tag: 'Polo de malha aberta' }))
  const zeros = data.zeros.map(([x, y]) => ({ x, y, tag: 'Zero de malha aberta' }))
  const crosses = data.jw_crossings.flatMap((c) => [
    { x: 0, y: c.w, K: c.K, tag: 'Cruzamento com o eixo jω' },
    ...(c.w > 0 ? [{ x: 0, y: -c.w, K: c.K, tag: 'Cruzamento com o eixo jω' }] : []),
  ])
  const breaks = data.breakaway.map((b) => ({ x: b.s, y: 0, K: b.K, tag: 'Ponto de separação/chegada' }))
  return (
    <figure className="chart">
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 16, bottom: 20, left: 8 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis type="number" dataKey="x" domain={xa?.domain ?? win.x} ticks={xa?.ticks} tickFormatter={tickFmt} tick={axisStyle} stroke="var(--axis)" allowDataOverflow
            label={{ value: 'Eixo real σ', position: 'insideBottom', offset: -12, style: axisStyle }} />
          <YAxis type="number" dataKey="y" domain={ya?.domain ?? win.y} ticks={ya?.ticks} tickFormatter={tickFmt} tick={axisStyle} stroke="var(--axis)" allowDataOverflow width={64}
            label={{ value: 'Eixo imaginário jω', angle: -90, position: 'insideLeft', style: { ...axisStyle, textAnchor: 'middle' } }} />
          <ZAxis range={[60, 60]} />
          <ReferenceLine x={0} stroke="var(--axis)" />
          <ReferenceLine y={0} stroke="var(--axis)" />
          <Tooltip content={<RlTooltip />} cursor={{ strokeDasharray: '3 3' }} />
          {segments.map((seg, i) => (
            <Scatter key={`b${i}`} data={seg} line={{ stroke: 'var(--series-1)', strokeWidth: 2 }} shape={noShape} isAnimationActive={false} legendType="none" />
          ))}
          <Scatter name="Polos" data={poles} shape={crossShape} isAnimationActive={false} />
          {zeros.length > 0 && <Scatter name="Zeros" data={zeros} shape={circleShape} isAnimationActive={false} />}
          {(crosses.length > 0 || breaks.length > 0) && <Scatter name="Pontos notáveis" data={[...crosses, ...breaks]} shape={dotShape} isAnimationActive={false} />}
        </ScatterChart>
      </ResponsiveContainer>
      <figcaption className="legend-inline">
        <span><i className="sw sw-line" /> Ramos do lugar das raízes</span>
        <span><i className="sw sw-x">×</i> Polos</span>
        {zeros.length > 0 && <span><i className="sw sw-o">○</i> Zeros</span>}
        {(crosses.length > 0 || breaks.length > 0) && <span><i className="sw sw-dot" /> Cruzamentos jω / separação</span>}
      </figcaption>
    </figure>
  )
}
