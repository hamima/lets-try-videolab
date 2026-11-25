import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { SubtitleCaption } from '@/api/tasks'
import { AutoTextarea, SaveFooter } from './ResearchEditor'

// ─── Timestamp formatting (matches backend/subtitles.py's HH:MM:SS,mmm) ────────

function formatTimestamp(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  const ms = Math.round((seconds - whole) * 1000)
  const h = Math.floor(whole / 3600)
  const m = Math.floor((whole % 3600) / 60)
  const s = whole % 60
  const pad = (n: number, len = 2) => String(n).padStart(len, '0')
  return `${pad(h)}:${pad(m)}:${pad(s)},${pad(ms, 3)}`
}

interface Props {
  captions: SubtitleCaption[]
  onSave: (captions: SubtitleCaption[]) => Promise<void>
}

export default function SubtitleEditor({ captions: initial, onSave }: Props) {
  const [captions, setCaptions] = useState<SubtitleCaption[]>(initial)
  const [dirty, setDirty]   = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)

  const [expandedScenes, setExpandedScenes] = useState<Set<number>>(() => new Set([0]))

  useEffect(() => {
    setCaptions(initial)
    setDirty(false)
    setSaved(false)
    setExpandedScenes(new Set([0]))
  }, [initial])

  // Group the flat caption list by scene_id, preserving first-seen order.
  const scenes = useMemo(() => {
    const order: number[] = []
    const byScene = new Map<number, { caption: SubtitleCaption; index: number }[]>()
    captions.forEach((caption, index) => {
      if (!byScene.has(caption.scene_id)) {
        byScene.set(caption.scene_id, [])
        order.push(caption.scene_id)
      }
      byScene.get(caption.scene_id)!.push({ caption, index })
    })
    return order.map(sceneId => ({ sceneId, entries: byScene.get(sceneId)! }))
  }, [captions])

  function toggleScene(sceneIndex: number) {
    setExpandedScenes(prev => {
      const n = new Set(prev)
      n.has(sceneIndex) ? n.delete(sceneIndex) : n.add(sceneIndex)
      return n
    })
  }

  function updateCaption(index: number, patch: Partial<SubtitleCaption>) {
    setCaptions(prev => prev.map((c, i) => (i === index ? { ...c, ...patch } : c)))
    setDirty(true)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await onSave(captions)
      setDirty(false)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  if (captions.length === 0) {
    return <p className="text-sm text-muted-foreground">No content yet.</p>
  }

  return (
    <div className="space-y-2">
      {scenes.map((scene, si) => {
        const sceneOpen = expandedScenes.has(si)
        return (
          <div key={scene.sceneId} className="border rounded-lg overflow-hidden">
            <button
              onClick={() => toggleScene(si)}
              className="w-full flex items-center justify-between px-4 py-2.5 bg-muted/40 hover:bg-muted/70 transition-colors text-left"
            >
              <span className="text-xs font-bold uppercase tracking-widest text-foreground">
                Scene {scene.sceneId}
                <span className="ml-2 font-normal text-muted-foreground normal-case tracking-normal">
                  {scene.entries.length} caption{scene.entries.length !== 1 ? 's' : ''}
                </span>
              </span>
              {sceneOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
            </button>

            {sceneOpen && (
              <div className="p-3 space-y-3">
                {scene.entries.map(({ caption, index }) => (
                  <div key={index} className="border rounded-md p-3 space-y-2">
                    <div className="flex items-center gap-3">
                      <div className="space-y-1">
                        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">Start (sec)</p>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={caption.start_sec}
                          onChange={e => updateCaption(index, { start_sec: Number(e.target.value) })}
                          className="w-28 text-sm rounded-md border border-input bg-transparent px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
                        />
                        <p className="text-[11px] text-muted-foreground">{formatTimestamp(caption.start_sec)}</p>
                      </div>
                      <div className="space-y-1">
                        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">End (sec)</p>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={caption.end_sec}
                          onChange={e => updateCaption(index, { end_sec: Number(e.target.value) })}
                          className="w-28 text-sm rounded-md border border-input bg-transparent px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
                        />
                        <p className="text-[11px] text-muted-foreground">{formatTimestamp(caption.end_sec)}</p>
                      </div>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">Text</p>
                      <AutoTextarea value={caption.text} onChange={v => updateCaption(index, { text: v })} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}

      <div className="pt-2">
        <SaveFooter dirty={dirty} saving={saving} saved={saved} onSave={handleSave} />
      </div>
    </div>
  )
}
