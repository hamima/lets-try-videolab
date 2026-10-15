import { useState } from 'react'

interface Pause {
  start: number
  end: number
  duration: number
}

interface TimingScene {
  scene_id: number
  start_sec: number
  end_sec: number
  duration_sec: number
  internal_pauses: Pause[]
  pause_count: number
}

export interface NarrationTiming {
  total_duration_sec: number
  scene_count: number
  scenes: TimingScene[]
}

interface Props {
  data: NarrationTiming
}

const SCENE_COLORS = [
  'bg-blue-400', 'bg-emerald-400', 'bg-amber-400', 'bg-purple-400', 'bg-pink-400', 'bg-cyan-400',
]

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function NarrationTimingViewer({ data }: Props) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set())

  if (!data?.scenes?.length) {
    return <p className="text-sm text-muted-foreground">No narration timing data yet.</p>
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
      {/* Summary */}
      <div className="flex gap-8">
        <div>
          <p className="text-xs text-muted-foreground">Total duration</p>
          <p className="text-lg font-semibold">{formatTime(data.total_duration_sec)}</p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Scenes</p>
          <p className="text-lg font-semibold">{data.scene_count}</p>
        </div>
      </div>

      {/* Proportional timeline bar */}
      <div className="flex h-8 rounded-md overflow-hidden border">
        {data.scenes.map((scene, i) => (
          <div
            key={scene.scene_id}
            title={`Scene ${scene.scene_id}: ${formatTime(scene.start_sec)}–${formatTime(scene.end_sec)} (${scene.duration_sec.toFixed(1)}s)`}
            className={`${SCENE_COLORS[i % SCENE_COLORS.length]} flex items-center justify-center text-[10px] font-semibold text-white border-r border-white/30 last:border-r-0`}
            style={{ width: `${(scene.duration_sec / data.total_duration_sec) * 100}%` }}
          >
            {scene.duration_sec / data.total_duration_sec > 0.035 ? scene.scene_id : ''}
          </div>
        ))}
      </div>

      {/* Per-scene breakdown */}
      <div className="space-y-1.5">
        {data.scenes.map((scene, i) => {
          const hasPauses = scene.internal_pauses.length > 0
          const open = expanded.has(scene.scene_id)
          return (
            <div key={scene.scene_id} className="border rounded-lg overflow-hidden">
              <button
                onClick={() => hasPauses && toggle(scene.scene_id)}
                className={`w-full flex items-center gap-3 px-3 py-2 text-left ${hasPauses ? 'hover:bg-muted/50 cursor-pointer' : 'cursor-default'}`}
              >
                <span className={`w-2 h-2 rounded-full shrink-0 ${SCENE_COLORS[i % SCENE_COLORS.length]}`} />
                <span className="text-xs font-semibold shrink-0 w-16">Scene {scene.scene_id}</span>
                <span className="text-xs text-muted-foreground shrink-0">
                  {formatTime(scene.start_sec)} – {formatTime(scene.end_sec)}
                </span>
                <span className="text-xs font-medium ml-auto shrink-0">{scene.duration_sec.toFixed(1)}s</span>
                {hasPauses && (
                  <span className="text-[11px] text-muted-foreground shrink-0 px-2 py-0.5 rounded-full bg-muted">
                    {scene.pause_count} pause{scene.pause_count !== 1 ? 's' : ''}
                  </span>
                )}
              </button>
              {open && hasPauses && (
                <div className="px-3 pb-2 pt-0.5 border-t bg-muted/20">
                  <div className="flex flex-wrap gap-1.5 pt-2">
                    {scene.internal_pauses.map((p, idx) => (
                      <span key={idx} className="text-[11px] font-mono text-muted-foreground px-1.5 py-0.5 rounded bg-background border">
                        {formatTime(p.start)}–{formatTime(p.end)} ({p.duration.toFixed(2)}s)
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
