import { Loader2 } from 'lucide-react'
import type { StepDetail } from '@/api/tasks'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { frontierIndex } from '@/lib/wizard'
import { cn } from '@/lib/utils'

// Horizontal progress stepper for the run wizard. Dots carry no step number
// or name — hovering/focusing a dot reveals the step's real name in a
// tooltip, keeping the strip compact across all 19 steps.
export default function WizardStepper({
  steps,
  currentStepId,
  onSelect,
}: {
  steps: StepDetail[]
  currentStepId: string
  onSelect: (stepId: string) => void
}) {
  const frontier = frontierIndex(steps)

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto px-4 py-3">
      {steps.map((step, index) => {
        const isCurrent = step.id === currentStepId
        const isReachable = index <= frontier
        const isDone = step.status === 'done'
        const isFailed = step.status === 'failed'
        const isRunning = step.status === 'running'

        return (
          <div key={step.id} className="flex items-center">
            {index > 0 && (
              <div className={cn('h-px w-4 shrink-0', index <= frontier ? 'bg-primary/40' : 'bg-border')} />
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  aria-label={step.name}
                  disabled={!isReachable}
                  onClick={() => isReachable && onSelect(step.id)}
                  className={cn(
                    'w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 transition-colors border',
                    isCurrent && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
                    isDone && 'bg-emerald-100 text-emerald-700 border-emerald-200',
                    isFailed && 'bg-red-100 text-red-700 border-red-200',
                    isRunning && 'bg-blue-50 text-blue-600 border-blue-200',
                    !isDone && !isFailed && !isRunning && 'bg-muted text-muted-foreground border-transparent',
                    !isReachable && 'opacity-50 cursor-not-allowed',
                    isReachable && !isCurrent && 'cursor-pointer hover:opacity-80',
                  )}
                >
                  {isRunning ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : isDone ? (
                    '✓'
                  ) : isFailed ? (
                    '✗'
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-current" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent>{step.name}</TooltipContent>
            </Tooltip>
          </div>
        )
      })}
    </div>
  )
}
