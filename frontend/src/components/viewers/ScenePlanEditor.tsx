import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Scene, SceneBeat } from '@/api/tasks'
import { AutoTextarea, SaveFooter } from './ResearchEditor'

const BEAT_FIELDS: { key: keyof SceneBeat; label: string; numeric?: boolean }[] = [
  { key: 'narration', label: 'Narration' },
  { key: 'duration',  label: 'Duration (in seconds)', numeric: true },
  { key: 'visual',    label: 'Visual'    },
  { key: 'purpose',   label: 'Purpose'   },
  { key: 'emotion',   label: 'Emotion'   },
]

function extractNum(v: string): string {
  const m = v.match(/(\d+(?:\.\d+)?)/)
  return m ? m[1] : v
}

interface Props {
  scenes: Scene[]
  onSave: (scenes: Scene[]) => Promise<void>
}

export default function ScenePlanEditor({ scenes: initial, onSave }: Props) {
  const [scenes, setScenes] = useState<Scene[]>(initial)
  const [dirty, setDirty]   = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)

  const [expandedScenes, setExpandedScenes] = useState<Set<number>>(() => new Set([0]))
  const [expandedBeats, setExpandedBeats]   = useState<Set<string>>(() => new Set())

  useEffect(() => {
    setScenes(initial)
    setDirty(false)
    setSaved(false)
    setExpandedScenes(new Set([0]))
    setExpandedBeats(new Set())
  }, [initial])

  function toggleScene(si: number) {
    setExpandedScenes(prev => {
      const n = new Set(prev)
      n.has(si) ? n.delete(si) : n.add(si)
      return n
    })
  }

  function toggleBeat(key: string) {
    setExpandedBeats(prev => {
      const n = new Set(prev)
      n.has(key) ? n.delete(key) : n.add(key)
      return n
    })
  }

  function updateBeat(si: number, bi: number, key: keyof SceneBeat, value: string) {
    setScenes(prev => prev.map((scene, s) =>
      s !== si ? scene : {
        ...scene,
        beats: scene.beats.map((beat, b) =>
          b !== bi ? beat : { ...beat, [key]: value }
        ),
      }
    ))
    setDirty(true)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await onSave(scenes)
      setDirty(false)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  if (scenes.length === 0) {
    return <p className="text-sm text-muted-foreground">No content yet.</p>
  }

  return (
    <div className="space-y-2">
      {scenes.map((scene, si) => {
        const sceneOpen = expandedScenes.has(si)
        return (
          <div key={scene.id} className="border rounded-lg overflow-hidden">
            {/* Scene header */}
            <button
              onClick={() => toggleScene(si)}
              className="w-full flex items-center justify-between px-4 py-2.5 bg-muted/40 hover:bg-muted/70 transition-colors text-left"
            >
              <span className="text-xs font-bold uppercase tracking-widest text-foreground">
                Scene {scene.id}
                <span className="ml-2 font-normal text-muted-foreground normal-case tracking-normal">
                  {scene.beats.length} asset{scene.beats.length !== 1 ? 's' : ''}
                </span>
              </span>
              {sceneOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
            </button>

            {sceneOpen && (
              <div className="p-3 space-y-2">
                {scene.beats.map((beat, bi) => {
                  const beatKey = `${si}-${bi}`
                  const beatOpen = expandedBeats.has(beatKey)
                  const assetId = `${scene.id}.${bi + 1}`
                  const preview = beat.narration
                    ? beat.narration.slice(0, 60) + (beat.narration.length > 60 ? '…' : '')
                    : ''

                  return (
                    <div key={bi} className="border rounded-md overflow-hidden">
                      {/* Beat header */}
                      <button
                        onClick={() => toggleBeat(beatKey)}
                        className="w-full flex items-center justify-between px-3 py-2 bg-background hover:bg-muted/50 transition-colors text-left"
                      >
                        <span className="flex items-center gap-2 min-w-0">
                          <span className="text-[11px] font-semibold text-muted-foreground shrink-0">
                            Asset {assetId}
                          </span>
                          {preview && (
                            <span className="text-xs text-foreground truncate">
                              {preview}
                            </span>
                          )}
                        </span>
                        {beatOpen
                          ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
                          : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />}
                      </button>

                      {beatOpen && (
                        <div className="px-3 py-3 space-y-3 border-t">
                          {BEAT_FIELDS.map(({ key, label, numeric }) => (
                            <div key={key} className="space-y-1">
                              <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">
                                {label}
                              </p>
                              {numeric ? (
                                <input
                                  type="number"
                                  min="0"
                                  value={extractNum(beat[key])}
                                  onChange={e => updateBeat(si, bi, key, e.target.value)}
                                  className="w-24 text-sm rounded-md border border-input bg-transparent px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
                                />
                              ) : (
                                <AutoTextarea
                                  value={beat[key]}
                                  onChange={v => updateBeat(si, bi, key, v)}
                                />
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
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
