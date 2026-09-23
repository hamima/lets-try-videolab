import { useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Upload } from 'lucide-react'
import type { AssetFile, AssetFolderScene } from '@/api/tasks'
import { saveAssetFiles, uploadAssetImage } from '@/api/tasks'
import { AutoTextarea } from './ResearchEditor'
import { Button } from '@/components/ui/button'

// ─── Single asset card ─────────────────────────────────────────────────────────

interface AssetCardProps {
  sceneId: string
  assetId: string
  domain: string
  runId: string
  initialFiles: AssetFile[]
}

function AssetCard({ sceneId, assetId, domain, runId, initialFiles }: AssetCardProps) {
  const [files, setFiles]   = useState<AssetFile[]>(initialFiles)
  const [dirty, setDirty]   = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved]   = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function updateText(filename: string, content: string) {
    setFiles(prev => prev.map(f => f.filename === filename ? { ...f, content } : f))
    setDirty(true)
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    try {
      const textFiles = files
        .filter(f => f.type === 'text' && f.content !== undefined)
        .map(f => ({ filename: f.filename, content: f.content! }))
      await saveAssetFiles(domain, runId, sceneId, assetId, textFiles)
      setDirty(false)
      setSaved(true)
    } finally {
      setSaving(false)
    }
  }

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setSaving(true)
    try {
      const res = await uploadAssetImage(domain, runId, sceneId, assetId, file)
      setFiles(prev => prev.map(f =>
        f.type === 'image' ? { ...f, url: res.url + '?t=' + Date.now() } : f
      ))
    } finally {
      setSaving(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  return (
    <div className="space-y-4">
      {files.map(f => (
        <div key={f.filename} className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground select-none">
            {f.label}
          </p>

          {f.type === 'image' ? (
            <div className="space-y-2">
              {f.url ? (
                <img
                  src={f.url}
                  alt={f.label}
                  className="max-h-56 rounded-md border object-contain bg-muted/20"
                />
              ) : (
                <div className="h-32 rounded-md border border-dashed flex items-center justify-center text-muted-foreground text-sm">
                  No image
                </div>
              )}
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleImageUpload}
                />
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={saving}
                >
                  <Upload className="w-3.5 h-3.5" />
                  Upload image
                </Button>
              </div>
            </div>
          ) : (
            <AutoTextarea
              value={f.content ?? ''}
              onChange={v => updateText(f.filename, v)}
            />
          )}
        </div>
      ))}

      {/* Save footer — only shown when there are editable text files */}
      {files.some(f => f.type === 'text') && (
        <div className="flex items-center gap-3 pt-1">
          <Button
            size="sm"
            disabled={!dirty || saving}
            onClick={handleSave}
          >
            {saving ? 'Saving…' : saved && !dirty ? 'Saved' : 'Save'}
          </Button>
          {saved && !dirty && (
            <span className="text-xs text-emerald-600">Changes saved</span>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Main viewer ───────────────────────────────────────────────────────────────

interface Props {
  scenes: AssetFolderScene[]
  domain: string
  runId: string
}

export default function AssetFolderViewer({ scenes, domain, runId }: Props) {
  const [expandedScenes, setExpandedScenes] = useState<Set<string>>(() => new Set(scenes[0] ? [scenes[0].id] : []))
  const [expandedAssets, setExpandedAssets] = useState<Set<string>>(() => new Set())

  function toggleScene(id: string) {
    setExpandedScenes(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
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

  if (scenes.length === 0) {
    return <p className="text-sm text-muted-foreground">No assets yet.</p>
  }

  return (
    <div className="space-y-2">
      {scenes.map(scene => {
        const sceneOpen = expandedScenes.has(scene.id)
        return (
          <div key={scene.id} className="border rounded-lg overflow-hidden">
            {/* Scene header */}
            <button
              onClick={() => toggleScene(scene.id)}
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
                {scene.assets.map(asset => {
                  const assetKey = `${scene.id}-${asset.id}`
                  const assetOpen = expandedAssets.has(assetKey)
                  const imageFile = asset.files.find(f => f.type === 'image')

                  return (
                    <div key={asset.id} className="border rounded-md overflow-hidden">
                      {/* Asset header */}
                      <button
                        onClick={() => toggleAsset(assetKey)}
                        className="w-full flex items-center justify-between px-3 py-2 bg-background hover:bg-muted/50 transition-colors text-left"
                      >
                        <span className="flex items-center gap-2 min-w-0">
                          <span className="text-xs font-semibold text-foreground shrink-0">
                            Asset {asset.id}
                          </span>
                          {imageFile && !assetOpen && (
                            <span className="text-xs text-muted-foreground">· image</span>
                          )}
                          <span className="text-xs text-muted-foreground truncate">
                            {asset.files.map(f => f.label).join(', ')}
                          </span>
                        </span>
                        {assetOpen
                          ? <ChevronDown className="w-3 h-3 text-muted-foreground shrink-0" />
                          : <ChevronRight className="w-3 h-3 text-muted-foreground shrink-0" />}
                      </button>

                      {assetOpen && (
                        <div className="px-4 py-4 border-t">
                          <AssetCard
                            sceneId={scene.id}
                            assetId={asset.id}
                            domain={domain}
                            runId={runId}
                            initialFiles={asset.files}
                          />
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
    </div>
  )
}
