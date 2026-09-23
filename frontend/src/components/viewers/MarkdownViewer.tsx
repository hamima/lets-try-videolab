import { useEffect, useState } from 'react'
import { marked } from 'marked'

export default function MarkdownViewer({ content }: { content: string }) {
  const [html, setHtml] = useState('')

  useEffect(() => {
    setHtml(marked.parse(content) as string)
  }, [content])

  return (
    <div
      className="markdown-content"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
