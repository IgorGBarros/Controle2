# Controle II — Análise de Sistemas

Aplicação web que replica, para **qualquer planta G(s)**, todos os itens do *Trabalho de Controle II*
(Engenharia Mecatrônica — UNIFACS, 2013), originalmente resolvido no MATLAB/SIMULINK.

- **Backend:** Python + Django + Django REST Framework (cálculos com NumPy, SciPy e SymPy)
- **Frontend:** React + TypeScript + Vite (gráficos com Recharts, fórmulas com KaTeX)

## O que é calculado

| Item | Conteúdo | Comando MATLAB equivalente |
|---|---|---|
| a | Equação diferencial, Laplace, função de transferência e espaço de estados | `tf`, `tf2ss` |
| b | Coeficientes, ordem, tipo, ganho DC e resposta ao degrau em malha aberta | `step` |
| c | Fatoração do denominador, ωn e ζ de cada fator de 2ª ordem e do par dominante | `sqrt`, `roots` |
| d | Polos, zeros, ganho, estabilidade e tabela de Routh-Hurwitz | `tf2zp` |
| e | Malha fechada com ganho K e resposta ao degrau | `feedback`, `step` |
| f | Diagrama de Bode por assíntotas (frequências de canto, inclinações) × curva exata | — |
| g | Bode com margem de ganho e de fase (para G e para K·G) | `margin` |
| h | Saída para degrau, impulso e rampa em malha aberta e fechada, com erro em regime | `step`, `impulse`, `lsim` |
| i | Ganho para cada entrada, constantes de erro Kp/Kv/Ka e faixa de K estável | — |
| j | Lugar das raízes: assíntotas, centroide, separação, ângulos de partida, cruzamento jω, Routh em K | `rlocus` |
| k | Desempenho transitório em malha aberta (tr, tp, Mp, ts) — analítico e medido | `stepinfo` |
| l | Idem em malha fechada com controlador proporcional unitário | `stepinfo` |
| m | Comparação malha aberta × fechada no mesmo gráfico | — |
| n | Ganho proporcional para um erro em regime especificado (verifica a estabilidade) | — |
| o | Ganho proporcional para Ts e Mp especificados (polos desejados, condição de ângulo e varredura de K) | — |
| p | Ziegler-Nichols 1º método (tangente no ponto de inflexão): P, PI, PID | — |
| q | Ziegler-Nichols 2º método (ganho crítico Ku e período Pu): P, PI, PID | — |
| r | Média dos parâmetros dos dois métodos e simulação para degrau, rampa e senoide | SIMULINK |

A planta pode ser informada no formato vetorial do MATLAB (`1 11.3 14 10`) ou como expressão em `s`
(`(s+10)(s^2+1.3s+1)`). O exemplo padrão é a planta do trabalho original:

```
G(s) = 1 / (s³ + 11,3 s² + 14 s + 10)
```

### Diferenças em relação ao trabalho de 2013

O objetivo é replicar o trabalho, mas alguns cálculos foram corrigidos:

- **Item k/l:** as fórmulas corretas são `tr = (π − β)/ωd` e `Mp = e^(−σπ/ωd)` (o original usava
  `atan(...)/ωd` e o expoente positivo, chegando a Mp = 14,69). Os valores medidos na simulação também são exibidos.
- **Item n:** K = 190 atende ao erro de 5%, mas a malha fechada é **instável** (Ku = 148,2). A aplicação avisa
  e mostra o menor erro alcançável só com ação proporcional.
- **Item p:** L e T são obtidos pela tangente exata no ponto de inflexão (no original foram estimados no gráfico).
  Por padrão as regras são normalizadas pelo ganho estático do processo; a opção pode ser desligada para reproduzir o original.

## Como executar

### Backend (porta 8000)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```

### Frontend (porta 5173)

```bash
cd frontend
npm install
npm run dev
```

Acesse <http://localhost:5173>. Em desenvolvimento, o Vite encaminha `/api` para `http://127.0.0.1:8000`
(altere com a variável `VITE_API_PROXY`). Para hospedar separadamente, defina `VITE_API_URL` no build do
frontend e `CORS_ALLOWED_ORIGINS` / `DJANGO_ALLOWED_HOSTS` / `DJANGO_SECRET_KEY` / `DJANGO_DEBUG=0` no backend.

### Testes

```bash
cd backend && python manage.py test     # valida os resultados contra o trabalho de 2013
cd frontend && npm run lint && npm run build
```

## API

`POST /api/analyze/`

```json
{
  "num": "1",
  "den": "1 11.3 14 10",
  "k": 10,
  "ess_target": 0.05,
  "ts_spec": 3,
  "mp_spec": 7.5,
  "sine_freq": 1,
  "zn_include_gain": true
}
```

Opcionais: `k_step`, `k_ramp`, `k_impulse`, `sine_amp`, `tfinal`. A resposta contém `system` e a lista
`items` (a–r), cada um com `data` ou `error`.

`GET /api/examples/` — plantas de exemplo · `GET /api/health/` — verificação de saúde.

## Estrutura

```
backend/
  config/                 configurações do Django
  analysis/
    engine/
      parsing.py          leitura de polinômios (vetor ou expressão em s)
      tf.py               função de transferência, simulação, stepinfo
      stability.py        Routh-Hurwitz, lugar das raízes, Ku
      items.py            itens a) a r)
      report.py           orquestração e serialização JSON
    views.py, urls.py     API REST
    tests/                testes do motor e da API
frontend/
  src/
    lib/                  tipos, cliente da API, formatação
    components/           formulário, gráficos, KaTeX, UI
    items/                visualização de cada item
```
