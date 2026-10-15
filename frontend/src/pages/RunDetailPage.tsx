import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Loader2, RotateCcw, Plus } from 'lucide-react'
import { getRunStatus, getStepContent, runStep, startRun, updateStepContent, type RunStatus, type StepContent, type StepDetail } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import StepContentViewer from '@/components/viewers/StepContentViewer'
import ResearchEditor from '@/components/viewers/ResearchEditor'
import ScenePlanEditor from '@/components/viewers/ScenePlanEditor'
import AssetPlanEditor from '@/components/viewers/AssetPlanEditor'
import AssetFolderViewer from '@/components/viewers/AssetFolderViewer'
import ImageSceneViewer from '@/components/viewers/ImageSceneViewer'
import VideoSceneViewer from '@/components/viewers/VideoSceneViewer'
import AnimationPromptViewer from '@/components/viewers/AnimationPromptViewer'
import NarrationTimingViewer, { type NarrationTiming } from '@/components/viewers/NarrationTimingViewer'
import EditDecisionListViewer, { type EditDecisionList } from '@/components/viewers/EditDecisionListViewer'
import { cn } from '@/lib/utils'

// ─── Domain colours (same as list page) ─────────────────────────────────────

const DOMAIN_COLORS: Record<string, string> = {
  political:         'bg-red-100 text-red-700',
  general_knowledge: 'bg-blue-100 text-blue-700',
  science:           'bg-emerald-100 text-emerald-700',
  business:          'bg-yellow-100 text-yellow-700',
  history:           'bg-amber-100 text-amber-700',
  sports:            'bg-orange-100 text-orange-700',
  technology:        'bg-purple-100 text-purple-700',
  general:           'bg-slate-100 text-slate-700',
}

// ─── Step status pill ─────────────────────────────────────────────────────────

function StepPill({ status, id }: { status: StepDetail['status']; id: string }) {
  if (status === 'running') return <Loader2 className="w-5 h-5 shrink-0 text-blue-500 animate-spin" />
  return (
    <span className={cn(
      'w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0',
      status === 'done'    && 'bg-emerald-100 text-emerald-700',
      status === 'failed'  && 'bg-red-100 text-red-700',
      status === 'pending' && 'bg-muted text-muted-foreground',
    )}>
      {status === 'done' ? '✓' : status === 'failed' ? '✗' : id}
    </span>
  )
}

// ─── Content panel ────────────────────────────────────────────────────────────

function ContentPanel({
  step,
  domain,
  runId,
  reloadKey,
  onRerun,
}: {
  step: StepDetail | null
  domain: string
  runId: string
  reloadKey: number
  onRerun: () => void
}) {
  const [content, setContent] = useState<StepContent | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!step) { setContent(null); return }
    if (step.status === 'pending') { setContent(null); return }

    setLoading(true)
    getStepContent(domain, runId, step.id)
      .then(setContent)
      .catch(() => setContent(null))
      .finally(() => setLoading(false))
  }, [step?.id, step?.status, domain, runId, reloadKey])

  if (!step) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-8">
        <p className="text-muted-foreground text-sm">Select a step to view its output.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-5 py-4 border-b flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <div>
            <h2 className="font-semibold text-sm">{step.name}</h2>
            <p className="text-xs text-muted-foreground">Step {step.id} · {step.type}</p>
          </div>
          {step.status === 'running' && <Badge variant="secondary" className="gap-1"><Loader2 className="w-3 h-3 animate-spin" />Running</Badge>}
          {step.status === 'done'    && <Badge variant="success">Done</Badge>}
          {step.status === 'failed'  && <Badge variant="destructive">Failed</Badge>}
          {step.status === 'pending' && <Badge variant="outline">Pending</Badge>}
        </div>
        {step.type !== 'runpod_animation' && (
          <Button size="sm" variant="outline" onClick={onRerun} className="gap-1.5">
            <RotateCcw className="w-3.5 h-3.5" />
            Rerun
          </Button>
        )}
      </div>

      {/* Content */}
      <ScrollArea className="flex-1">
        <div className="p-5">
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : step.status === 'pending' ? (
            <div className="text-center py-12">
              <p className="text-muted-foreground text-sm">This step hasn't run yet.</p>
              {step.type !== 'runpod_animation' && (
                <Button size="sm" variant="outline" className="mt-3 gap-1.5" onClick={onRerun}>
                  <RotateCcw className="w-3.5 h-3.5" /> Run now
                </Button>
              )}
            </div>
          ) : step.status === 'failed' ? (
            <div className="text-center py-12">
              <p className="text-destructive text-sm font-medium">Step failed</p>
              <p className="text-muted-foreground text-xs mt-1">Check server logs for details.</p>
              {step.type !== 'runpod_animation' && (
                <Button size="sm" variant="outline" className="mt-3 gap-1.5" onClick={onRerun}>
                  <RotateCcw className="w-3.5 h-3.5" /> Retry
                </Button>
              )}
            </div>
          ) : content ? (
            content.kind === 'research' || content.kind === 'story' ? (
              <ResearchEditor
                sections={content.sections}
                onSave={(sections) => updateStepContent(domain, runId, step.id, { sections })}
              />
            ) : content.kind === 'scene_plan' ? (
              <ScenePlanEditor
                scenes={content.scenes}
                onSave={(scenes) => updateStepContent(domain, runId, step.id, { scenes })}
              />
            ) : content.kind === 'asset_manifest' || content.kind === 'asset_acquisition' ? (
              <AssetPlanEditor
                scenes={content.scenes}
                onSave={(asset_scenes) => updateStepContent(domain, runId, step.id, { asset_scenes })}
              />
            ) : content.kind === 'assets_viewer' ? (
              <AssetFolderViewer
                scenes={content.scenes}
                domain={domain}
                runId={runId}
              />
            ) : content.kind === 'image_list' ? (
              <ImageSceneViewer
                images={content.images}
                domain={domain}
                runId={runId}
              />
            ) : content.kind === 'animation_list' ? (
              <AnimationPromptViewer
                items={content.items}
                domain={domain}
                runId={runId}
              />
            ) : content.kind === 'json' && step.id === '15' && content.content ? (
              <NarrationTimingViewer data={content.content as NarrationTiming} />
            ) : content.kind === 'json' && step.id === '16' && content.content && !Array.isArray(content.content) ? (
              <EditDecisionListViewer data={content.content as EditDecisionList} />
            ) : content.kind === 'video_list' ? (
              <VideoSceneViewer
                videos={content.videos}
                domain={domain}
                runId={runId}
              />
            ) : (
              <StepContentViewer content={content} />
            )
          ) : (
            <p className="text-muted-foreground text-sm">No content available.</p>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function RunDetailPage() {
  const { domain = '', runId = '' } = useParams<{ domain: string; runId: string }>()
  const navigate = useNavigate()

  const [run, setRun] = useState<RunStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedStep, setSelectedStep] = useState<StepDetail | null>(null)
  const [_rerunning, setRerunning] = useState(false)
  const [contentReloadKey, setContentReloadKey] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevActiveStepRef = useRef<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getRunStatus(domain, runId)
      setRun(data)

      // Auto-select active step when it changes
      if (data.active_step && data.active_step !== prevActiveStepRef.current) {
        prevActiveStepRef.current = data.active_step
        const activeStep = data.steps.find(s => s.id === data.active_step)
        if (activeStep) setSelectedStep(activeStep)
      }

      return data
    } catch {
      return null
    } finally {
      setLoading(false)
    }
  }, [domain, runId])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  // Poll every 3s while run is active
  useEffect(() => {
    if (!run) return
    if (run.active && !pollRef.current) {
      pollRef.current = setInterval(fetchStatus, 3000)
    } else if (!run.active && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [run?.active, fetchStatus])

  // Keep selectedStep in sync with latest step statuses
  useEffect(() => {
    if (!selectedStep || !run) return
    const updated = run.steps.find(s => s.id === selectedStep.id)
    if (updated && updated.status !== selectedStep.status) {
      setSelectedStep(updated)
    }
  }, [run?.steps])

  async function handleRerun(step: StepDetail) {
    setRerunning(true)
    try {
      await runStep(domain, runId, step.id, true)
      await fetchStatus()
      setContentReloadKey((k) => k + 1)
    } finally {
      setRerunning(false)
    }
  }

  async function handleFreshStart() {
    try {
      const res = await startRun(domain, true)
      navigate(`/tasks/${res.domain}/${res.run_id}`)
    } catch {}
  }

  const date = run?.run_id
    ? (() => {
        try {
          const [datePart, timePart] = run.run_id.split('_')
          const [y, m, d] = datePart.split('-')
          const t = timePart ?? '000000'
          return new Date(`${y}-${m}-${d}T${t.slice(0,2)}:${t.slice(2,4)}:${t.slice(4,6)}`).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
        } catch { return run.run_id }
      })()
    : ''

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Sub-header */}
      <div className="border-b px-4 py-3 flex items-center justify-between shrink-0 bg-background">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" className="gap-1.5 -ml-1" onClick={() => navigate('/tasks')}>
            <ArrowLeft className="w-4 h-4" /> Pipeline
          </Button>
          <div className="h-4 w-px bg-border" />
          <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full', DOMAIN_COLORS[domain] ?? DOMAIN_COLORS.general)}>
            {domain.replace('_', ' ')}
          </span>
          <span className="text-sm text-muted-foreground">{date}</span>
          {run?.active && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Active
            </span>
          )}
        </div>
        <Button variant="outline" size="sm" className="gap-1.5" onClick={handleFreshStart}>
          <Plus className="w-3.5 h-3.5" /> Fresh Start
        </Button>
      </div>

      {/* Body */}
      {loading ? (
        <div className="flex flex-1 overflow-hidden">
          <div className="w-72 border-r p-4 space-y-2 shrink-0">
            {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-10 rounded-lg" />)}
          </div>
          <div className="flex-1 p-6 space-y-3">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
          </div>
        </div>
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {/* Step timeline — left panel */}
          <div className="w-72 border-r shrink-0 flex flex-col">
            <ScrollArea className="flex-1">
              <div className="p-3 space-y-1">
                {run?.steps.map((step) => (
                  <button
                    key={step.id}
                    onClick={() => setSelectedStep(step)}
                    className={cn(
                      'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
                      selectedStep?.id === step.id
                        ? 'bg-primary/10 text-primary'
                        : 'hover:bg-accent'
                    )}
                  >
                    <StepPill status={step.status} id={step.id} />
                    <div className="min-w-0 flex-1">
                      <p className={cn('text-sm font-medium truncate', selectedStep?.id === step.id ? 'text-primary' : 'text-foreground')}>
                        {step.name}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">{step.type}</p>
                    </div>
                  </button>
                ))}
              </div>
            </ScrollArea>
          </div>

          {/* Content panel — right */}
          <div className="flex-1 overflow-hidden">
            <ContentPanel
              step={selectedStep}
              domain={domain}
              runId={runId}
              reloadKey={contentReloadKey}
              onRerun={() => selectedStep && handleRerun(selectedStep)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
