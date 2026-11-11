import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ChevronLeft, ChevronRight, CheckCircle2 } from 'lucide-react'
import { getRunStatus, runStep, type RunStatus, type StepDetail } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import StepContentPanel from '@/components/StepContentPanel'
import WizardStepper from '@/components/WizardStepper'
import { firstReachableStepId, isStepReachable, nextStepId, previousStepId } from '@/lib/wizard'

export default function RunWizardPage() {
  const { domain = '', runId = '', stepId = '' } = useParams<{ domain: string; runId: string; stepId: string }>()
  const navigate = useNavigate()

  const [run, setRun] = useState<RunStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [contentReloadKey, setContentReloadKey] = useState(0)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await getRunStatus(domain, runId)
      setRun(data)
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

  // Poll every 3s while run is active — same cadence as the classic page.
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

  async function handleRerun(step: StepDetail) {
    await runStep(domain, runId, step.id, true)
    await fetchStatus()
    setContentReloadKey((k) => k + 1)
  }

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-6 space-y-4">
        <Skeleton className="h-6 w-1/3" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!run) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center">
        <p className="text-muted-foreground text-sm">Couldn't load this run.</p>
      </div>
    )
  }

  // Route guard: redirect any URL for a step beyond the reachable frontier
  // back to the furthest step the user is actually allowed to be on.
  if (!isStepReachable(run.steps, stepId)) {
    const target = firstReachableStepId(run.steps)
    return <Navigate to={`/tasks/${domain}/${runId}/wizard/${target}`} replace />
  }

  const currentStep = run.steps.find((s) => s.id === stepId) ?? null
  const isLastStep = run.steps.length > 0 && run.steps[run.steps.length - 1].id === stepId
  const canAdvance = currentStep?.status === 'done'
  const prevId = previousStepId(run.steps, stepId)
  const nextId = nextStepId(run.steps, stepId)

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 56px)' }}>
      {/* Sub-header */}
      <div className="border-b px-4 py-3 flex items-center justify-between shrink-0 bg-background">
        <Button variant="ghost" size="sm" className="gap-1.5 -ml-1" onClick={() => navigate(`/tasks/${domain}/${runId}`)}>
          <ArrowLeft className="w-4 h-4" /> View in classic
        </Button>
        <span className="text-sm text-muted-foreground">Wizard · {domain.replace('_', ' ')} / {runId}</span>
      </div>

      {/* Progress stepper */}
      <div className="border-b shrink-0">
        <WizardStepper
          steps={run.steps}
          currentStepId={stepId}
          onSelect={(id) => navigate(`/tasks/${domain}/${runId}/wizard/${id}`)}
        />
      </div>

      {/* Step content */}
      <div className="flex-1 overflow-hidden">
        <StepContentPanel
          step={currentStep}
          domain={domain}
          runId={runId}
          reloadKey={contentReloadKey}
          onRerun={() => currentStep && handleRerun(currentStep)}
          onSaved={() => fetchStatus()}
        />
      </div>

      {/* Back / Next controls */}
      <div className="border-t px-4 py-3 flex items-center justify-between shrink-0 bg-background">
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={!prevId}
          onClick={() => prevId && navigate(`/tasks/${domain}/${runId}/wizard/${prevId}`)}
        >
          <ChevronLeft className="w-4 h-4" /> Back
        </Button>

        {isLastStep && canAdvance ? (
          <span className="flex items-center gap-1.5 text-sm text-emerald-600 font-medium">
            <CheckCircle2 className="w-4 h-4" /> Pipeline complete — all {run.steps.length} steps done
          </span>
        ) : (
          <Button
            size="sm"
            className="gap-1.5"
            disabled={!canAdvance || !nextId}
            onClick={() => nextId && navigate(`/tasks/${domain}/${runId}/wizard/${nextId}`)}
          >
            Next <ChevronRight className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  )
}
