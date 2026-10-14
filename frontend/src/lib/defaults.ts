import type { AnalyzeParams, LoopSpec } from './types'

/** Malha padrão: planta do trabalho de 2013 com realimentação unitária negativa. */
export const DEFAULT_LOOP: LoopSpec = {
  plant: { mode: 'tf', num: '1', den: '1 11.3 14 10' },
  controller: { mode: 'tf', num: '1', den: '1' },
  sensor: { num: '1', den: '1' },
  feedback: 'negative',
  delay: 0,
  pade_order: 2,
}

/** Parâmetros padrão: mesmos valores usados no trabalho de 2013. */
export const DEFAULT_PARAMS: AnalyzeParams = {
  k: 10,
  k_step: null,
  k_ramp: null,
  k_impulse: null,
  ess_target: 0.05,
  ts_spec: 3,
  mp_spec: 7.5,
  sine_freq: 1,
  sine_amp: 1,
  tfinal: null,
  zn_include_gain: true,
}

/** Preenche os campos ausentes de um exemplo com os valores padrão da malha. */
export function completeLoop(spec: LoopSpec): Required<LoopSpec> {
  return {
    plant: { ...DEFAULT_LOOP.plant, ...spec.plant },
    controller: { ...DEFAULT_LOOP.controller!, ...spec.controller },
    sensor: { ...DEFAULT_LOOP.sensor, ...spec.sensor },
    feedback: spec.feedback ?? 'negative',
    delay: spec.delay ?? 0,
    pade_order: spec.pade_order ?? 2,
  }
}
