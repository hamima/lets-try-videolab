import { useState } from 'react'
import { ChevronDown, ChevronRight, Film, Image as ImageIcon, Type, Volume2 } from 'lucide-react'

interface ClipEffects {
  ken_burns?: { direction: string; intensity: number } | null
  speed?: number
  zoom_punch?: { at_sec: number; scale: number; duration_sec: number } | null
  transition_out?: string
}

interface Clip {
  path: string | null
  type: 'video' | 'image' | 'placeholder'
  trim_start_sec?: number
  trim_end_sec?: number
  duration_sec: number
  effects?: ClipEffects
}

interface TextOverlay {
  text: string
  start_sec: number
  end_sec: number
  style: string
  animation: string
}

interface Sfx {
  name: string
  at_sec: number
  volume: number
}

interface TimelineScene {
  scene_id: number
  start_time_sec: number
  duration_sec: number
  clips: Clip[]
  text_overlays: TextOverlay[]
  sfx: Sfx[]
  reasoning?: string
}

export interface EditDecisionList {
  project: {
    resolution: string
    fps: number
    total_duration_sec: number
    edl_version?: number
  }
  timeline: TimelineScene[]
}

interface Props {
  data: EditDecisionList
}

const SCENE_COLORS = [
  'bg-blue-400', 'bg-emerald-400', 'bg-amber-400', 'bg-purple-400', 'bg-pink-400', 'bg-cyan-400',
]

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function clipLabel(clip: Clip): string {
  if (!clip.path) return 'Placeholder'
  const parts = clip.path.split('/')
  return parts.slice(-2).join('/')
}

export default function EditDecisionListViewer({ data }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(
    () => new Set(data.timeline[0] ? [data.timeline[0].scene_id] : []),
  )

  if (!data?.timeline?.length) {
    return <p className="text-sm text-muted-foreground">No edit decision list yet.</p>
  }

  function toggle(id: number) {
    setExpanded((prev) => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }

  return (
    <div className="space-y-4">
      {/* Project summary */}
      <div className="flex gap-8">
        <div>
          <p className="text-xs text-muted-foreground">Total duration</p>
          <p className="text-lg font-semibold">{formatTime(data.project.total_duration_sec)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Resolution</p>
          <p className="text-lg font-semibold">{data.project.resolution}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Scenes</p>
          <p className="text-lg font-semibold">{data.timeline.length}</p>
        </div>
      </div>

      {/* Proportional timeline bar */}
      <div className="flex h-8 rounded-md overflow-hidden border">
        {data.timeline.map((scene, i) => (
          <div
            key={scene.scene_id}
            title={`Scene ${scene.scene_id}: ${formatTime(scene.start_time_sec)}–${formatTime(scene.start_time_sec + scene.duration_sec)} (${scene.duration_sec.toFixed(1)}s)`}
            className={`${SCENE_COLORS[i % SCENE_COLORS.length]} flex items-center justify-center text-[10px] font-semibold text-white border-r border-white/30 last:border-r-0`}
            style={{ width: `${(scene.duration_sec / data.project.total_duration_sec) * 100}%` }}
          >
            {scene.duration_sec / data.project.total_duration_sec > 0.035 ? scene.scene_id : ''}
          </div>
        ))}
      </div>

      {/* Scene breakdown */}
      <div className="space-y-2">
        {data.timeline.map((scene, i) => {
          const open = expanded.has(scene.scene_id)
          return (
            <div key={scene.scene_id} className="border rounded-lg overflow-hidden">
              <button
                onClick={() => toggle(scene.scene_id)}
                className="w-full flex items-center gap-3 px-4 py-2.5 bg-muted/40 hover:bg-muted/70 transition-colors text-left"
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${SCENE_COLORS[i % SCENE_COLORS.length]}`} />
                <span className="text-xs font-bold uppercase tracking-widest text-foreground shrink-0">
                  Scene {scene.scene_id}
                </span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {formatTime(scene.start_time_sec)} – {formatTime(scene.start_time_sec + scene.duration_sec)}
                </span>
                <span className="text-xs font-medium shrink-0">{scene.duration_sec.toFixed(1)}s</span>
                <span className="text-xs text-muted-foreground ml-auto shrink-0">
                  {scene.clips.length} clip{scene.clips.length !== 1 ? 's' : ''}
                </span>
                {open ? (
                  <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                )}
              </button>

              {open && (
                <div className="p-4 space-y-4">
                  {scene.reasoning && (
                    <p className="text-xs text-muted-foreground italic leading-relaxed border-l-2 pl-3">
                      {scene.reasoning}
                    </p>
                  )}

                  {/* Clips */}
                  <div className="space-y-1.5">
                    <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Clips</p>
                    {scene.clips.map((clip, idx) => (
                      <div key={idx} className="flex items-center gap-2 text-xs py-1.5 px-2.5 rounded-md bg-muted/30">
                        {clip.type === 'video' ? (
                          <Film className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                        ) : clip.type === 'image' ? (
                          <ImageIcon className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                        ) : (
                          <span className="w-3.5 h-3.5 shrink-0 rounded-sm border border-dashed" />
                        )}
                        <span className="font-mono truncate">{clipLabel(clip)}</span>
                        <span className="text-muted-foreground ml-auto shrink-0">{clip.duration_sec.toFixed(1)}s</span>
                        {clip.effects?.ken_burns && (
                          <span className="shrink-0 px-1.5 py-0.5 rounded-full bg-background border text-muted-foreground">
                            {clip.effects.ken_burns.direction.replace('_', ' ')}
                          </span>
                        )}
                        {clip.effects?.zoom_punch && (
                          <span className="shrink-0 px-1.5 py-0.5 rounded-full bg-background border text-muted-foreground">
                            zoom punch
                          </span>
                        )}
                        {clip.effects?.speed !== undefined && clip.effects.speed !== 1.0 && (
                          <span className="shrink-0 px-1.5 py-0.5 rounded-full bg-background border text-muted-foreground">
                            {clip.effects.speed}x
                          </span>
                        )}
                        {clip.effects?.transition_out && (
                          <span className="shrink-0 px-1.5 py-0.5 rounded-full bg-background border text-muted-foreground">
                            {clip.effects.transition_out}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* Text overlays */}
                  {scene.text_overlays.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Text overlays</p>
                      {scene.text_overlays.map((t, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs py-1.5 px-2.5 rounded-md bg-muted/30">
                          <Type className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                          <span className="font-medium truncate">"{t.text}"</span>
                          <span className="text-muted-foreground ml-auto shrink-0">
                            {t.start_sec.toFixed(1)}s–{t.end_sec.toFixed(1)}s
                          </span>
                          <span className="shrink-0 px-1.5 py-0.5 rounded-full bg-background border text-muted-foreground">
                            {t.style.replace(/_/g, ' ')}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* SFX */}
                  {scene.sfx.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">Sound effects</p>
                      {scene.sfx.map((s, idx) => (
                        <div key={idx} className="flex items-center gap-2 text-xs py-1.5 px-2.5 rounded-md bg-muted/30">
                          <Volume2 className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                          <span className="font-medium">{s.name.replace(/_/g, ' ')}</span>
                          <span className="text-muted-foreground ml-auto shrink-0">at {s.at_sec.toFixed(1)}s</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
