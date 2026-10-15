import type { ReactNode } from 'react'
import { fmt } from '../lib/format'
import type { Num, StepInfo } from '../lib/types'

export function Section({ id, letter, title, children }: { id: string; letter: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="section">
      <h2>
        <span className="letter">{letter})</span> {title}
      </h2>
      {children}
    </section>
  )
}

export function Matlab({ lines }: { lines: string[] }) {
  return (
    <details className="matlab">
      <summary>Equivalente em MATLAB</summary>
      <pre>
        <code>{lines.join('\n')}</code>
      </pre>
    </details>
  )
}

type Tone = 'info' | 'ok' | 'warn' | 'bad'
const ICON: Record<Tone, string> = { info: 'ℹ', ok: '✓', warn: '!', bad: '✕' }
const LABEL: Record<Tone, string> = { info: 'Nota', ok: 'OK', warn: 'Atenção', bad: 'Problema' }

export function Note({ tone = 'info', children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div className={`note note-${tone}`} role={tone === 'bad' ? 'alert' : undefined}>
      <span className="note-icon" aria-hidden>
        {ICON[tone]}
      </span>
      <span className="sr-only">{LABEL[tone]}: </span>
      <div>{children}</div>
    </div>
  )
}

export function Stats({ items }: { items: { label: ReactNode; value: ReactNode; hint?: ReactNode }[] }) {
  return (
    <dl className="stats">
      {items.map((it, i) => (
        <div key={i} className="stat">
          <dt>{it.label}</dt>
          <dd>{it.value}</dd>
          {it.hint && <small>{it.hint}</small>}
        </div>
      ))}
    </dl>
  )
}

export function Table({ head, rows, caption }: { head: ReactNode[]; rows: ReactNode[][]; caption?: ReactNode }) {
  return (
    <div className="table-wrap">
      <table>
        {caption && <caption>{caption}</caption>}
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StabilityBadge({ stable }: { stable: boolean | undefined }) {
  if (stable === undefined) return null
  return <span className={`badge ${stable ? 'badge-ok' : 'badge-bad'}`}>{stable ? '✓ Estável' : '✕ Instável'}</span>
}

const sec = (x: Num | undefined) => (x === null || x === undefined ? '—' : `${fmt(x)} s`)

export function StepInfoStats({ info, title }: { info: StepInfo; title?: string }) {
  if (info.stable === false) return <Note tone="bad">{title ? `${title}: ` : ''}sistema instável — não há regime permanente.</Note>
  return (
    <Stats
      items={[
        { label: 'Valor final', value: fmt(info.final_value) },
        { label: 'Tempo de subida (10–90%)', value: sec(info.rise_time) },
        { label: 'Tempo de pico', value: sec(info.peak_time) },
        { label: 'Sobressinal', value: info.overshoot === null || info.overshoot === undefined ? '—' : `${fmt(info.overshoot)} %` },
        { label: 'Acomodação (2%)', value: sec(info.settling_time) },
      ]}
    />
  )
}

/** Aviso de IA desabilitada, com as duas formas de habilitar. */
export function AiDisabled({ what = 'Desabilitado neste servidor' }: { what?: string }) {
  return (
    <>
      {what}: defina <code>ANTHROPIC_API_KEY</code> no backend para usar o Claude, ou <code>LLM_PROVIDER=ollama</code> para usar um modelo local (por
      exemplo, <code>qwen3.5</code>).
    </>
  )
}
