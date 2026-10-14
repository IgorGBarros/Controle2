// Tipos da resposta da API (/api/analyze/).

export type Num = number | 'inf' | '-inf' | null
export interface Cx {
  re: number
  im: number
}
export type Series = Record<string, (number | null)[]>

export interface TimeData {
  t: number[]
  series: Series
}

export type BehaviourKind = 'settles' | 'unbounded' | 'oscillates' | 'diverge'
export interface Behaviour {
  kind: BehaviourKind
  value: Num
}

export interface StepInfo {
  stable?: boolean
  final_value?: Num
  rise_time?: Num
  peak_time?: Num
  peak?: Num
  overshoot?: Num
  settling_time?: Num
}

export interface Dominant {
  pole: Cx
  sigma: number
  wd: number
  complex: boolean
  stable: boolean
  wn?: number
  zeta?: number
  beta?: number
  tau?: number
  rise_time?: Num
  peak_time?: Num
  overshoot?: Num
  settling_time_2?: Num
  settling_time_5?: Num
}

export interface ResponseSet extends TimeData {
  analysis: Record<
    string,
    {
      output?: Behaviour
      output_text?: string
      error?: Behaviour
      amplitude_ratio?: Num
      phase_deg?: Num
      output_amplitude?: Num
    }
  >
}

export interface PidRow {
  controller: 'P' | 'PI' | 'PID'
  Kp: number
  Ki: number | null
  Kd: number | null
  Ti: number | null
  Td: number | null
}

export interface RuleRow {
  controller: string
  Kp: string
  Ti: string
  Td: string
}

export interface ControllersResponse {
  closed: Record<string, { controller_tf: string; tf: string; stable: boolean; info: StepInfo }>
  t: number[]
  series: Series
}

export type Interval = [number, number | null]

export interface Margins {
  gm_db: Num
  gm: Num
  wpc: Num
  pm: Num
  wgc: Num
  closed_loop_stable: boolean
}

export interface TfInfo {
  num: number[]
  den: number[]
  latex: string
  poles: Cx[]
  zeros: Cx[]
  stable: boolean
}

export interface BlockInfo {
  latex: string
  poles: Cx[]
  zeros: Cx[]
  unity: boolean
}

export type Feedback = 'negative' | 'positive'

export interface PidGains {
  kp: number
  ki: number
  kd: number
}

export interface SystemInfo extends TfInfo {
  plant: BlockInfo
  controller: BlockInfo
  sensor: BlockInfo
  controller_pid: PidGains | null
  open_loop: TfInfo
  closed_loop: TfInfo
  feedback: Feedback
  delay: number
  pade_order: number
  standard: boolean
}

export interface Item<T = unknown> {
  key: string
  title: string
  data: T | null
  error: string | null
}

export interface ReportSection {
  key: string
  title: string
  paragraphs: string[]
  bullets: string[]
  cites: string[]
  chart: { kind: 'nyquist'; re: number[]; im: number[]; w: number[] } | null
}

export interface Report {
  sections: ReportSection[]
  references: { key: string; cite: string; text: string }[]
}

export interface AnalysisResult {
  system: SystemInfo
  params: AnalyzeParams
  items: Item[]
  report: Report
}

export interface AnalyzeParams {
  k: number
  k_step?: number | null
  k_ramp?: number | null
  k_impulse?: number | null
  ess_target: number
  ts_spec: number
  mp_spec: number
  sine_freq: number
  sine_amp: number
  tfinal?: number | null
  zn_include_gain: boolean
}

export interface PlantSpec {
  mode: 'tf' | 'zpk' | 'ss'
  num?: string
  den?: string
  zeros?: string
  poles?: string
  gain?: number
  A?: string
  B?: string
  C?: string
  D?: string
}

export interface ControllerSpec {
  mode: 'tf' | 'pid'
  num?: string
  den?: string
  kp?: number
  ki?: number
  kd?: number
}

export interface LoopSpec {
  plant: PlantSpec
  controller?: ControllerSpec
  sensor?: { num?: string; den?: string }
  feedback?: Feedback
  delay?: number
  pade_order?: number
}

export type AnalyzeRequest = AnalyzeParams & LoopSpec

export interface Example {
  name: string
  description: string
  spec: LoopSpec
}

/* ---- itens ---- */

export interface ItemA {
  order: number
  standard: boolean
  feedback: Feedback
  blocks: { plant: BlockInfo; controller: BlockInfo; sensor: BlockInfo }
  controller_pid: PidGains | null
  delay: number
  pade: string | null
  pade_order: number
  open_loop: string
  closed_loop: string
  ode: string
  laplace: string
  tf: string
  state_space: { A: number[][]; B: number[][]; C: number[][]; D: number[][] }
  matlab: string[]
}

export interface ItemB {
  den_coeffs: { name: string; power: number; value: number }[]
  num_coeffs: { name: string; power: number; value: number }[]
  classification: string
  system_type: number
  relative_degree: number
  dc_gain: Num
  tf: string
  delay: number
  step: TimeData
  step_behaviour: string
}

export interface ItemC {
  standard: boolean
  factored: string
  factors: (
    | { kind: 'real'; pole: number; latex: string; tau: number | null }
    | { kind: 'quadratic'; poles: Cx[]; b: number; c: number; wn: number; zeta: number; latex: string; normalized: string }
  )[]
  second_order: { wn: number; zeta: number } | null
  dominant: Dominant | null
  matlab: string[]
}

export interface RouthTable {
  rows: { power: number; values: number[] }[]
  sign_changes: number
  notes: string[]
  stable: boolean
}

export interface ItemD {
  poles: { value: Cx; text: string; wn: number; zeta: number | null; tau: number | null; stable: boolean }[]
  zeros: { value: Cx; text: string }[]
  gain: number
  stable: boolean
  routh: RouthTable
  standard: boolean
  blocks: Record<string, string[]> | null
  verdict: string
  matlab: string[]
}

export interface ItemE {
  K: number
  closed_loop: TfInfo
  tf: string
  step: TimeData
  info: StepInfo
  behaviour: string
  ess_step: Behaviour
  matlab: string[]
}

export interface Corner {
  w: number
  kind: 'polo' | 'zero'
  order: number
  slope: number
  slope_after: number
  rhp: boolean
  zeta: number | null
  phase: number
}

export interface ItemF {
  bode_gain: number
  bode_gain_db: number
  type: number
  low_slope: number
  corners: Corner[]
  bode_form: string
  w: number[]
  series: Series
}

export interface ItemG {
  K: number
  standard: boolean
  positive_feedback: boolean
  w: number[]
  series: Series
  margins: Margins
  margins_k: Margins
  matlab: string[]
}

export interface ItemH {
  open_loop: ResponseSet
  closed_loop: ResponseSet
  closed_loop_tf: string
  standard: boolean
}

export interface ItemI {
  stable_intervals: Interval[]
  inputs: Record<
    'step' | 'ramp' | 'impulse',
    ResponseSet & { K: number; tf: string; stable: boolean; constants: { Kp: Num; Kv: Num; Ka: Num } }
  >
  constants_unit: { Kp: Num; Kv: Num; Ka: Num }
  system_type: number
  unity_feedback: boolean
}

export interface ItemJ {
  poles: [number, number][]
  zeros: [number, number][]
  branches: [number, number, number][][]
  asymptotes: { centroid: number; angles: number[] } | null
  breakaway: { s: number; K: number }[]
  departure: { pole: [number, number]; angle: number }[]
  jw_crossings: { K: number; w: number }[]
  window: { x: [number, number]; y: [number, number] }
  stable_intervals: Interval[]
  routh_k: { rows: { power: number; values: string[] }[]; first_column: string[] } | null
  critical: { Ku: number; wu: number; Pu: number | null } | null
  positive_feedback: boolean
  characteristic: string
  matlab: string[]
}

export interface Transient {
  tf: string
  poles: Cx[]
  dominant: Dominant | null
  measured: StepInfo
  matlab: string[]
}

export interface ItemM extends TimeData {
  open: StepInfo
  closed: StepInfo
  open_dominant: Dominant | null
  closed_dominant: Dominant | null
}

export interface ItemN {
  applicable: boolean
  reason?: string
  input?: string
  target?: number
  K?: number | null
  unity_feedback?: boolean
  limit?: string
  formula?: string
  stable?: boolean
  stable_intervals?: Interval[]
  tf?: string
  t?: number[]
  series?: Series
  error?: Behaviour
  warning?: string
  k_max?: number
  e_min?: number
}

export interface ScanPoint {
  K: number
  ts: number | null
  mp: number | null
  tr: number | null
}

export interface ItemO {
  ts_spec: number
  mp_spec: number
  zeta: number
  sigma: number
  wd: number
  wn: number
  desired_poles: Cx[]
  desired_poly: string
  desired_tf: string
  angle_at_desired: number
  angle_deficiency: number
  on_locus: boolean
  k_at_desired: number | null
  scan: ScanPoint[]
  feasible: boolean
  feasible_ranges: [number, number][]
  best: ScanPoint | null
  response: (TimeData & { tf: string; poles: Cx[] }) | null
}

export interface ItemP extends Partial<ControllersResponse> {
  applicable: boolean
  reason?: string
  rules: RuleRow[]
  L?: number
  T?: number
  process_gain?: number
  gain_included?: boolean
  inflection?: { t: number; y: number; slope: number }
  plant?: TimeData
  tangent?: [number, number][]
  table?: PidRow[]
  warnings?: string[]
  process_is_plant?: boolean
}

export interface ItemQ extends Partial<ControllersResponse> {
  applicable: boolean
  reason?: string
  rules: RuleRow[]
  Ku?: number
  Pu?: number
  wu?: number
  oscillation?: TimeData
  table?: PidRow[]
}

export interface ItemR extends Partial<ResponseSet> {
  applicable: boolean
  reason?: string
  sources?: string[]
  average?: Record<'P' | 'PI' | 'PID', { Kp: number; Ki: number | null; Kd: number | null }>
  controller_tf?: string
  tf?: string
  stable?: boolean
  info?: StepInfo
  sine?: { amp: number; freq: number }
  sensor_unity?: boolean
  sensor_tf?: string
  positive_feedback?: boolean
}
