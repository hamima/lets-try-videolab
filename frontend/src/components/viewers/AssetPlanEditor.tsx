import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { AssetScene } from '@/api/tasks'
import { AutoTextarea, SaveFooter } from './ResearchEditor'

// ─── Selector fields ──────────────────────────────────────────────────────────

const FIELD_OPTIONS: Record<string, string[]> = {
  ASSET_TYPE: ['ai_image', 'stock_video', 'editorial_video', 'photo', 'chart', 'map'],
  KEN_BURNS:  ['zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'N/A'],
  PRIORITY:   ['Critical', 'Optional'],
}

const NUMERIC_FIELDS = new Set(['DURATION'])

function extractNum(v: string): string {
  const m = v.match(/(\d+(?:\.\d+)?)/)
  return m ? m[1] : v
}

function SelectField({ value, options, onChange }: { value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-full text-sm rounded-md border border-input bg-transparent px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
    >
      {options.map(o => <option key={o} value={o}>{o}</option>)}
      {/* Keep current value even if it's not in the list */}
      {value && !options.includes(value) && <option value={value}>{value}</option>}
    </select>
  )
}

interface Props {
  scenes: AssetScene[]
  onSave: (scenes: AssetScene[]) => Promise<void>
}

export default function AssetPlanEditor({ scenes: initial, onSave }: Props) {
  const [scenes, setScenes] = useState<AssetScene[]>(initial)
  const [dirty, setDirty]   = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)

  // Track expanded state for scenes and assets separately
  const [expandedScenes, setExpandedScenes]   = useState<Set<number>>(() => new Set([0]))
  const [expandedAssets, setExpandedAssets]   = useState<Set<string>>(() => new Set())

  useEffect(() => {
    setScenes(initial)
    setDirty(false)
    setSaved(false)
    setExpandedScenes(new Set([0]))
    setExpandedAssets(new Set())
  }, [initial])

  function toggleScene(si: number) {
    setExpandedScenes(prev => {
      const n = new Set(prev)
      n.has(si) ? n.delete(si) : n.add(si)
      return n
    })
  }

  function toggleAsset(key: string) {
    setExpandedAssets(prev => {
      const n = new Set(prev)
      n.has(key) ? n.delete(key) : n.add(key)
      return n
    })
  }

  function updateField(si: number, ai: number, fi: number, value: string) {
    setScenes(prev => prev.map((scene, s) =>
      s !== si ? scene : {
        ...scene,
        assets: scene.assets.map((asset, a) =>
          a !== ai ? asset : {
            ...asset,
            fields: asset.fields.map((f, i) =>
              i !== fi ? f : { ...f, content: value }
            ),
          }
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
                  {scene.assets.length} asset{scene.assets.length !== 1 ? 's' : ''}
                </span>
              </span>
              {sceneOpen
                ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
                : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
            </button>

            {sceneOpen && (
              <div className="p-3 space-y-2">
                {scene.assets.map((asset, ai) => {
                  const assetKey = `${si}-${ai}`
                  const assetOpen = expandedAssets.has(assetKey)
                  const typeField = asset.fields.find(f => f.label === 'ASSET_TYPE' || f.label === 'TYPE')
                  const assetType = typeField?.content ?? ''
                  return (
                    <div key={asset.id} className="border rounded-md overflow-hidden">
                      {/* Asset header */}
                      <button
                        onClick={() => toggleAsset(assetKey)}
                        className="w-full flex items-center justify-between px-3 py-2 bg-background hover:bg-muted/50 transition-colors text-left"
                      >
                        <span className="flex items-center gap-1.5 min-w-0">
                          <span className="text-xs font-semibold text-foreground shrink-0">
                            Asset {asset.id}
                          </span>
                          {assetType && (
                            <span className="text-xs text-muted-foreground">: {assetType}</span>
                          )}
                        </span>
                        {assetOpen
                          ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
                          : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />}
                      </button>

                      {assetOpen && (
                        <div className="px-3 py-3 space-y-3 border-t">
                          {asset.fields.map((field, fi) => {
                            const options = FIELD_OPTIONS[field.label]
                            const isNumeric = NUMERIC_FIELDS.has(field.label)
                            const displayLabel = isNumeric ? `${field.label} (in seconds)` : field.label
                            return (
                              <div key={fi} className="space-y-1">
                                <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">
                                  {displayLabel}
                                </p>
                                {options ? (
                                  <SelectField
                                    value={field.content}
                                    options={options}
                                    onChange={v => updateField(si, ai, fi, v)}
                                  />
                                ) : isNumeric ? (
                                  <input
                                    type="number"
                                    min="0"
                                    value={extractNum(field.content)}
                                    onChange={e => updateField(si, ai, fi, e.target.value)}
                                    className="w-24 text-sm rounded-md border border-input bg-transparent px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
                                  />
                                ) : (
                                  <AutoTextarea
                                    value={field.content}
                                    onChange={v => updateField(si, ai, fi, v)}
                                  />
                                )}
                              </div>
                            )
                          })}
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
