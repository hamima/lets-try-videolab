import type { StepDetail } from '@/api/tasks'

// Shared gating logic for the step wizard: the user may always go back to a
// step already behind the "frontier", but may not jump ahead of it. The
// frontier is the first step that isn't done yet, or the last step once
// everything is done.
//
// This mirrors RunDetailPage's own status model — it reads StepDetail.status
// only and makes no backend calls or assumptions of its own.

export function frontierIndex(steps: StepDetail[]): number {
  if (steps.length === 0) return 0
  const firstIncomplete = steps.findIndex((s) => s.status !== 'done')
  return firstIncomplete === -1 ? steps.length - 1 : firstIncomplete
}

export function firstReachableStepId(steps: StepDetail[]): string {
  const step = steps[frontierIndex(steps)]
  return step ? step.id : ''
}

export function isStepReachable(steps: StepDetail[], stepId: string): boolean {
  const index = steps.findIndex((s) => s.id === stepId)
  if (index === -1) return false
  return index <= frontierIndex(steps)
}

export function nextStepId(steps: StepDetail[], currentStepId: string): string | null {
  const index = steps.findIndex((s) => s.id === currentStepId)
  if (index === -1 || index === steps.length - 1) return null
  return steps[index + 1].id
}

export function previousStepId(steps: StepDetail[], currentStepId: string): string | null {
  const index = steps.findIndex((s) => s.id === currentStepId)
  if (index <= 0) return null
  return steps[index - 1].id
}
