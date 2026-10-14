function niceStep(range: number, target = 5): number {
  const raw = range / target
  const mag = 10 ** Math.floor(Math.log10(raw))
  const n = raw / mag
  return (n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10) * mag
}

/** Domínio e marcas "redondas" para o eixo y. */
export function niceAxis(values: (number | null)[]): { domain: [number, number]; ticks: number[] } | undefined {
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

