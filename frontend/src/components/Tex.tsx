import katex from 'katex'
import 'katex/dist/katex.min.css'
import { useMemo } from 'react'

interface Props {
  children: string
  block?: boolean
}

/** Renderiza LaTeX com KaTeX. */
export function Tex({ children, block = false }: Props) {
  const html = useMemo(
    () => katex.renderToString(children, { displayMode: block, throwOnError: false, strict: 'ignore' }),
    [children, block],
  )
  if (block) return <div className="tex-block" dangerouslySetInnerHTML={{ __html: html }} />
  return <span dangerouslySetInnerHTML={{ __html: html }} />
}
