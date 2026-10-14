import { Fragment } from 'react'
import { Tex } from './Tex'

/** Texto com fórmulas: $...$ (inline) e $$...$$ (bloco) são renderizados com KaTeX. */
export function RichText({ text }: { text: string }) {
  if (text.startsWith('$$') && text.endsWith('$$')) return <Tex block>{text.slice(2, -2)}</Tex>
  const parts = text.split(/(\$[^$]+\$)/g)
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith('$') && p.endsWith('$') && p.length > 2 ? <Tex key={i}>{p.slice(1, -1)}</Tex> : <Fragment key={i}>{p}</Fragment>,
      )}
    </>
  )
}
