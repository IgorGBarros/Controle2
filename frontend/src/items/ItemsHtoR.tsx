import { RootLocusChart, XYChart } from '../components/Charts'
import { LoopDiagram } from '../components/LoopDiagram'
import { Tex } from '../components/Tex'
import { Matlab, Note, StabilityBadge, Stats, StepInfoStats, Table } from '../components/ui'
import { behaviourText, fmt, fmtCx, fmtInterval, texNum } from '../lib/format'
import type {
  ControllersResponse,
  Dominant,
  ItemH,
  ItemI,
  ItemJ,
  ItemM,
  ItemN,
  ItemO,
  ItemP,
  ItemQ,
  ItemR,
  PidRow,
  ResponseSet,
  RuleRow,
  StepInfo,
  Transient,
} from '../lib/types'

const INPUT_LABEL: Record<string, string> = { step: 'Degrau', ramp: 'Rampa', impulse: 'Impulso', sine: 'Senoide' }

function InputCharts({ rs, kinds }: { rs: ResponseSet; kinds: ('step' | 'ramp' | 'impulse')[] }) {
  return (
    <div className="grid-3">
      {kinds.map((k) => (
        <div key={k}>
          <XYChart
            x={rs.t}
            series={rs.series}
            lines={k === 'ramp' ? [{ key: 'ramp', label: 'y(t)' }, { key: 'ramp_input', label: 'r(t) = t', dashed: true }] : [{ key: k, label: 'y(t)' }]}
            xLabel="Tempo (s)"
            title={`Entrada ${INPUT_LABEL[k].toLowerCase()}`}
            height={230}
          />
          <p className="muted small">Saída: {rs.analysis[k]?.output_text}.</p>
          {rs.analysis[k]?.error && <p className="muted small">Erro em regime: {behaviourText(rs.analysis[k].error)}</p>}
        </div>
      ))}
    </div>
  )
}

export function ItemHView({ d }: { d: ItemH }) {
  return (
    <>
      <h3>Malha aberta — {d.standard ? 'G(s)' : 'L(s) = C(s)G(s)H(s)'}</h3>
      <InputCharts rs={d.open_loop} kinds={['step', 'impulse', 'ramp']} />
      <h3>Malha fechada (K = 1)</h3>
      <Tex block>{`T(s) = ${d.closed_loop_tf}`}</Tex>
      <InputCharts rs={d.closed_loop} kinds={['step', 'impulse', 'ramp']} />
      <Note>
        Para a rampa, a saída sempre cresce junto com a entrada; o que importa é o <em>erro</em> r(t) − y(t). Erro em regime infinito significa que o
        sistema não consegue acompanhar a rampa (sistema tipo 0), e não que ele seja instável. O erro é sempre medido como e(t) = r(t) − y(t).
      </Note>
    </>
  )
}

export function ItemIView({ d }: { d: ItemI }) {
  const c = d.constants_unit
  return (
    <>
      <p>
        Faixa de ganho com malha fechada estável:{' '}
        <strong>{d.stable_intervals.length ? d.stable_intervals.map(fmtInterval).join(' ∪ ') : 'nenhum K > 0'}</strong>
      </p>
      <Table
        head={[d.unity_feedback ? 'Constante de erro (K = 1)' : 'Constante de erro de G_eq = T/(1−T), K = 1', 'Valor', 'Erro em regime']}
        rows={[
          [<Tex key="k">{'K_p = \\lim_{s\\to0} G_{eq}(s)'}</Tex>, fmt(c.Kp), <Tex key="e">{'e_{degrau} = 1/(1+K_p)'}</Tex>],
          [<Tex key="k">{'K_v = \\lim_{s\\to0} sG_{eq}(s)'}</Tex>, fmt(c.Kv), <Tex key="e">{'e_{rampa} = 1/K_v'}</Tex>],
          [<Tex key="k">{'K_a = \\lim_{s\\to0} s^2G_{eq}(s)'}</Tex>, fmt(c.Ka), <Tex key="e">{'e_{parábola} = 1/K_a'}</Tex>],
        ]}
      />
      <div className="grid-3">
        {(['step', 'ramp', 'impulse'] as const).map((k) => {
          const inp = d.inputs[k]
          return (
            <div key={k}>
              <h4>
                {INPUT_LABEL[k]} — K = {fmt(inp.K)} <StabilityBadge stable={inp.stable} />
              </h4>
              <XYChart
                x={inp.t}
                series={inp.series}
                lines={k === 'ramp' ? [{ key: 'ramp', label: 'y(t)' }, { key: 'ramp_input', label: 'r(t)', dashed: true }] : [{ key: k, label: 'y(t)' }]}
                xLabel="Tempo (s)"
                height={220}
              />
              <p className="muted small">
                Saída: {inp.analysis[k]?.output_text}. Erro em regime: {behaviourText(inp.analysis[k]?.error)}
              </p>
            </div>
          )
        })}
      </div>
      <p className="muted">Os ganhos de cada entrada podem ser ajustados nos parâmetros avançados.</p>
    </>
  )
}

export function ItemJView({ d }: { d: ItemJ }) {
  return (
    <>
      <p>Equação característica da malha fechada com ganho K: 1 {d.positive_feedback ? '−' : '+'} K·L(s) = 0</p>
      {d.positive_feedback && <Note tone="warn">Realimentação positiva: o lugar das raízes é o “de 0°”, traçado aqui como o lugar de −L(s).</Note>}
      <Tex block>{d.characteristic}</Tex>
      <RootLocusChart data={d} />
      <Table
        head={['Regra', 'Resultado']}
        rows={[
          ['Nº de ramos', String(d.poles.length)],
          ['Polos / zeros finitos', `${d.poles.length} / ${d.zeros.length}`],
          ...(d.asymptotes
            ? [
                ['Centroide das assíntotas σa', fmt(d.asymptotes.centroid)],
                ['Ângulos das assíntotas', d.asymptotes.angles.map((a) => `${fmt(a)}°`).join(', ')],
              ]
            : []),
          ['Pontos de separação/chegada', d.breakaway.length ? d.breakaway.map((b) => `s = ${fmt(b.s)} (K = ${fmt(b.K)})`).join('; ') : 'nenhum'],
          ['Ângulos de partida (polos complexos)', d.departure.length ? d.departure.map((x) => `${fmt(x.angle)}° em ${fmt(x.pole[0])}+${fmt(x.pole[1])}j`).join('; ') : '—'],
          ['Cruzamentos com o eixo jω', d.jw_crossings.length ? d.jw_crossings.map((c) => `ω = ±${fmt(c.w)} rad/s para K = ${fmt(c.K)}`).join('; ') : 'nenhum'],
          ['Faixa de K estável', d.stable_intervals.length ? d.stable_intervals.map(fmtInterval).join(' ∪ ') : 'nenhum K > 0'],
        ]}
      />
      {d.critical && d.critical.Pu && (
        <Note>
          Ganho crítico <strong>Ku = {fmt(d.critical.Ku)}</strong>, frequência de oscilação ωu = {fmt(d.critical.wu)} rad/s, período Pu ={' '}
          {fmt(d.critical.Pu)} s.
        </Note>
      )}
      {d.routh_k && (
        <>
          <h3>Tabela de Routh em função de K</h3>
          <Table
            head={['', ...d.routh_k.rows[0].values.map((_, i) => `col ${i + 1}`)]}
            rows={d.routh_k.rows.map((r) => [<Tex key="p">{`s^{${r.power}}`}</Tex>, ...r.values.map((v, i) => <Tex key={i}>{v}</Tex>)])}
          />
          <p className="muted">Estabilidade exige todos os elementos da 1ª coluna com o mesmo sinal.</p>
        </>
      )}
      <Matlab lines={d.matlab} />
    </>
  )
}

function AnalyticTable({ dom, measured }: { dom: Dominant | null; measured: StepInfo }) {
  const s = (x: unknown) => (typeof x === 'number' ? `${fmt(x)} s` : '—')
  return (
    <Table
      head={['Parâmetro', 'Fórmula (polo dominante)', 'Analítico', 'Medido na simulação']}
      rows={[
        ['Tempo de subida', <Tex key="f">{'t_r = (\\pi - \\beta)/\\omega_d'}</Tex>, s(dom?.rise_time), `${s(measured.rise_time)} (10–90%)`],
        ['Tempo de pico', <Tex key="f">{'t_p = \\pi/\\omega_d'}</Tex>, s(dom?.peak_time), s(measured.peak_time)],
        [
          'Sobressinal máximo',
          <Tex key="f">{'M_p = e^{-\\sigma\\pi/\\omega_d}'}</Tex>,
          typeof dom?.overshoot === 'number' ? `${fmt(dom.overshoot)} %` : '—',
          typeof measured.overshoot === 'number' ? `${fmt(measured.overshoot)} %` : '—',
        ],
        ['Tempo de acomodação (2%)', <Tex key="f">{'t_s = 4/\\sigma'}</Tex>, s(dom?.settling_time_2), s(measured.settling_time)],
        ['Tempo de acomodação (5%)', <Tex key="f">{'t_s = 3/\\sigma'}</Tex>, s(dom?.settling_time_5), '—'],
      ]}
    />
  )
}

export function TransientView({ d }: { d: Transient }) {
  return (
    <>
      <Tex block>{d.tf}</Tex>
      <p>Polos: {d.poles.map((p) => fmtCx(p)).join(' ; ')}</p>
      {d.dominant && d.dominant.stable ? (
        <>
          <Stats
            items={[
              { label: 'Polo dominante', value: fmtCx(d.dominant.pole) },
              { label: 'σ', value: fmt(d.dominant.sigma) },
              { label: 'ωd', value: `${fmt(d.dominant.wd)} rad/s` },
              { label: 'ωn', value: `${fmt(d.dominant.wn)} rad/s` },
              { label: 'ζ', value: fmt(d.dominant.zeta) },
            ]}
          />
          <AnalyticTable dom={d.dominant} measured={d.measured} />
          <Note>
            As fórmulas analíticas consideram só o par dominante (aproximação de 2ª ordem). A coluna “medido” vem da simulação do sistema completo e
            serve para validar a aproximação.
          </Note>
        </>
      ) : (
        <Note tone="bad">Sistema instável ou marginalmente estável — os critérios de desempenho transitório não se aplicam.</Note>
      )}
      <Matlab lines={d.matlab} />
    </>
  )
}

export function ItemMView({ d }: { d: ItemM }) {
  const row = (label: string, a: unknown, b: unknown, unit = '') => [label, typeof a === 'number' ? `${fmt(a)}${unit}` : '—', typeof b === 'number' ? `${fmt(b)}${unit}` : '—']
  return (
    <>
      <XYChart
        x={d.t}
        series={d.series}
        lines={[
          { key: 'open', label: 'Malha aberta' },
          { key: 'closed', label: 'Malha fechada (K = 1)' },
        ]}
        xLabel="Tempo (s)"
        yLabel="Amplitude"
        title="Resposta ao degrau unitário"
        height={320}
      />
      <Table
        head={['Parâmetro', 'Malha aberta', 'Malha fechada (K=1)']}
        rows={[
          row('Valor final', d.open.final_value, d.closed.final_value),
          row('Tempo de subida (10–90%)', d.open.rise_time, d.closed.rise_time, ' s'),
          row('Tempo de pico', d.open.peak_time, d.closed.peak_time, ' s'),
          row('Sobressinal', d.open.overshoot, d.closed.overshoot, ' %'),
          row('Acomodação (2%)', d.open.settling_time, d.closed.settling_time, ' s'),
          row('ωn dominante', d.open_dominant?.wn, d.closed_dominant?.wn, ' rad/s'),
          row('ζ dominante', d.open_dominant?.zeta, d.closed_dominant?.zeta),
        ]}
      />
      <p className="muted">
        Fechar a malha altera o valor final (erro em regime) e desloca os polos, mudando ωn, ζ e consequentemente velocidade e sobressinal.
      </p>
    </>
  )
}

export function ItemNView({ d }: { d: ItemN }) {
  if (!d.applicable) return <Note>{d.reason}</Note>
  return (
    <>
      <p>
        Entrada de referência para o tipo deste sistema: <strong>{d.input}</strong>. Erro desejado: <strong>{fmt((d.target ?? 0) * 100)} %</strong>.
      </p>
      {!d.unity_feedback && (
        <Note>Com realimentação não unitária, o erro e = r − y é obtido diretamente de T(s) e o ganho K é encontrado numericamente.</Note>
      )}
      <Tex block>{d.limit ?? ''}</Tex>
      <Tex block>{d.formula ?? ''}</Tex>
      <Stats
        items={[
          { label: 'Ganho proporcional K', value: fmt(d.K) },
          { label: 'Malha fechada', value: <StabilityBadge stable={d.stable} /> },
          { label: 'Faixa estável', value: d.stable_intervals?.map(fmtInterval).join(' ∪ ') || 'nenhuma' },
        ]}
      />
      {d.warning && <Note tone="bad">{d.warning}</Note>}
      {d.stable && d.error && <Note tone="ok">Com K = {fmt(d.K)} a malha fechada é estável e o erro em regime fica em {behaviourText(d.error)}.</Note>}
      {d.t && d.series && (
        <XYChart
          x={d.t}
          series={d.series}
          lines={[
            { key: 'output', label: 'y(t)' },
            { key: 'input', label: 'r(t)', dashed: true },
          ]}
          xLabel="Tempo (s)"
          title={`Resposta em malha fechada com K = ${fmt(d.K)}`}
        />
      )}
    </>
  )
}

export function ItemOView({ d }: { d: ItemO }) {
  const scanSeries = {
    ts: d.scan.map((s) => s.ts),
    mp: d.scan.map((s) => s.mp),
  }
  const ks = d.scan.map((s) => s.K)
  return (
    <>
      <p>
        Especificações: <strong>Ts &lt; {fmt(d.ts_spec)} s</strong> e <strong>Mp &lt; {fmt(d.mp_spec)} %</strong>.
      </p>
      <Tex block>{`T_s = \\frac{4}{\\sigma} \\Rightarrow \\sigma = \\frac{4}{${texNum(d.ts_spec)}} = ${texNum(d.sigma)}`}</Tex>
      <Tex block>{`M_p = e^{-\\pi\\sigma/\\omega_d} \\Rightarrow \\omega_d = \\frac{-\\pi\\sigma}{\\ln M_p} = ${texNum(d.wd)}\\ \\text{rad/s}`}</Tex>
      <Tex block>{`\\omega_n = \\sqrt{\\sigma^2 + \\omega_d^2} = ${texNum(d.wn)}, \\qquad \\zeta = ${texNum(d.zeta)}`}</Tex>
      <Tex block>{`\\text{FTMF desejada} = ${d.desired_tf}`}</Tex>
      <p>
        Polos desejados: <strong>{d.desired_poles.map((p) => fmtCx(p)).join(' e ')}</strong>.
      </p>
      {d.on_locus ? (
        <Note tone="ok">
          Os polos desejados pertencem ao lugar das raízes: K = 1/|G(s<sub>d</sub>)| = {fmt(d.k_at_desired)}.
        </Note>
      ) : (
        <Note tone="warn">
          Os polos desejados <strong>não</strong> pertencem ao lugar das raízes (∠G(s<sub>d</sub>) = {fmt(d.angle_at_desired)}°, deficiência angular de{' '}
          {fmt(d.angle_deficiency)}°). Só com ganho proporcional não é possível posicioná-los exatamente — seria necessário um compensador (avanço/PD)
          que contribua com essa fase.
        </Note>
      )}
      <h3>Varredura de K (simulação do sistema completo)</h3>
      {d.scan.length > 0 && (
        <div className="grid-2">
          <XYChart x={ks} series={scanSeries} lines={[{ key: 'ts', label: 'Ts (s)' }]} xLabel="K" yLabel="Ts (s)" logX refs={[{ y: d.ts_spec, label: 'limite' }]} height={240} title="Tempo de acomodação × K" />
          <XYChart x={ks} series={scanSeries} lines={[{ key: 'mp', label: 'Mp (%)', color: 'var(--series-2)' }]} xLabel="K" yLabel="Mp (%)" logX refs={[{ y: d.mp_spec, label: 'limite' }]} height={240} title="Sobressinal × K" />
        </div>
      )}
      {d.feasible ? (
        <Note tone="ok">
          Faixa(s) de K que atendem às duas especificações: {d.feasible_ranges.map(([a, b]) => `${fmt(a)} ≤ K ≤ ${fmt(b)}`).join(' ; ')}. Menor Ts obtido com
          K = {fmt(d.best?.K)} (Ts = {fmt(d.best?.ts)} s, Mp = {fmt(d.best?.mp)} %).
        </Note>
      ) : (
        <Note tone="bad">
          Nenhum ganho proporcional atende simultaneamente às especificações.
          {d.best && ` Melhor compromisso com Mp dentro do limite: K = ${fmt(d.best.K)} → Ts = ${fmt(d.best.ts)} s, Mp = ${fmt(d.best.mp)} %.`}
        </Note>
      )}
      {d.response && d.best && (
        <XYChart x={d.response.t} series={d.response.series} lines={[{ key: 'step', label: 'y(t)' }]} xLabel="Tempo (s)" title={`Resposta ao degrau com K = ${fmt(d.best.K)}`} />
      )}
    </>
  )
}

function RulesTable({ rules }: { rules: RuleRow[] }) {
  return (
    <Table
      head={['Controlador', 'Kp', 'Ti', 'Td']}
      rows={rules.map((r) => [r.controller, <Tex key="kp">{r.Kp}</Tex>, <Tex key="ti">{r.Ti}</Tex>, <Tex key="td">{r.Td}</Tex>])}
    />
  )
}

function PidTable({ table, closed }: { table: PidRow[]; closed?: ControllersResponse['closed'] }) {
  return (
    <Table
      head={['Controlador', 'Kp', 'Ki = Kp/Ti', 'Kd = Kp·Td', 'Malha fechada', 'Mp', 'Ts (2%)']}
      rows={table.map((r) => {
        const c = closed?.[r.controller]
        return [
          r.controller,
          fmt(r.Kp),
          fmt(r.Ki),
          fmt(r.Kd),
          <StabilityBadge key="s" stable={c?.stable} />,
          typeof c?.info.overshoot === 'number' ? `${fmt(c.info.overshoot)} %` : '—',
          typeof c?.info.settling_time === 'number' ? `${fmt(c.info.settling_time)} s` : '—',
        ]
      })}
    />
  )
}

function ControllerCharts({ d }: { d: Partial<ControllersResponse> }) {
  if (!d.t || !d.series || !d.closed) return null
  return (
    <>
      <XYChart
        x={d.t}
        series={d.series}
        lines={[
          { key: 'P', label: 'P' },
          { key: 'PI', label: 'PI' },
          { key: 'PID', label: 'PID' },
        ]}
        xLabel="Tempo (s)"
        yLabel="Amplitude"
        title="Resposta ao degrau em malha fechada"
        refs={[{ y: 1 }]}
        height={320}
      />
      {(['PI', 'PID'] as const).map((k) => (
        <div key={k}>
          <Tex block>{`C_{${k}}(s) = ${d.closed![k].controller_tf} \\qquad T_{${k}}(s) = ${d.closed![k].tf}`}</Tex>
        </div>
      ))}
    </>
  )
}

export function ItemPView({ d }: { d: ItemP }) {
  return (
    <>
      <p>
        No 1º método obtém-se a resposta do processo ao degrau{d.process_is_plant === false ? ' (P(s) = G(s)H(s), o que o controlador “enxerga”)' : ''}. Pela reta tangente no ponto
        de inflexão da curva em S determinam-se o atraso L e a constante de tempo T. O controlador C(s) informado é substituído pelos controladores calculados.
      </p>
      <RulesTable rules={d.rules} />
      {!d.applicable ? (
        <Note tone="warn">{d.reason}</Note>
      ) : (
        <>
          {d.plant && d.tangent && (
            <XYChart
              x={d.plant.t}
              series={{
                ...d.plant.series,
                tangent: d.plant.t.map((t) => {
                  const [[l], [l2, k]] = d.tangent!
                  const y = (k * (t - l)) / (l2 - l)
                  return y < Math.min(0, k) - Math.abs(k) * 0.1 || y > Math.max(0, k) + Math.abs(k) * 0.1 ? null : y
                }),
              }}
              lines={[
                { key: 'step', label: 'Resposta ao degrau' },
                { key: 'tangent', label: 'Tangente na inflexão', dashed: true },
              ]}
              xLabel="Tempo (s)"
              yLabel="Amplitude"
              refs={[{ y: d.process_gain }, { x: d.L, label: 'L' }, { x: (d.L ?? 0) + (d.T ?? 0), label: 'L+T' }]}
              height={300}
            />
          )}
          <Stats
            items={[
              { label: 'Atraso L (td)', value: `${fmt(d.L)} s` },
              { label: 'Constante de tempo T (τ)', value: `${fmt(d.T)} s` },
              { label: 'Ganho do processo K', value: fmt(d.process_gain) },
              { label: 'Inflexão', value: `t = ${fmt(d.inflection?.t)} s` },
            ]}
          />
          {d.warnings?.map((w, i) => (
            <Note key={i} tone="warn">
              {w}
            </Note>
          ))}
          <Note>
            {d.gain_included
              ? 'As regras foram normalizadas pelo ganho estático do processo (Kp = 1,2·T/(K·L) etc.). Desmarque a opção nos parâmetros para usar T/L sem normalizar, como no trabalho original.'
              : 'Regras aplicadas sem normalizar pelo ganho estático do processo (como no trabalho original).'}
          </Note>
          {d.table && <PidTable table={d.table} closed={d.closed} />}
          <ControllerCharts d={d} />
        </>
      )}
    </>
  )
}

export function ItemQView({ d }: { d: ItemQ }) {
  return (
    <>
      <p>
        Substituindo C(s) por uma ação proporcional, aumenta-se Kp de zero até o ganho crítico Ku, no qual a saída apresenta oscilação sustentada com período Pu.
      </p>
      <RulesTable rules={d.rules} />
      {!d.applicable ? (
        <Note tone="warn">{d.reason}</Note>
      ) : (
        <>
          <Stats
            items={[
              { label: 'Ganho crítico Ku', value: fmt(d.Ku) },
              { label: 'Frequência ωu', value: `${fmt(d.wu)} rad/s` },
              { label: 'Período crítico Pu', value: `${fmt(d.Pu)} s` },
            ]}
          />
          {d.oscillation && (
            <XYChart x={d.oscillation.t} series={d.oscillation.series} lines={[{ key: 'step', label: 'y(t)' }]} xLabel="Tempo (s)" title={`Oscilação sustentada com K = Ku = ${fmt(d.Ku)}`} height={240} />
          )}
          {d.table && <PidTable table={d.table} closed={d.closed} />}
          <ControllerCharts d={d} />
        </>
      )}
    </>
  )
}

export function ItemRView({ d }: { d: ItemR }) {
  if (!d.applicable || !d.average || !d.t || !d.series || !d.analysis) return <Note tone="warn">{d.reason}</Note>
  const a = d.average
  return (
    <>
      <p>Média dos parâmetros obtidos em: {d.sources?.join(' e ')}.</p>
      <Table
        head={['Controlador', 'Kp médio', 'Ki médio', 'Kd médio']}
        rows={(['P', 'PI', 'PID'] as const).map((k) => [k, fmt(a[k].Kp), fmt(a[k].Ki), fmt(a[k].Kd)])}
      />
      <p>Sistema montado (equivalente ao diagrama do SIMULINK) com o PID médio no lugar de C(s):</p>
      <LoopDiagram controller="PID(s)" plant="G(s)" sensor={d.sensor_unity ? 'H = 1' : 'H(s)'} feedback={d.positive_feedback ? 'positive' : 'negative'} />
      {!d.sensor_unity && d.sensor_tf && <Tex block>{`H(s) = ${d.sensor_tf}`}</Tex>}
      <Tex block>{`C(s) = ${d.controller_tf}`}</Tex>
      <Tex block>{`T(s) = ${d.tf}`}</Tex>
      <p>
        Malha fechada: <StabilityBadge stable={d.stable} />
      </p>
      {d.info && <StepInfoStats info={d.info} />}
      <div className="grid-3">
        <div>
          <XYChart x={d.t} series={d.series} lines={[{ key: 'step', label: 'y(t)' }]} xLabel="Tempo (s)" title="Saída — degrau" refs={[{ y: 1 }]} height={230} />
          <p className="muted small">Erro em regime: {behaviourText(d.analysis.step?.error)}</p>
        </div>
        <div>
          <XYChart
            x={d.t}
            series={d.series}
            lines={[
              { key: 'ramp', label: 'y(t)' },
              { key: 'ramp_input', label: 'r(t)', dashed: true },
            ]}
            xLabel="Tempo (s)"
            title="Saída — rampa"
            height={230}
          />
          <p className="muted small">Erro em regime: {behaviourText(d.analysis.ramp?.error)}</p>
        </div>
        <div>
          <XYChart
            x={d.t}
            series={d.series}
            lines={[
              { key: 'sine', label: 'y(t)' },
              { key: 'sine_input', label: 'r(t)', dashed: true },
            ]}
            xLabel="Tempo (s)"
            title={`Saída — senoide (ω = ${fmt(d.sine?.freq)} rad/s)`}
            height={230}
          />
          <p className="muted small">
            Em regime: amplitude × {fmt(d.analysis.sine?.amplitude_ratio)}, defasagem {fmt(d.analysis.sine?.phase_deg)}°.
          </p>
        </div>
      </div>
    </>
  )
}
