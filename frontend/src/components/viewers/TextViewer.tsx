interface Props {
  content: unknown
  isJson?: boolean
}

export default function TextViewer({ content, isJson }: Props) {
  const text = isJson
    ? JSON.stringify(content, null, 2)
    : String(content ?? '')

  return (
    <pre className="text-xs leading-relaxed bg-muted rounded-lg p-4 overflow-auto whitespace-pre-wrap break-words text-foreground font-mono">
      {text}
    </pre>
  )
}
