import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Loader2, Plus, Compass } from 'lucide-react'
import { getRunStatus, runStep, startRun, type RunStatus, type StepDetail } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import StepContentPanel from '@/components/StepContentPanel'
import { firstReachableStepId, isStepReachable } from '@/lib/wizard'
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function RunDetailPage() {
  const { domain = '', runId = '' } = useParams<{ domain: string; runId: string }>()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const owner = searchParams.get('owner') ?? undefined

  const [run, setRun] = useState<RunStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedStep, setSelectedStep] = useState<StepDetail | null>(null)
  const [_rerunning, setRerunning] = useState(false)
  const [contentReloadKey, setContentReloadKey] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prevActiveStepRef = useRef<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getRunStatus(domain, runId, owner)
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
  }, [domain, runId, owner])

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
      await runStep(domain, runId, step.id, true, owner)
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
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" onClick={handleFreshStart}>
            <Plus className="w-3.5 h-3.5" /> Fresh Start
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                disabled={!run}
                onClick={() => run && navigate(`/tasks/${domain}/${runId}/wizard/${firstReachableStepId(run.steps)}${owner ? `?owner=${encodeURIComponent(owner)}` : ''}`)}
              >
                <Compass className="w-3.5 h-3.5" /> Wizard View
              </Button>
            </TooltipTrigger>
            <TooltipContent>Open this run as a step-by-step wizard</TooltipContent>
          </Tooltip>
        </div>
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
                {run?.steps.map((step) => {
                  const reachable = isStepReachable(run.steps, step.id)
                  const tab = (
                    <button
                      key={step.id}
                      disabled={!reachable}
                      onClick={() => reachable && setSelectedStep(step)}
                      className={cn(
                        'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
                        !reachable && 'opacity-50 cursor-not-allowed',
                        reachable && selectedStep?.id === step.id
                          ? 'bg-primary/10 text-primary'
                          : reachable && 'hover:bg-accent'
                      )}
                    >
                      <StepPill status={step.status} id={step.id} />
                      <div className="min-w-0 flex-1">
                        <p className={cn('text-sm font-medium truncate', reachable && selectedStep?.id === step.id ? 'text-primary' : 'text-foreground')}>
                          {step.name}
                        </p>
                        <p className="text-xs text-muted-foreground truncate">{step.type}</p>
                      </div>
                    </button>
                  )
                  if (reachable) return tab
                  return (
                    <Tooltip key={step.id}>
                      <TooltipTrigger asChild>{tab}</TooltipTrigger>
                      <TooltipContent>Finish the previous steps first</TooltipContent>
                    </Tooltip>
                  )
                })}
              </div>
            </ScrollArea>
          </div>

          {/* Content panel — right */}
          <div className="flex-1 overflow-hidden">
            <StepContentPanel
              step={selectedStep}
              domain={domain}
              runId={runId}
              owner={owner}
              reloadKey={contentReloadKey}
              onRerun={() => selectedStep && handleRerun(selectedStep)}
              onSaved={() => fetchStatus()}
            />
          </div>
        </div>
      )}
    </div>
  )
}
