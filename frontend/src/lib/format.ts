import type { Behaviour, Cx, Interval, Num } from './types'

export function fmt(x: Num | undefined, digits = 4): string {
  if (x === null || x === undefined) return '—'
  if (x === 'inf') return '∞'
  if (x === '-inf') return '−∞'
  if (Math.abs(x) < 1e-12) return '0'
  const abs = Math.abs(x)
  if (abs >= 1e5 || abs < 1e-3) return x.toExponential(2).replace('.', ',').replace('e', '×10^').replace('+', '')
  return Number(x.toPrecision(digits)).toLocaleString('pt-BR', { maximumFractionDigits: 6 })
}

export function fmtUnit(x: Num | undefined, unit: string, digits = 4): string {
  const s = fmt(x, digits)
  return s === '—' ? s : `${s} ${unit}`
}

export function fmtCx(z: Cx, digits = 4): string {
  if (Math.abs(z.im) < 1e-12) return fmt(z.re, digits)
  const sign = z.im >= 0 ? '+' : '−'
  return `${fmt(z.re, digits)} ${sign} ${fmt(Math.abs(z.im), digits)}j`
}

export function fmtInterval([lo, hi]: Interval): string {
  return `${fmt(lo)} < K < ${hi === null ? '∞' : fmt(hi)}`
}

export function behaviourText(b: Behaviour | undefined): string {
  if (!b) return '—'
  switch (b.kind) {
    case 'settles':
      return fmt(b.value)
    case 'unbounded':
      return '∞ (cresce sem limite)'
    case 'oscillates':
      return 'oscila'
    case 'diverge':
      return 'diverge (instável)'
  }
}

/** Número para uso dentro de LaTeX (vírgula decimal sem espaço extra). */
export function texNum(x: Num | undefined, digits = 4): string {
  const s = fmt(x, digits)
  if (s === '∞') return '\\infty'
  return s.replace(/\./g, '').replace(',', '{,}').replace('×10^', '\\times 10^').replace('—', '-')
}
