import { useEffect, useMemo, useRef, useState } from 'react'
import type { SimResult } from '../lib/api'
import { fmt } from '../lib/format'

type View = 'tanque' | 'carrinho' | 'motor'

interface Props {
  data: SimResult
  uMin: number | null
  uMax: number | null
  /** Instante mostrado (para o cursor dos gráficos); null quando a animação não foi usada. */
  onTime: (t: number | null) => void
}

interface Sample {
  t: number
  r: number
  y: number
  u: number
  uRaw: number
  d: number
}

function finite(xs: (number | null)[]): number[] {
  return xs.filter((x): x is number => x !== null && Number.isFinite(x))
}

function sampleAt(data: SimResult, t: number): Sample {
  const ts = data.t
  let lo = 0
  let hi = ts.length - 1
  if (t <= ts[0]) hi = 0
  else if (t >= ts[hi]) lo = hi
  else {
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (ts[mid] <= t) lo = mid
      else hi = mid
    }
  }
  const f = hi === lo ? 0 : (t - ts[lo]) / (ts[hi] - ts[lo])
  const at = (arr: (number | null)[]) => {
    const a = arr[lo] ?? NaN
    const b = arr[hi] ?? NaN
    return a + f * (b - a)
  }
  const s = data.series
  return { t, r: at(s.r), y: at(s.y), u: at(s.u), uRaw: at(s.u_raw), d: at(s.d) }
}

const clamp01 = (x: number) => (Number.isFinite(x) ? Math.min(1, Math.max(0, x)) : 0)

/** Animação da simulação: reproduz y(t), u(t) e r(t) em uma vista física e em medidores. */
export function SimAnimation({ data, uMin, uMax, onTime }: Props) {
  const tEnd = data.t[data.t.length - 1] ?? 0
  const [view, setView] = useState<View>('tanque')
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [time, setTime] = useState(tEnd)
  const [touched, setTouched] = useState(false)
  const timeRef = useRef(tEnd)
  const lastEmit = useRef(0)

  // Nova simulação: mostra o estado final e para a reprodução.
  const [dataKey, setDataKey] = useState(data)
  if (dataKey !== data) {
    setDataKey(data)
    setPlaying(false)
    setTime(tEnd)
    setTouched(false)
  }

  useEffect(() => {
    timeRef.current = time
  }, [time])

  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    // a duração real da animação é ajustada para ~8 s em velocidade 1×, qualquer que seja o horizonte simulado
    const rate = (tEnd / 8) * speed
    const frame = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      const next = Math.min(tEnd, timeRef.current + dt * rate)
      timeRef.current = next
      setTime(next)
      if (now - lastEmit.current > 80 || next >= tEnd) {
        lastEmit.current = now
        onTime(next)
      }
      if (next >= tEnd) {
        setPlaying(false)
        return
      }
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [playing, speed, tEnd, onTime])

  const scales = useMemo(() => {
    const ys = [...finite(data.series.y), ...finite(data.series.r)]
    let lo = Math.min(0, ...ys)
    let hi = Math.max(...ys, 1e-9)
    const pad = (hi - lo) * 0.1 || 1
    lo -= lo < 0 ? pad : 0
    hi += pad
    // escala robusta: ignora picos curtos (ex.: derivada sobre o erro no instante do degrau)
    const us = finite(data.series.u).sort((a, b) => a - b)
    const q = (f: number) => (us.length ? us[Math.min(us.length - 1, Math.max(0, Math.round(f * (us.length - 1))))] : 0)
    let uLo = uMin ?? Math.min(0, q(0.02))
    let uHi = uMax ?? Math.max(q(0.98), 1e-9)
    if (uLo === uHi) {
      uLo -= 1
      uHi += 1
    }
    const ds = finite(data.series.d)
    const dMax = Math.max(1e-9, ...ds.map(Math.abs))
    return { lo, hi, uLo, uHi, dMax }
  }, [data, uMin, uMax])

  const s = sampleAt(data, time)
  const yf = clamp01((s.y - scales.lo) / (scales.hi - scales.lo))
  const rf = clamp01((s.r - scales.lo) / (scales.hi - scales.lo))
  const uAbsMax = Math.max(Math.abs(scales.uLo), Math.abs(scales.uHi))
  const un = Number.isFinite(s.u) ? Math.max(-1, Math.min(1, s.u / uAbsMax)) : 0
  const saturated = (uMax !== null && s.uRaw > uMax + 1e-9) || (uMin !== null && s.uRaw < uMin - 1e-9)
  const diverged = !Number.isFinite(s.y)

  const togglePlay = () => {
    if (!playing && (timeRef.current >= tEnd - 1e-9 || !touched)) {
      timeRef.current = 0
      setTime(0)
      onTime(0)
    }
    setTouched(true)
    setPlaying((p) => !p)
  }

  return (
    <div className="sim-anim">
      <div className="anim-stage">
        <div className="anim-controls">
          <button type="button" className="play" onClick={togglePlay} aria-label={playing ? 'Pausar' : 'Reproduzir'}>
            {playing ? '❚❚' : '▶'}
          </button>
          <input
            type="range"
            min={0}
            max={tEnd}
            step={tEnd / 1000 || 0.01}
            value={time}
            aria-label="Tempo da animação"
            onChange={(e) => {
              const v = Number(e.target.value)
              setPlaying(false)
              setTouched(true)
              timeRef.current = v
              setTime(v)
              onTime(v)
            }}
          />
          <span className="anim-time">
            t = {fmt(time, 3)} / {fmt(tEnd, 3)} s
          </span>
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label="Velocidade">
            {[0.25, 0.5, 1, 2, 4].map((v) => (
              <option key={v} value={v}>
                {String(v).replace('.', ',')}×
              </option>
            ))}
          </select>
          <select value={view} onChange={(e) => setView(e.target.value as View)} aria-label="Visualização">
            <option value="tanque">Tanque (nível)</option>
            <option value="carrinho">Carrinho (posição)</option>
            <option value="motor">Motor (ângulo)</option>
          </select>
        </div>
        {view === 'tanque' && <Tank yf={yf} rf={rf} un={un} d={s.d / scales.dMax} t={time} />}
        {view === 'carrinho' && <Cart yf={yf} rf={rf} un={un} d={s.d / scales.dMax} />}
        {view === 'motor' && <Motor yf={yf} rf={rf} un={un} d={s.d / scales.dMax} />}
        <p className="muted small">
          Analogia visual: a saída y(t) é mostrada como {view === 'tanque' ? 'nível do tanque' : view === 'carrinho' ? 'posição do carrinho' : 'ângulo do eixo'}, o
          sinal de controle u(t) como {view === 'tanque' ? 'abertura da válvula' : view === 'carrinho' ? 'força aplicada' : 'torque'} e a referência como a marca
          tracejada.
        </p>
      </div>
      <div className="readouts" aria-live="off">
        <Readout label="Referência r" value={s.r} lo={scales.lo} hi={scales.hi} color="var(--text-muted)" />
        <Readout label="Saída y" value={s.y} lo={scales.lo} hi={scales.hi} color="var(--series-1)" />
        <Readout label="Erro e" value={s.r - s.y} lo={-(scales.hi - scales.lo)} hi={scales.hi - scales.lo} color="var(--series-2)" />
        <Readout label="Controle u" value={s.u} lo={scales.uLo} hi={scales.uHi} color="var(--series-3)" />
        {data.series.d.some((x) => x) && <Readout label="Perturbação" value={s.d} lo={-scales.dMax} hi={scales.dMax} color="var(--series-5)" />}
        {saturated && <span className="sat-flag">ATUADOR SATURADO</span>}
        {diverged && <span className="sat-flag">SAÍDA DIVERGIU</span>}
      </div>
    </div>
  )
}

function Readout({ label, value, lo, hi, color }: { label: string; value: number; lo: number; hi: number; color: string }) {
  const span = hi - lo || 1
  const zero = clamp01((0 - lo) / span)
  const v = clamp01((value - lo) / span)
  const left = Math.min(zero, v)
  const width = Math.abs(v - zero)
  return (
    <div className="readout">
      <span>{label}</span>
      <div className="meter">
        <i style={{ left: `${left * 100}%`, width: `${Math.max(width * 100, 0.8)}%`, background: color }} />
        {lo < 0 && <span className="zero" style={{ left: `${zero * 100}%` }} />}
      </div>
      <strong>{Number.isFinite(value) ? fmt(Math.abs(value) < 1e-3 * Math.max(1, Math.abs(hi - lo)) ? 0 : value, 3) : '—'}</strong>
    </div>
  )
}

/* ------------------------------------------------------------------ vistas */

interface ViewProps {
  yf: number // saída normalizada 0..1
  rf: number // referência normalizada 0..1
  un: number // controle normalizado −1..1
  d: number // perturbação normalizada −1..1
}

function Tank({ yf, rf, un, d, t }: ViewProps & { t: number }) {
  const top = 50
  const bottom = 270
  const h = bottom - top
  const level = bottom - yf * h
  const ref = bottom - rf * h
  const inflow = Math.max(0, un)
  const outflow = Math.max(0, -un)
  const wave = (x: number) => level + Math.sin(x / 14 + t * 3) * 2.2 * (0.3 + inflow)
  const surface = Array.from({ length: 19 }, (_, i) => 200 + i * 10).map((x) => `${x},${wave(x).toFixed(1)}`)
  return (
    <svg viewBox="0 -14 520 324" role="img" aria-label={`Tanque com nível ${Math.round(yf * 100)}%`}>
      {/* tubulação de entrada e válvula */}
      <path d="M30 32 H262 V58" fill="none" stroke="var(--border-strong)" strokeWidth="12" strokeLinejoin="round" />
      <path d="M30 32 H262 V58" fill="none" stroke="var(--surface-2)" strokeWidth="7" strokeLinejoin="round" />
      <g transform="translate(120 32)">
        <path d="M-14 -11 L14 11 L14 -11 L-14 11 Z" fill="var(--surface-1)" stroke="var(--series-3)" strokeWidth="2" />
        <line x1="0" y1="0" x2="0" y2="-20" stroke="var(--series-3)" strokeWidth="2" />
        <rect x={-11} y={-27} width="22" height="7" rx="2" fill="var(--series-3)" transform={`rotate(${inflow * 80} 0 -23)`} />
      </g>
      <text x="120" y="70" textAnchor="middle" className="anim-svg-text">válvula · u</text>
      {/* jato de entrada */}
      {inflow > 0.01 && <rect x={262 - 1 - inflow * 7} y={58} width={2 + inflow * 14} height={Math.max(0, level - 58)} fill="var(--series-1)" opacity="0.55" />}
      {/* tanque */}
      <rect x="190" y={top} width="200" height={h} rx="6" fill="var(--surface-2)" stroke="var(--border-strong)" strokeWidth="2" />
      <path d={`M200 ${bottom - 2} L${surface.join(' L')} L380 ${bottom - 2} Z`} fill="var(--series-1)" opacity="0.35" />
      <polyline points={surface.join(' ')} fill="none" stroke="var(--series-1)" strokeWidth="2" />
      {/* referência */}
      <line x1="182" x2="398" y1={ref} y2={ref} stroke="var(--text-primary)" strokeDasharray="6 5" strokeWidth="1.5" />
      <text x="404" y={ref + 4} className="anim-svg-text">referência</text>
      <text x="290" y={Math.min(bottom - 8, level + 18)} textAnchor="middle" className="anim-svg-text">nível · y</text>
      {/* saída / dreno (u negativo) */}
      <path d="M390 250 H470" stroke="var(--border-strong)" strokeWidth="10" />
      {outflow > 0.01 && <rect x="470" y={250} width={2 + outflow * 12} height="40" fill="var(--series-1)" opacity="0.5" />}
      {/* perturbação */}
      {Math.abs(d) > 0.01 && (
        <g>
          <line x1="80" x2="180" y1="200" y2="200" stroke="var(--series-5)" strokeWidth={2 + Math.abs(d) * 4} markerEnd="url(#arrow-d)" />
          <text x="80" y="190" className="anim-svg-text">perturbação</text>
          <defs>
            <marker id="arrow-d" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
              <path d="M0 0 L10 5 L0 10 z" fill="var(--series-5)" />
            </marker>
          </defs>
        </g>
      )}
    </svg>
  )
}

function Cart({ yf, rf, un, d }: ViewProps) {
  const x0 = 70
  const x1 = 450
  const cx = x0 + yf * (x1 - x0)
  const rx = x0 + rf * (x1 - x0)
  const cartW = 76
  const left = cx - cartW / 2
  const coils = 10
  const springEnd = left
  const spring = Array.from({ length: coils * 2 + 1 }, (_, i) => {
    const x = 30 + ((springEnd - 30) * i) / (coils * 2)
    const y = 190 + (i === 0 || i === coils * 2 ? 0 : i % 2 ? -10 : 10)
    return `${x.toFixed(1)},${y}`
  }).join(' ')
  const raw = un * 110
  const force = raw > 0 ? Math.min(raw, 505 - cx) : Math.max(raw, 15 - cx)
  return (
    <svg viewBox="0 0 520 300" role="img" aria-label={`Carrinho na posição ${Math.round(yf * 100)}%`}>
      <defs>
        <marker id="arrow-u" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--series-3)" />
        </marker>
        <marker id="arrow-d2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--series-5)" />
        </marker>
      </defs>
      {/* parede e trilho */}
      <rect x="18" y="140" width="12" height="110" fill="var(--border-strong)" />
      <line x1="30" x2="500" y1="236" y2="236" stroke="var(--border-strong)" strokeWidth="3" />
      {Array.from({ length: 10 }, (_, i) => (
        <line key={i} x1={x0 + (i * (x1 - x0)) / 9} x2={x0 + (i * (x1 - x0)) / 9} y1="240" y2="248" stroke="var(--axis)" />
      ))}
      {/* referência */}
      <line x1={rx} x2={rx} y1="70" y2="236" stroke="var(--text-primary)" strokeDasharray="6 5" strokeWidth="1.5" />
      <path d={`M${rx} 70 l18 7 l-18 7 z`} fill="var(--text-primary)" />
      <text x={rx > 400 ? rx - 6 : rx + 22} y="81" textAnchor={rx > 400 ? 'end' : 'start'} className="anim-svg-text">referência</text>
      {/* mola */}
      <polyline points={spring} fill="none" stroke="var(--axis)" strokeWidth="2" />
      {/* carrinho */}
      <rect x={left} y="160" width={cartW} height="58" rx="8" fill="var(--series-1)" opacity="0.9" />
      <circle cx={left + 18} cy="226" r="10" fill="var(--text-primary)" />
      <circle cx={left + cartW - 18} cy="226" r="10" fill="var(--text-primary)" />
      <text x={cx} y="193" textAnchor="middle" fill="#fff" fontSize="13" fontWeight="600">y</text>
      {/* força de controle */}
      {Math.abs(force) > 2 && (
        <line x1={cx} x2={cx + force} y1="140" y2="140" stroke="var(--series-3)" strokeWidth="4" markerEnd="url(#arrow-u)" />
      )}
      <text x={Math.min(470, Math.max(50, cx + force / 2))} y="126" textAnchor="middle" className="anim-svg-text">força · u</text>
      {/* perturbação */}
      {Math.abs(d) > 0.01 && (
        <>
          <line x1={cx - Math.sign(d) * 90} x2={cx - Math.sign(d) * 42} y1="275" y2="275" stroke="var(--series-5)" strokeWidth={2 + Math.abs(d) * 3} markerEnd="url(#arrow-d2)" />
          <text x={cx} y="295" textAnchor="middle" className="anim-svg-text">perturbação</text>
        </>
      )}
    </svg>
  )
}

function Motor({ yf, rf, un, d }: ViewProps) {
  const cx = 260
  const cy = 160
  const R = 105
  const ang = (f: number) => -135 + f * 270
  const toXY = (deg: number, r: number) => {
    const a = ((deg - 90) * Math.PI) / 180
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)]
  }
  const [px, py] = toXY(ang(yf), R - 16)
  const [tx, ty] = toXY(ang(rf), R + 6)
  const [tx2, ty2] = toXY(ang(rf) - 5, R + 20)
  const [tx3, ty3] = toXY(ang(rf) + 5, R + 20)
  const torqueSpan = un * 120
  const arcStart = ang(yf)
  const arcEnd = arcStart + torqueSpan
  const [ax0, ay0] = toXY(arcStart, R + 30)
  const [ax1, ay1] = toXY(arcEnd, R + 30)
  const large = Math.abs(torqueSpan) > 180 ? 1 : 0
  const sweep = torqueSpan > 0 ? 1 : 0
  return (
    <svg viewBox="0 0 520 320" role="img" aria-label={`Motor com ângulo ${Math.round(yf * 100)}% da escala`}>
      <defs>
        <marker id="arrow-t" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--series-3)" />
        </marker>
      </defs>
      {/* escala */}
      {Array.from({ length: 28 }, (_, i) => {
        const deg = -135 + (i * 270) / 27
        const [x0, y0] = toXY(deg, R)
        const [x1, y1] = toXY(deg, R - (i % 3 === 0 ? 12 : 6))
        return <line key={i} x1={x0} y1={y0} x2={x1} y2={y1} stroke="var(--axis)" strokeWidth={i % 3 === 0 ? 2 : 1} />
      })}
      <circle cx={cx} cy={cy} r={R - 22} fill="var(--surface-2)" stroke="var(--border-strong)" strokeWidth="2" />
      {/* referência */}
      <path d={`M${tx} ${ty} L${tx2} ${ty2} L${tx3} ${ty3} Z`} fill="var(--text-primary)" />
      <text x={tx2} y={ty2 - 6} textAnchor="middle" className="anim-svg-text">ref.</text>
      {/* eixo e ponteiro */}
      <line x1={cx} y1={cy} x2={px} y2={py} stroke="var(--series-1)" strokeWidth="6" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="14" fill="var(--series-1)" />
      <circle cx={cx} cy={cy} r="5" fill="var(--surface-1)" />
      {/* torque */}
      {Math.abs(torqueSpan) > 3 && (
        <path d={`M${ax0} ${ay0} A${R + 30} ${R + 30} 0 ${large} ${sweep} ${ax1} ${ay1}`} fill="none" stroke="var(--series-3)" strokeWidth="4" markerEnd="url(#arrow-t)" />
      )}
      <text x={cx} y={cy + 52} textAnchor="middle" className="anim-svg-text">ângulo · y</text>
      <text x="40" y="300" className="anim-svg-text">arco verde: torque · u</text>
      {Math.abs(d) > 0.01 && (
        <text x="480" y="300" textAnchor="end" className="anim-svg-text" fill="var(--series-5)">
          perturbação {d > 0 ? '+' : '−'}
        </text>
      )}
    </svg>
  )
}
