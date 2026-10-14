import type { Feedback } from '../lib/types'

interface Props {
  controller: string
  plant: string
  sensor: string
  feedback: Feedback
  delay?: number
}

/** Diagrama de blocos da malha: r → Σ → K·C(s) → G(s) → y, realimentação por H(s). */
export function LoopDiagram({ controller, plant, sensor, feedback, delay }: Props) {
  const sign = feedback === 'positive' ? '+' : '−'
  return (
    <svg className="loop-diagram" viewBox="0 0 640 170" role="img" aria-label={`Malha: ${controller}, ${plant}, realimentação ${feedback === 'positive' ? 'positiva' : 'negativa'} por ${sensor}`}>
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="var(--text-secondary)" />
        </marker>
      </defs>
      <g stroke="var(--text-secondary)" strokeWidth="2" fill="none">
        <line x1="20" y1="55" x2="92" y2="55" markerEnd="url(#arrow)" />
        <circle cx="110" cy="55" r="17" />
        <line x1="127" y1="55" x2="178" y2="55" markerEnd="url(#arrow)" />
        <line x1="322" y1="55" x2="368" y2="55" markerEnd="url(#arrow)" />
        <line x1="512" y1="55" x2="616" y2="55" markerEnd="url(#arrow)" />
        <polyline points="560,55 560,135 392,135" markerEnd="url(#arrow)" />
        <polyline points="248,135 110,135 110,74" markerEnd="url(#arrow)" />
      </g>
      <g className="ld-block">
        <rect x="180" y="30" width="140" height="50" rx="8" />
        <rect x="370" y="30" width="140" height="50" rx="8" />
        <rect x="250" y="112" width="140" height="46" rx="8" />
      </g>
      <g className="ld-text" textAnchor="middle">
        <text x="250" y="60">{controller}</text>
        <text x="440" y="60">{plant}</text>
        <text x="320" y="140">{sensor}</text>
        {delay ? <text x="440" y="22" className="ld-small">atraso {delay} s</text> : null}
        <text x="34" y="45" className="ld-small" textAnchor="start">r</text>
        <text x="604" y="45" className="ld-small">y</text>
        <text x="96" y="92" className="ld-sign">{sign}</text>
        <text x="80" y="48" className="ld-sign">+</text>
      </g>
    </svg>
  )
}
