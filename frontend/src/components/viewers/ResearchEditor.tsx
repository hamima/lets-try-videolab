import { useEffect, useRef, useState } from 'react'
import type { ResearchSection } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'

// ─── Auto-growing textarea ────────────────────────────────────────────────────

export function AutoTextarea({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = 'auto'
      ref.current.style.height = ref.current.scrollHeight + 'px'
    }
  }, [value])

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full resize-none text-sm leading-relaxed bg-transparent border border-input rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-ring overflow-hidden"
      style={{ minHeight: 40 }}
    />
  )
}

// ─── Save footer (shared) ─────────────────────────────────────────────────────

export function SaveFooter({
  dirty,
  saving,
  saved,
  onSave,
}: {
  dirty: boolean
  saving: boolean
  saved: boolean
  onSave: () => void
}) {
  return (
    <>
      <Separator />
      <div className="flex items-center justify-end gap-3 pb-2">
        {saved && !dirty && <span className="text-xs text-emerald-600">Saved</span>}
        <Button size="sm" onClick={onSave} disabled={!dirty || saving}>
          {saving ? 'Saving…' : 'Save Changes'}
        </Button>
      </div>
    </>
  )
}

// ─── Research / Story editor ──────────────────────────────────────────────────

interface Props {
  sections: ResearchSection[]
  onSave: (sections: ResearchSection[]) => Promise<void>
}

export default function ResearchEditor({ sections: initial, onSave }: Props) {
  const [sections, setSections] = useState<ResearchSection[]>(initial)
  const [dirty, setDirty]   = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)

  useEffect(() => {
    setSections(initial)
    setDirty(false)
    setSaved(false)
  }, [initial])

  function update(idx: number, content: string) {
    setSections(prev => prev.map((s, i) => i === idx ? { ...s, content } : s))
    setDirty(true)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await onSave(sections)
      setDirty(false)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  if (sections.length === 0) {
    return <p className="text-sm text-muted-foreground">No content yet.</p>
  }

  return (
    <div className="space-y-5">
      {sections.map((section, idx) => (
        <div key={idx} className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">
            {section.label}
          </p>
          <AutoTextarea value={section.content} onChange={v => update(idx, v)} />
        </div>
      ))}
      <SaveFooter dirty={dirty} saving={saving} saved={saved} onSave={handleSave} />
    </div>
  )
}
