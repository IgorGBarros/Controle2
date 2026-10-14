import { BodeCharts, XYChart } from '../components/Charts'
import { Tex } from '../components/Tex'
import { Matlab, Note, StabilityBadge, Stats, StepInfoStats, Table } from '../components/ui'
import { fmt, fmtCx, texNum } from '../lib/format'
import type { Dominant, ItemA, ItemB, ItemC, ItemD, ItemE, ItemF, ItemG, Margins } from '../lib/types'

function Matrix({ name, m }: { name: string; m: number[][] }) {
  const body = m.map((row) => row.map((v) => texNum(v)).join(' & ')).join(' \\\\ ')
  return <Tex>{`${name} = \\begin{bmatrix} ${body} \\end{bmatrix}`}</Tex>
}

export function ItemAView({ d }: { d: ItemA }) {
  return (
    <>
      <p>
        Representação de um sistema linear de ordem <em>n = {d.order}</em> por uma equação diferencial. Aplicando a transformada de
        Laplace com condições iniciais nulas obtém-se a função de transferência.
      </p>
      <Tex block>{d.ode}</Tex>
      <Tex block>{d.laplace}</Tex>
      <Tex block>{d.tf}</Tex>
      <h3>Espaço de estados da planta (forma canônica controlável)</h3>
      <div className="matrices">
        <Matrix name="A" m={d.state_space.A} />
        <Matrix name="B" m={d.state_space.B} />
        <Matrix name="C" m={d.state_space.C} />
        <Matrix name="D" m={d.state_space.D} />
      </div>
      <Tex block>{'\\dot{x} = A x + B u, \\qquad y = C x + D u'}</Tex>
      {d.delay > 0 && d.pade && (
        <>
          <h3>Atraso de transporte</h3>
          <Tex block>{`e^{-${texNum(d.delay)}s} \\approx ${d.pade}\\quad\\text{(Padé de ordem ${d.pade_order})}`}</Tex>
        </>
      )}
      <h3>Malha de controle</h3>
      <Stats
        items={[
          { label: 'Controlador C(s)', value: d.controller_pid ? `PID (Kp=${fmt(d.controller_pid.kp)}, Ki=${fmt(d.controller_pid.ki)}, Kd=${fmt(d.controller_pid.kd)})` : <Tex>{d.blocks.controller.latex}</Tex> },
          { label: 'Sensor H(s)', value: <Tex>{d.blocks.sensor.latex}</Tex> },
          { label: 'Realimentação', value: d.feedback === 'positive' ? 'positiva (+)' : 'negativa (−)' },
        ]}
      />
      {d.controller_pid && <Tex block>{`C(s) = ${d.blocks.controller.latex}`}</Tex>}
      <Tex block>{d.open_loop}</Tex>
      <Tex block>{d.closed_loop}</Tex>
      <Matlab lines={d.matlab} />
    </>
  )
}

export function ItemBView({ d }: { d: ItemB }) {
  return (
    <>
      <p>
        <strong>{d.classification}</strong> — tipo {d.system_type}, grau relativo {d.relative_degree}.
      </p>
      <Table
        head={['Coeficiente', 'Termo', 'Valor']}
        rows={[
          ...d.den_coeffs.map((c) => [<Tex key="n">{c.name}</Tex>, <Tex key="t">{`s^{${c.power}}\\text{ (den.)}`}</Tex>, fmt(c.value)]),
          ...d.num_coeffs.map((c) => [<Tex key="n">{c.name}</Tex>, <Tex key="t">{`s^{${c.power}}\\text{ (num.)}`}</Tex>, fmt(c.value)]),
        ]}
      />
      <Tex block>{`G(s) = ${d.tf}`}</Tex>
      <Stats items={[{ label: 'Ganho DC  G(0)', value: fmt(d.dc_gain) }]} />
      <h3>Resposta ao degrau unitário da planta{d.delay > 0 ? ' (com atraso)' : ''}</h3>
      <XYChart x={d.step.t} series={d.step.series} lines={[{ key: 'step', label: 'y(t)' }]} xLabel="Tempo (s)" yLabel="Amplitude" />
      <p className="muted">Saída em regime: {d.step_behaviour}.</p>
    </>
  )
}

export function DominantStats({ dom }: { dom: Dominant }) {
  if (!dom.stable) return <Note tone="bad">O polo dominante está sobre o eixo imaginário ou no semiplano direito.</Note>
  return (
    <Stats
      items={[
        { label: 'Polo dominante', value: fmtCx(dom.pole) },
        { label: 'ωn', value: `${fmt(dom.wn)} rad/s` },
        { label: 'ζ (qsi)', value: fmt(dom.zeta) },
        { label: 'σ', value: fmt(dom.sigma) },
        { label: 'ωd', value: `${fmt(dom.wd)} rad/s` },
      ]}
    />
  )
}

export function ItemCView({ d }: { d: ItemC }) {
  return (
    <>
      <p>Fatorando o denominador {d.standard ? '' : 'da malha aberta L(s) = C(s)G(s)H(s) '}em termos de 1ª e 2ª ordem:</p>
      <Tex block>{d.factored}</Tex>
      <p>
        Cada fator quadrático é comparado com a forma padrão <Tex>{'s^2 + 2\\zeta\\omega_n s + \\omega_n^2'}</Tex>, de onde{' '}
        <Tex>{'\\omega_n = \\sqrt{c}'}</Tex> e <Tex>{'\\zeta = b / (2\\omega_n)'}</Tex>.
      </p>
      <Table
        head={['Fator', 'Tipo', 'ωn (rad/s)', 'ζ', 'τ (s)']}
        rows={d.factors.map((f) =>
          f.kind === 'quadratic'
            ? [<Tex key="l">{f.latex}</Tex>, '2ª ordem', fmt(f.wn), fmt(f.zeta), '—']
            : [<Tex key="l">{f.latex}</Tex>, '1ª ordem', '—', '—', fmt(f.tau)],
        )}
      />
      {d.factors
        .filter((f) => f.kind === 'quadratic')
        .map((f, i) => (f.kind === 'quadratic' ? <Tex key={i} block>{`\\frac{1}{${f.normalized}}`}</Tex> : null))}
      {d.second_order && (
        <Note>
          Sistema de 2ª ordem: ωn = {fmt(d.second_order.wn)} rad/s e ζ = {fmt(d.second_order.zeta)}
          {d.second_order.zeta >= 1 ? ' (sobreamortecido/criticamente amortecido).' : ' (subamortecido).'}
        </Note>
      )}
      {d.dominant && (
        <>
          <h3>Par dominante (mais próximo do eixo jω)</h3>
          <DominantStats dom={d.dominant} />
        </>
      )}
      {!d.factors.some((f) => f.kind === 'quadratic') && <Note>Não há polos complexos: o sistema não possui fator de 2ª ordem subamortecido.</Note>}
      <Matlab lines={d.matlab} />
    </>
  )
}

export function ItemDView({ d }: { d: ItemD }) {
  return (
    <>
      <Note tone={d.stable ? 'ok' : 'bad'}>{d.verdict}</Note>
      {d.blocks && (
        <p className="muted">
          Polos de L(s) = C·G·H vindos de cada bloco —{' '}
          {Object.entries(d.blocks)
            .map(([k, v]) => `${k}: ${v.length ? v.join(', ') : 'nenhum'}`)
            .join(' · ')}
        </p>
      )}
      <Table
        head={['Polo', '|p| = ωn', 'ζ', 'τ = 1/σ (s)', 'Situação']}
        rows={d.poles.map((p) => [p.text, fmt(p.wn), fmt(p.zeta), fmt(p.tau), <StabilityBadge key="s" stable={p.stable} />])}
      />
      <Stats
        items={[
          { label: 'Zeros', value: d.zeros.length ? d.zeros.map((z) => z.text).join(', ') : 'nenhum' },
          { label: 'Ganho (zpk)', value: fmt(d.gain) },
        ]}
      />
      <h3>Critério de Routh-Hurwitz do denominador</h3>
      <Table
        head={['', ...d.routh.rows[0].values.map((_, i) => `col ${i + 1}`)]}
        rows={d.routh.rows.map((r) => [<Tex key="p">{`s^{${r.power}}`}</Tex>, ...r.values.map((v) => fmt(v))])}
      />
      <p className="muted">Trocas de sinal na 1ª coluna: {d.routh.sign_changes} (= nº de polos no semiplano direito).</p>
      {d.routh.notes.map((n, i) => (
        <Note key={i} tone="warn">
          {n}
        </Note>
      ))}
      <Matlab lines={d.matlab} />
    </>
  )
}

export function ItemEView({ d }: { d: ItemE }) {
  return (
    <>
      <p>
        Fechando a malha com ganho <strong>K = {fmt(d.K)}</strong> em série com o controlador:
      </p>
      <Tex block>{d.tf}</Tex>
      <p>
        Polos de malha fechada: {d.closed_loop.poles.map((p) => fmtCx(p)).join(' ; ')} <StabilityBadge stable={d.closed_loop.stable} />
      </p>
      <XYChart x={d.step.t} series={d.step.series} lines={[{ key: 'step', label: 'y(t)' }]} xLabel="Tempo (s)" yLabel="Amplitude" title="Resposta ao degrau em malha fechada" />
      <StepInfoStats info={d.info} />
      <p className="muted">
        Saída: {d.behaviour}. Erro em regime ao degrau:{' '}
        {d.ess_step.kind === 'settles' ? `${fmt(d.ess_step.value)} (${fmt((d.ess_step.value as number) * 100)} %)` : '—'}
      </p>
      <Matlab lines={d.matlab} />
    </>
  )
}

export function ItemFView({ d }: { d: ItemF }) {
  return (
    <>
      <p>Escrevendo a malha aberta na forma de Bode (constantes de tempo):</p>
      <Tex block>{d.bode_form}</Tex>
      <p>
        Ganho de Bode: {fmt(d.bode_gain)} → {fmt(d.bode_gain_db)} dB. Inclinação inicial: {d.low_slope} dB/déc
        {d.type > 0 ? ` (${d.type} polo(s) na origem)` : ''}.
      </p>
      <Table
        head={['Frequência de canto (rad/s)', 'Origem', 'Mudança de inclinação', 'Inclinação após', 'Fase total do fator']}
        rows={d.corners.map((c) => [
          fmt(c.w),
          `${c.kind}${c.order === 2 ? ' duplo (complexo, ζ=' + fmt(c.zeta) + ')' : ''}${c.rhp ? ' — semiplano direito' : ''}`,
          `${c.slope > 0 ? '+' : ''}${c.slope} dB/déc`,
          `${c.slope_after} dB/déc`,
          `${c.phase > 0 ? '+' : ''}${c.phase}°`,
        ])}
      />
      <BodeCharts
        w={d.w}
        series={d.series}
        mag={[
          { key: 'mag_asym', label: 'Assíntotas' },
          { key: 'mag', label: 'Exato', dashed: true },
        ]}
        phase={[
          { key: 'phase_asym', label: 'Assíntotas' },
          { key: 'phase', label: 'Exato', dashed: true },
        ]}
        magRefs={d.corners.map((c) => ({ x: c.w }))}
      />
      <p className="muted">
        Fase assintótica: fatores de 1ª ordem variam linearmente entre ωc/10 e 10ωc; fatores de 2ª ordem são aproximados por um degrau em ωn.
      </p>
    </>
  )
}

function MarginStats({ m }: { m: Margins }) {
  return (
    <Stats
      items={[
        { label: 'Margem de ganho', value: m.gm_db === 'inf' ? '∞' : `${fmt(m.gm_db)} dB`, hint: m.gm === 'inf' ? '' : `(${fmt(m.gm)} ×)` },
        { label: 'ω cruzamento de fase', value: m.wpc === null ? '—' : `${fmt(m.wpc)} rad/s` },
        { label: 'Margem de fase', value: m.pm === 'inf' ? '∞' : `${fmt(m.pm)}°` },
        { label: 'ω cruzamento de ganho', value: m.wgc === null ? '—' : `${fmt(m.wgc)} rad/s` },
        { label: 'Malha fechada', value: <StabilityBadge stable={m.closed_loop_stable} /> },
      ]}
    />
  )
}

export function ItemGView({ d }: { d: ItemG }) {
  const m = d.margins
  return (
    <>
      <BodeCharts
        w={d.w}
        series={d.series}
        mag={[
          { key: 'mag', label: d.standard ? 'G(jω)' : 'L(jω)' },
          { key: 'mag_k', label: `K·${d.standard ? 'G' : 'L'}(jω), K=${fmt(d.K)}` },
        ]}
        phase={[{ key: 'phase', label: 'Fase' }]}
        magRefs={[{ y: 0, label: '0 dB' }, ...(typeof m.wpc === 'number' ? [{ x: m.wpc }] : [])]}
        phaseRefs={[{ y: -180, label: '−180°' }, ...(typeof m.wpc === 'number' ? [{ x: m.wpc, label: 'ωpc' }] : [])]}
      />
      {d.positive_feedback && (
        <Note tone="warn">Realimentação positiva: as margens são calculadas para −L(s), que equivale a uma malha com realimentação negativa.</Note>
      )}
      <h3>Margens de {d.standard ? 'G(s)' : 'L(s)'} (K = 1)</h3>
      <MarginStats m={m} />
      {typeof m.gm === 'number' && m.closed_loop_stable && (
        <Note>
          A margem de ganho indica que a malha fechada fica no limite da estabilidade com um ganho de {fmt(m.gm)} (= Ku, ganho crítico).
        </Note>
      )}
      <h3>Margens de K·{d.standard ? 'G(s)' : 'L(s)'} com K = {fmt(d.K)}</h3>
      <MarginStats m={d.margins_k} />
      <Matlab lines={d.matlab} />
    </>
  )
}
