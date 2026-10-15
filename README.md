# Controle II — Análise de Sistemas

**Uma ferramenta web para estudar sistemas de controle clássico.** Você descreve uma malha de controle — a
planta, o controlador, o sensor e o tipo de realimentação — e a ferramenta calcula e explica, passo a passo,
tudo o que normalmente se faz à mão ou no MATLAB em uma disciplina de Controle: função de transferência,
polos e estabilidade, resposta ao degrau, diagramas de Bode, margens, lugar das raízes, erro em regime,
projeto de ganho e sintonia de PID por Ziegler-Nichols. No final, gera um relatório explicativo com base em
livros de referência da área.

![Visão geral da ferramenta](docs/img/visao-geral.png)

## Por que existe

A ferramenta nasceu de um trabalho de Controle II de um curso de Engenharia Mecatrônica (2013). Nele, uma
planta de 3ª ordem foi analisada em 18 itens (a até r) com MATLAB e SIMULINK. Este projeto transforma aquele
roteiro em uma aplicação que funciona **para qualquer sistema**: em vez de reescrever scripts para cada
planta, basta informar a malha e todos os itens são recalculados, com gráficos, fórmulas e interpretação.

Ela é útil para:

- **estudantes**, que podem conferir exercícios, ver o efeito de cada parâmetro e entender o porquê de cada
  resultado;
- **professores**, para gerar exemplos e gabaritos rapidamente;
- **quem precisa de uma análise rápida** de uma malha SISO sem ter MATLAB instalado.

## Como funciona

```
 r ──►(Σ)──► K·C(s) ──► G(s)·e^(−θs) ──┬──► y
       ▲ ∓                             │
       └────────── H(s) ◄──────────────┘
```

1. **Monte a malha.** Informe a planta **G(s)** (função de transferência, zeros/polos/ganho ou espaço de
   estados), um **atraso** opcional, o **controlador C(s)** (função de transferência ou PID), o **sensor H(s)**
   e se a realimentação é **negativa ou positiva**. Polinômios aceitam o formato do MATLAB (`1 11.3 14 10`) ou
   expressões em `s` (`(s+10)(s^2+1.3s+1)`).
2. **Defina as especificações**, como o ganho K, o erro em regime desejado e os limites de tempo de acomodação
   (Ts) e sobressinal (Mp).
3. **Clique em "Analisar malha".** O backend calcula os 18 itens e o relatório; o frontend mostra cada item
   com fórmulas, tabelas e gráficos interativos.
4. **Simule** a malha no tempo, ajustando os ganhos do PID e acrescentando saturação, perturbação e ruído.
5. **Leia o relatório final** e, se quiser, **converse com o tutor de IA** sobre os resultados.

![Formulário com uma malha que tem sensor na realimentação](docs/img/formulario-malha.png)

## O que a ferramenta calcula

| Item | O que mostra |
|---|---|
| **a** | Equação diferencial, transformada de Laplace, função de transferência, espaço de estados e as funções de malha aberta L(s) e fechada T(s) |
| **b** | Coeficientes, ordem, tipo, ganho estático e resposta ao degrau da planta |
| **c** | Fatoração do denominador e frequência natural ωn e amortecimento ζ de cada fator de 2ª ordem |
| **d** | Polos, zeros, estabilidade em malha aberta e tabela de Routh-Hurwitz |
| **e** | Malha fechada com ganho K: função de transferência, polos e resposta ao degrau |
| **f** | Diagrama de Bode por assíntotas (frequências de canto e inclinações) comparado à curva exata |
| **g** | Bode com margem de ganho e margem de fase |
| **h** | Respostas a degrau, impulso e rampa em malha aberta e fechada, com o erro em regime |
| **i** | Ganho para cada tipo de entrada, constantes de erro Kp, Kv, Ka e faixa de K que mantém a malha estável |
| **j** | Lugar das raízes: assíntotas, pontos de separação, ângulos de partida, cruzamento com o eixo jω e Routh em função de K |
| **k / l** | Desempenho transitório (tempo de subida, de pico, de acomodação e sobressinal) em malha aberta e fechada — pela fórmula e medido na simulação |
| **m** | Comparação entre malha aberta e fechada no mesmo gráfico |
| **n** | Ganho proporcional para um erro em regime especificado, avisando se ele desestabiliza a malha |
| **o** | Ganho proporcional para atender Ts e Mp: polos desejados, condição de ângulo e varredura de K |
| **p** | Ziegler-Nichols, 1º método (curva de reação): controladores P, PI e PID |
| **q** | Ziegler-Nichols, 2º método (ganho crítico Ku e período Pu): controladores P, PI e PID |
| **r** | Média dos parâmetros dos dois métodos e simulação para degrau, rampa e senoide |

<p align="center">
  <img src="docs/img/lugar-das-raizes.png" alt="Lugar das raízes" width="49%">
  <img src="docs/img/ziegler-nichols.png" alt="Sintonia por Ziegler-Nichols" width="49%">
</p>

### Simulação no tempo

A seção **s) Simulação no tempo** integra a malha passo a passo e mostra o que a análise linear não mostra:

- **saturação do atuador** e **anti-windup** (integração condicional ou *back-calculation*);
- **perturbação de carga** na entrada da planta e **ruído no sensor**;
- **controlador discreto**, com período de amostragem próprio;
- **atraso de transporte exato**, simulado com um buffer de amostras em vez da aproximação de Padé;
- referência em degrau, onda quadrada, rampa ou senoide.

Os ganhos Kp, Ki e Kd são ajustados por *sliders* e o gráfico é recalculado na hora. Dá para fixar uma resposta e
compará-la com outra, por exemplo com e sem anti-windup. A simulação mostra a saída, o sinal de controle (antes e
depois da saturação) e métricas como IAE, sobressinal, tempo de acomodação, recuperação após a perturbação, tempo
em saturação e variação total do sinal de controle. Ela também avisa quando a malha diverge ou quando a saturação
está mascarando uma malha linear instável.

O controlador segue a forma paralela do bloco **PID Controller do Simulink**: `Kp + Ki/s + Kd·N·s/(s + N)`,
com N = 100 e a derivada sobre o erro por padrão (também é possível aplicá-la sobre a medição, o que evita o
pico de controle na mudança de referência). O botão **"Reproduzir o diagrama do Simulink (item r)"** monta o
mesmo diagrama do trabalho de 2013 (degrau em t = 1 s, H(s) = 1, sem saturação). Com os ganhos usados em 2013
(Kp = 46,1129, Ki = 53,80365, Kd = 10,2266), a simulação chega ao mesmo pico de 1,49 cerca de 1,4 s após o
degrau mostrado no Scope original — isso é verificado por um teste automatizado.

![Simulação com saturação: resposta com anti-windup comparada à resposta fixada sem anti-windup](docs/img/simulacao-windup.png)

#### Assistente de sintonia com IA

Dentro do simulador, o aluno descreve o objetivo ("sobressinal abaixo de 5% e o atuador não pode passar de 20")
e o assistente:

1. traduz o objetivo em especificações numéricas;
2. escolhe a estrutura (P, PI, PD ou PID) e a variante (derivada sobre erro ou medição, anti-windup);
3. usa como ferramentas o **simulador** e um **otimizador numérico** (Nelder-Mead minimizando IAE, ITAE ou ISE
   com penalidade para as restrições), mudando de estratégia quando uma restrição não é atendida;
4. entrega a recomendação com o compromisso envolvido; a sintonia é re-simulada pelo motor e pode ser aplicada
   aos *sliders* com um clique.

O Claude decide **o que** otimizar; os **números** vêm sempre do simulador e do otimizador.

### Relatório final explicativo

Depois dos itens, a ferramenta escreve um relatório que **interpreta os resultados daquela malha**: se ela é
estável e por quê, como os polos explicam a resposta no tempo, o que as margens dizem sobre robustez, por que
um ganho que reduz o erro pode desestabilizar o sistema, que tipo de compensador seria necessário e como
os PIDs de Ziegler-Nichols se comportam. Inclui largura de banda, pico de ressonância e o diagrama polar
(Nyquist) com o critério Z = N + P. O texto cita, por capítulo:

- OGATA, Katsuhiko. *Engenharia de Controle Moderno*. 5. ed. São Paulo: Pearson, 2011.
- MEZA, Magno Enrique Mendoza. *Sistemas de Controle com Python: Resposta em Frequência*. São Paulo: Blucher, 2024.

O relatório pode ser impresso ou salvo em PDF pelo navegador.

![Seção de resposta em frequência do relatório, com o diagrama de Nyquist](docs/img/relatorio-frequencia.png)

### Recursos de IA (opcionais)

Com uma chave da API do Claude configurada no backend, aparecem dois recursos:

- **Descrever o sistema em linguagem natural** — por exemplo, *"motor CC com J = 0,01 kg·m², b = 0,1 N·m·s,
  R = 1 Ω e L = 0,5 H"*. O modelo deriva G(s), C(s) e H(s), mostra a modelagem e as hipóteses, e a malha só é
  usada depois de **validada pelo motor de cálculo**. O formulário é preenchido para você conferir antes de
  analisar.
- **Tutor de IA** — um chat ao final da página que responde perguntas sobre a malha analisada ("por que o
  sobressinal aumenta com K?"), explicando com base nos dois livros acima.
- **Assistente de sintonia** — dentro do simulador, encontra os ganhos do controlador a partir de um objetivo
  em linguagem natural, usando o simulador e o otimizador como ferramentas.

Sem a chave, a ferramenta funciona normalmente; os painéis apenas indicam como habilitá-los.

### Princípio: os números vêm sempre do motor de cálculo

Todos os valores são calculados com NumPy, SciPy e SymPy (raízes, simulação, Routh, margens, lugar das raízes).
O relatório é gerado a partir desses números, e a IA apenas os interpreta — o backend recalcula a análise e
envia os resultados ao modelo, que é instruído a não inventar valores.

### Diferenças em relação ao trabalho original

A ferramenta reproduz os resultados do trabalho de 2013 (ωn = 1, ζ = 0,65, Ku = 148,2, Pu = 1,679 s…), mas
corrige alguns pontos:

- **Itens k e l:** usa as fórmulas corretas `tr = (π − β)/ωd` e `Mp = e^(−σπ/ωd)` (o original obteve
  14,69 por um erro de sinal no expoente; o valor correto é Mp ≈ 6,8%).
- **Item n:** K = 190 atende ao erro de 5%, mas torna a malha **instável** (Ku = 148,2); a ferramenta avisa e
  mostra o menor erro possível só com ação proporcional.
- **Item p:** o atraso L e a constante de tempo T vêm da tangente exata no ponto de inflexão, em vez de leitura
  no gráfico. Por padrão as regras são normalizadas pelo ganho do processo; há uma opção para reproduzir a forma
  original.

## Como executar

Requisitos: Python 3.12+ e Node.js 20.19+ (ou 22.12+).

### Backend (Django, porta 8000)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```

### Frontend (React + Vite, porta 5173)

```bash
cd frontend
npm install
npm run dev
```

Acesse <http://localhost:5173>. Em desenvolvimento, o Vite encaminha `/api` para `http://127.0.0.1:8000`
(altere com `VITE_API_PROXY`).

### Habilitar a IA (opcional)

```bash
export ANTHROPIC_API_KEY=sk-ant-...      # antes de iniciar o Django
export CLAUDE_MODEL=claude-opus-5-5      # opcional
```

Com a IA habilitada, a descrição digitada, a malha e os resultados da análise são enviados à API da Anthropic.

### Testes

```bash
cd backend && python manage.py test          # inclui a validação contra os resultados de 2013
cd frontend && npm run lint && npm run build
```

### Hospedagem

Para hospedar frontend e backend separadamente, defina `VITE_API_URL` no build do frontend e, no backend,
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG=0`, `DJANGO_ALLOWED_HOSTS` e `CORS_ALLOWED_ORIGINS`. A API não usa banco
de dados.

## Tecnologias

- **Backend:** Python, Django, Django REST Framework, NumPy, SciPy, SymPy e o SDK `anthropic` (recursos de IA).
- **Frontend:** React, TypeScript, Vite, Recharts (gráficos) e KaTeX (fórmulas).

## API

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/analyze/` | Analisa uma malha e devolve os itens a–r e o relatório |
| `POST` | `/api/simulate/` | Simulação no tempo (`{"request": <corpo do /api/analyze/>, "sim": {...}}`) |
| `GET` | `/api/examples/` | Malhas de exemplo |
| `GET` | `/api/health/` | Verificação de saúde |
| `GET` | `/api/llm/status/` | Indica se a IA está habilitada e qual modelo |
| `POST` | `/api/describe/` | Linguagem natural → malha (`{"text": "..."}`) |
| `POST` | `/api/tutor/` | Tutor em streaming (`text/event-stream`) |
| `POST` | `/api/tune/` | Assistente de sintonia em streaming (`{"request", "sim", "goal"}`) |

Exemplo de corpo para `/api/analyze/`:

```json
{
  "plant": { "mode": "tf", "num": "1", "den": "1 11.3 14 10" },
  "controller": { "mode": "tf", "num": "1", "den": "1" },
  "sensor": { "num": "1", "den": "1" },
  "feedback": "negative",
  "delay": 0,
  "pade_order": 2,
  "k": 10,
  "ess_target": 0.05,
  "ts_spec": 3,
  "mp_spec": 7.5,
  "sine_freq": 1,
  "zn_include_gain": true
}
```

A planta também aceita `{"mode": "zpk", "zeros": "-3", "poles": "0, -2, -4", "gain": 8}` ou
`{"mode": "ss", "A": "[0 1; -2 -0.5]", "B": "[0; 1]", "C": "[1 0]", "D": "0"}`, e o controlador aceita
`{"mode": "pid", "kp": 20, "ki": 10, "kd": 5}`. Campos opcionais: `k_step`, `k_ramp`, `k_impulse`,
`sine_amp`, `tfinal`. O tutor recebe `{"request": <mesmo corpo do /api/analyze/>, "messages": [...]}` e
responde com eventos `{"delta": "..."}` seguidos de `{"done": true}`.

## Estrutura do projeto

```
backend/
  config/                 configurações do Django
  analysis/
    engine/
      parsing.py          leitura de polinômios, listas complexas e matrizes
      loop.py             malha C(s), G(s), H(s), sinal da realimentação, atraso (Padé)
      tf.py               função de transferência, simulação, indicadores da resposta
      stability.py        Routh-Hurwitz, lugar das raízes, ganho crítico
      items.py            itens a) a r)
      simulate.py         simulação no tempo (saturação, anti-windup, ruído, atraso exato)
      optimize.py         sintonia numérica de P/PI/PD/PID com restrições
      narrative.py        relatório final explicativo
      report.py           orquestração e serialização JSON
    examples.py           malhas de exemplo
    llm.py                tutor e entrada em linguagem natural (Claude)
    tuning.py             assistente de sintonia (Claude + simulador + otimizador)
    views.py, urls.py     API REST
    tests/                testes do motor, da API e da IA
frontend/
  src/
    lib/                  tipos, cliente da API, formatação
    components/           formulário, diagrama da malha, gráficos, relatório, tutor
    items/                visualização de cada item
docs/img/                 imagens deste README
```

## Limitações

- Plantas lineares, invariantes no tempo e SISO (uma entrada e uma saída). As não linearidades (saturação,
  ruído) existem apenas na simulação no tempo.
- Ordem máxima da malha aberta: 12. Nos itens a–r o atraso é aproximado por Padé; na simulação ele é exato.
- A modelagem física proposta pela IA é uma sugestão: o motor confere se a malha é válida, mas não se a física
  está correta — revise as hipóteses mostradas.
