import type { ReactNode } from 'react'
import { RichText } from './RichText'

/** Texto do tutor: parágrafos, listas com "- " ou "1.", **negrito** e fórmulas $...$ / $$...$$. */
function Inline({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return (
    <>
      {parts.map((p, i) => (p.startsWith('**') && p.endsWith('**') && p.length > 4 ? <strong key={i}><RichText text={p.slice(2, -2)} /></strong> : <RichText key={i} text={p} />))}
    </>
  )
}

export function ChatText({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  const lines = text.split('\n')
  let list: { ordered: boolean; items: string[] } | null = null
  let para: string[] = []
  const flushPara = () => {
    if (para.length) blocks.push(<p key={blocks.length}><Inline text={para.join(' ')} /></p>)
    para = []
  }
  const flushList = () => {
    if (list) {
      const items = list.items.map((it, i) => <li key={i}><Inline text={it} /></li>)
      blocks.push(list.ordered ? <ol key={blocks.length}>{items}</ol> : <ul key={blocks.length}>{items}</ul>)
    }
    list = null
  }
  for (const raw of lines) {
    const line = raw.trim()
    const bullet = /^[-*•]\s+(.*)$/.exec(line)
    const numbered = /^\d+[.)]\s+(.*)$/.exec(line)
    if (line.startsWith('$$') && line.endsWith('$$') && line.length > 4) {
      flushPara()
      flushList()
      blocks.push(<RichText key={blocks.length} text={line} />)
    } else if (bullet || numbered) {
      flushPara()
      const ordered = Boolean(numbered)
      if (!list || list.ordered !== ordered) {
        flushList()
        list = { ordered, items: [] }
      }
      list.items.push((bullet ?? numbered)![1])
    } else if (!line) {
      flushPara()
      flushList()
    } else {
      flushList()
      para.push(line.replace(/^#+\s*/, ''))
    }
  }
  flushPara()
  flushList()
  return <div className="chat-text">{blocks}</div>
}
