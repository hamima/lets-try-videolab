import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { saveAssetFiles } from '@/api/tasks'
import { AutoTextarea } from './ResearchEditor'
import { Button } from '@/components/ui/button'

interface AnimationItem {
  path: string
  text: string
  label: string
  scene_id: string
  asset_id: string
  image_url: string | null
}

interface Props {
  items: AnimationItem[]
  domain: string
  runId: string
}

// Group flat item list into scenes → assets
function groupItems(items: AnimationItem[]) {
  const sceneMap = new Map<string, Map<string, AnimationItem>>()
  for (const item of items) {
    if (!sceneMap.has(item.scene_id)) sceneMap.set(item.scene_id, new Map())
    sceneMap.get(item.scene_id)!.set(item.asset_id, item)
  }
  return Array.from(sceneMap.entries()).map(([scene_id, assetMap]) => ({
    scene_id,
    assets: Array.from(assetMap.entries()).map(([asset_id, item]) => ({ asset_id, item })),
  }))
}

// ─── Editable animation prompt card ─────────────────────────────────────────────

function AnimationPromptCard({
  item,
  domain,
  runId,
}: {
  item: AnimationItem
  domain: string
  runId: string
}) {
  const [text, setText] = useState(item.text)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  function handleChange(v: string) {
    setText(v)
    setDirty(true)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await saveAssetFiles(domain, runId, item.scene_id, item.asset_id, [
        { filename: 'animated.txt', content: text },
      ])
      setDirty(false)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex gap-4">
      {item.image_url ? (
        <img
          src={item.image_url}
          alt={item.label}
          className="w-40 h-40 shrink-0 rounded-md border object-cover bg-muted/20"
        />
      ) : (
        <div className="w-40 h-40 shrink-0 rounded-md border border-dashed flex items-center justify-center text-muted-foreground text-xs">
          No image
        </div>
      )}

      <div className="flex-1 min-w-0 space-y-2">
        <AutoTextarea value={text} onChange={handleChange} />
        <div className="flex items-center gap-3">
          <Button size="sm" disabled={!dirty || saving} onClick={handleSave}>
            {saving ? 'Saving…' : saved && !dirty ? 'Saved' : 'Save'}
          </Button>
          {saved && !dirty && <span className="text-xs text-emerald-600">Changes saved</span>}
        </div>
      </div>
    </div>
  )
}

// ─── Main viewer ───────────────────────────────────────────────────────────────

export default function AnimationPromptViewer({ items, domain, runId }: Props) {
  const scenes = groupItems(items)
  const [expandedScenes, setExpandedScenes] = useState<Set<string>>(
    () => new Set(scenes[0] ? [scenes[0].scene_id] : []),
  )

  if (scenes.length === 0) {
    return <p className="text-sm text-muted-foreground">No animation prompts yet.</p>
  }

  function toggleScene(id: string) {
    setExpandedScenes((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  return (
    <div className="space-y-2">
      {scenes.map(({ scene_id, assets }) => {
        const open = expandedScenes.has(scene_id)
        return (
          <div key={scene_id} className="border rounded-lg overflow-hidden">
            <button
              onClick={() => toggleScene(scene_id)}
              className="w-full flex items-center justify-between px-4 py-2.5 bg-muted/40 hover:bg-muted/70 transition-colors text-left"
            >
              <span className="text-xs font-bold uppercase tracking-widest text-foreground">
                Scene {scene_id}
                <span className="ml-2 font-normal text-muted-foreground normal-case tracking-normal">
                  {assets.length} asset{assets.length !== 1 ? 's' : ''}
                </span>
              </span>
              {open ? (
                <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
              ) : (
                <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
              )}
            </button>

            {open && (
              <div className="p-4 space-y-4">
                {assets.map(({ asset_id, item }) => (
                  <div key={asset_id}>
                    <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
                      Asset {asset_id}
                    </p>
                    <AnimationPromptCard item={item} domain={domain} runId={runId} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
