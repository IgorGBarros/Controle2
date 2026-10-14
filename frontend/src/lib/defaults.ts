import type { AnalyzeRequest } from './types'

/** Parâmetros padrão: mesmos valores usados no trabalho de 2013. */
export const DEFAULT_REQUEST: AnalyzeRequest = {
  num: '1',
  den: '1 11.3 14 10',
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
