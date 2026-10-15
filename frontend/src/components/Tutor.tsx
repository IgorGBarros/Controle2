import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, askTutor, type ChatMessage } from '../lib/api'
import type { AnalyzeRequest } from '../lib/types'
import { ChatText } from './ChatText'
import { AiDisabled } from './ui'

const SUGGESTIONS = [
  'Explique em palavras simples se esta malha é estável e por quê.',
  'Por que o ganho do item n deixa a malha instável?',
  'Como interpretar as margens de ganho e de fase deste sistema?',
  'Que compensador você sugere para atender Ts e Mp? Justifique com os resultados.',
  'Qual a diferença entre os PIDs do 1º e do 2º método de Ziegler-Nichols aqui?',
]

interface Props {
  request: AnalyzeRequest
  enabled: boolean
  model?: string
}

/** Tutor de IA: responde sobre a malha atual usando os resultados calculados pela ferramenta. */
export function Tutor({ request, enabled, model }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const requestKey = JSON.stringify(request)
  const [convKey, setConvKey] = useState(requestKey)

  // Uma nova análise começa uma nova conversa (o contexto mudou).
  if (convKey !== requestKey) {
    setConvKey(requestKey)
    setMessages([])
    setError(null)
  }

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [messages])

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || busy) return
    const history: ChatMessage[] = [...messages, { role: 'user', content: question }]
    setMessages([...history, { role: 'assistant', content: '' }])
    setInput('')
    setBusy(true)
    setError(null)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    try {
      await askTutor(request, history, (delta) => {
        setMessages((m) => {
          const copy = m.slice()
          const last = copy[copy.length - 1]
          copy[copy.length - 1] = { ...last, content: last.content + delta }
          return copy
        })
      }, ctrl.signal)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError(e instanceof ApiError ? e.message : 'Não foi possível falar com o tutor.')
        // remove a pergunta sem resposta para manter a alternância usuário/tutor
        setMessages((m) => (m[m.length - 1]?.content ? m : m.slice(0, -2)))
      }
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  return (
    <section id="tutor" className="section tutor no-print">
      <div className="report-head">
        <h2>Tutor de IA</h2>
        {messages.length > 0 && (
          <button type="button" className="chip" onClick={() => setMessages([])} disabled={busy}>
            Nova conversa
          </button>
        )}
      </div>
      {!enabled ? (
        <p className="muted">
          <AiDisabled what="O tutor está desabilitado neste servidor. Para habilitar" /> Depois, reinicie o Django.
        </p>
      ) : (
        <>
          <p className="muted small">
            Pergunte sobre a malha analisada acima. O tutor recebe os resultados calculados pela ferramenta e explica com base em Ogata e Meza; os números
            são sempre os da ferramenta.{model ? ` Modelo: ${model}.` : ''}
          </p>
          <div className="chat" aria-live="polite">
            {messages.length === 0 && (
              <div className="suggestions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chip" onClick={() => void send(s)} disabled={busy}>
                    {s}
                  </button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`bubble ${m.role}`}>
                <span className="who">{m.role === 'user' ? 'Você' : 'Tutor'}</span>
                {m.role === 'assistant' ? (m.content ? <ChatText text={m.content} /> : <span className="typing">pensando…</span>) : <p>{m.content}</p>}
              </div>
            ))}
            <div ref={endRef} />
          </div>
          {error && <p className="field-error">{error}</p>}
          <form className="chat-input" onSubmit={submit}>
            <textarea
              rows={2}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  void send(input)
                }
              }}
              placeholder="Ex.: por que o sobressinal aumenta quando K cresce?"
              disabled={busy}
            />
            <button type="submit" className="primary" disabled={busy || !input.trim()}>
              {busy ? 'Respondendo…' : 'Perguntar'}
            </button>
          </form>
        </>
      )}
    </section>
  )
}
