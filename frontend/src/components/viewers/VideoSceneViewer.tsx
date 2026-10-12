import { useState } from 'react'
import { ChevronDown, ChevronRight, Loader2, Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { animateAsset } from '@/api/tasks'

interface VideoItem {
  scene_id: string
  asset_id: string
  label: string
  thumbnail_url: string | null
  video_url: string | null
  status: 'done' | 'pending'
}

interface Props {
  videos: VideoItem[]
  domain: string
  runId: string
}

// Group flat asset list into scenes → assets
function groupVideos(videos: VideoItem[]) {
  const sceneMap = new Map<string, Map<string, VideoItem>>()
  for (const v of videos) {
    if (!sceneMap.has(v.scene_id)) sceneMap.set(v.scene_id, new Map())
    sceneMap.get(v.scene_id)!.set(v.asset_id, v)
  }
  return Array.from(sceneMap.entries()).map(([scene_id, assetMap]) => ({
    scene_id,
    assets: Array.from(assetMap.entries()).map(([asset_id, item]) => ({ asset_id, item })),
  }))
}

// ─── Asset video card ───────────────────────────────────────────────────────

function AssetVideoCard({
  item,
  domain,
  runId,
}: {
  item: VideoItem
  domain: string
  runId: string
}) {
  const [videoUrl, setVideoUrl] = useState(item.video_url)
  const [animating, setAnimating] = useState(false)

  async function handleAnimate() {
    setAnimating(true)
    try {
      const res = await animateAsset(domain, runId, item.scene_id, item.asset_id)
      setVideoUrl(res.url + '?t=' + Date.now())
    } finally {
      setAnimating(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-md overflow-hidden border bg-muted aspect-video">
          {item.thumbnail_url ? (
            <img src={item.thumbnail_url} alt={item.label} className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">
              No source
            </div>
          )}
        </div>
        <div className="rounded-md overflow-hidden border bg-muted aspect-video flex items-center justify-center">
          {videoUrl ? (
            <video controls className="w-full h-full object-cover" src={videoUrl}>
              Your browser does not support the video element.
            </video>
          ) : (
            <span className="text-xs text-muted-foreground px-2 text-center">Not animated yet</span>
          )}
        </div>
      </div>
      <Button
        size="sm"
        variant="outline"
        className="gap-1.5"
        disabled={animating}
        onClick={handleAnimate}
      >
        {animating ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : videoUrl ? (
          <RefreshCw className="w-3.5 h-3.5" />
        ) : (
          <Play className="w-3.5 h-3.5" />
        )}
        {animating ? 'Animating…' : videoUrl ? 'Re-animate' : 'Animate'}
      </Button>
    </div>
  )
}

// ─── Main viewer ───────────────────────────────────────────────────────────────

export default function VideoSceneViewer({ videos, domain, runId }: Props) {
  const scenes = groupVideos(videos)
  const [expandedScenes, setExpandedScenes] = useState<Set<string>>(
    () => new Set(scenes[0] ? [scenes[0].scene_id] : []),
  )

  if (scenes.length === 0) {
    return <p className="text-sm text-muted-foreground">No assets ready to animate yet.</p>
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
                {assets.map(({ asset_id, item }) => (
                  <div key={asset_id}>
                    <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground mb-2">
                      Asset {asset_id}
                    </p>
                    <AssetVideoCard item={item} domain={domain} runId={runId} />
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
