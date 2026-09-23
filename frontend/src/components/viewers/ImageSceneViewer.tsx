import { useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { regenerateAssetImage } from '@/api/tasks'

interface ImageItem {
  path: string
  url: string
  label: string
  scene_id: string
  asset_id: string
  filename: string
}

interface Props {
  images: ImageItem[]
  domain: string
  runId: string
}

// Group flat image list into scenes → assets
function groupImages(images: ImageItem[]) {
  const sceneMap = new Map<string, Map<string, ImageItem>>()
  for (const img of images) {
    if (!sceneMap.has(img.scene_id)) sceneMap.set(img.scene_id, new Map())
    sceneMap.get(img.scene_id)!.set(img.asset_id, img)
  }
  return Array.from(sceneMap.entries()).map(([scene_id, assetMap]) => ({
    scene_id,
    assets: Array.from(assetMap.entries()).map(([asset_id, img]) => ({ asset_id, img })),
  }))
}

// ─── Lightbox ─────────────────────────────────────────────────────────────────

function Lightbox({ url, label, onClose }: { url: string; label: string; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <button className="absolute top-4 right-4 text-white/70 hover:text-white" onClick={onClose}>
        <X className="w-6 h-6" />
      </button>
      <img
        src={url}
        alt={label}
        className="max-w-full max-h-full rounded-lg object-contain"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}

// ─── Asset image card ──────────────────────────────────────────────────────────

function AssetImageCard({
  item,
  domain,
  runId,
}: {
  item: ImageItem
  domain: string
  runId: string
}) {
  const [url, setUrl] = useState(item.url)
  const [regenerating, setRegenerating] = useState(false)
  const [lightbox, setLightbox] = useState(false)

  async function handleRegenerate(e: React.MouseEvent) {
    e.stopPropagation()
    setRegenerating(true)
    try {
      const res = await regenerateAssetImage(domain, runId, item.scene_id, item.asset_id)
      setUrl(res.url + '?t=' + Date.now())
    } finally {
      setRegenerating(false)
    }
  }

  return (
    <>
      <div className="space-y-2">
        <div
          className="relative rounded-md overflow-hidden border bg-muted cursor-zoom-in aspect-video"
          onClick={() => setLightbox(true)}
        >
          <img
            src={url}
            alt={item.label}
            className="w-full h-full object-cover"
            onError={(e) => {
              ;(e.target as HTMLImageElement).src =
                'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="%23e5e7eb"/></svg>'
            }}
          />
        </div>
        <Button
          size="sm"
          variant="outline"
          className="gap-1.5"
          disabled={regenerating}
          onClick={handleRegenerate}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${regenerating ? 'animate-spin' : ''}`} />
          {regenerating ? 'Regenerating…' : 'Regenerate'}
        </Button>
      </div>

      {lightbox && <Lightbox url={url} label={item.label} onClose={() => setLightbox(false)} />}
    </>
  )
}

// ─── Main viewer ───────────────────────────────────────────────────────────────

export default function ImageSceneViewer({ images, domain, runId }: Props) {
  const scenes = groupImages(images)
  const [expandedScenes, setExpandedScenes] = useState<Set<string>>(
    () => new Set(scenes[0] ? [scenes[0].scene_id] : []),
  )

  if (scenes.length === 0) {
    return <p className="text-sm text-muted-foreground">No images generated yet.</p>
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
              <div className="p-4 grid grid-cols-2 gap-4">
                {assets.map(({ asset_id, img }) => (
                  <div key={asset_id}>
                    <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
                      Asset {asset_id}
                    </p>
                    <AssetImageCard item={img} domain={domain} runId={runId} />
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
