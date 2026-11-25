import { useEffect, useState } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import { getStepContent, updateStepContent, type StepContent, type StepDetail } from '@/api/tasks'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import StepContentViewer from '@/components/viewers/StepContentViewer'
import ResearchEditor from '@/components/viewers/ResearchEditor'
import ScenePlanEditor from '@/components/viewers/ScenePlanEditor'
import SubtitleEditor from '@/components/viewers/SubtitleEditor'
import AssetPlanEditor from '@/components/viewers/AssetPlanEditor'
import AssetFolderViewer from '@/components/viewers/AssetFolderViewer'
import ImageSceneViewer from '@/components/viewers/ImageSceneViewer'
import VideoSceneViewer from '@/components/viewers/VideoSceneViewer'
import AnimationPromptViewer from '@/components/viewers/AnimationPromptViewer'
import NarrationTimingViewer, { type NarrationTiming } from '@/components/viewers/NarrationTimingViewer'
import EditDecisionListViewer, { type EditDecisionList } from '@/components/viewers/EditDecisionListViewer'

// Renders a single step's output using the content-type-specific viewer/editor,
// plus a header with status + rerun. Shared by the classic RunDetailPage and
// the step wizard, so editing behavior stays identical between the two views.
export default function StepContentPanel({
  step,
  domain,
  runId,
  owner,
  reloadKey,
  onRerun,
  onSaved,
}: {
  step: StepDetail | null
  domain: string
  runId: string
  owner?: string
  reloadKey: number
  onRerun: () => void
  onSaved: () => void
}) {
  const [content, setContent] = useState<StepContent | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!step) { setContent(null); return }
    if (step.status === 'pending') { setContent(null); return }

    setLoading(true)
    getStepContent(domain, runId, step.id, owner)
      .then(setContent)
      .catch(() => setContent(null))
      .finally(() => setLoading(false))
  }, [step?.id, step?.status, domain, runId, owner, reloadKey])

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
        <Button size="sm" variant="outline" onClick={onRerun} className="gap-1.5">
          <RotateCcw className="w-3.5 h-3.5" />
          Rerun
        </Button>
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
              <Button size="sm" variant="outline" className="mt-3 gap-1.5" onClick={onRerun}>
                <RotateCcw className="w-3.5 h-3.5" /> Run now
              </Button>
            </div>
          ) : step.status === 'failed' ? (
            <div className="text-center py-12">
              <p className="text-destructive text-sm font-medium">Step failed</p>
              <p className="text-muted-foreground text-xs mt-1">Check server logs for details.</p>
              <Button size="sm" variant="outline" className="mt-3 gap-1.5" onClick={onRerun}>
                <RotateCcw className="w-3.5 h-3.5" /> Retry
              </Button>
            </div>
          ) : content ? (
            content.kind === 'research' || content.kind === 'story' ? (
              <ResearchEditor
                sections={content.sections}
                onSave={async (sections) => { await updateStepContent(domain, runId, step.id, { sections }, owner); onSaved() }}
              />
            ) : content.kind === 'scene_plan' ? (
              <ScenePlanEditor
                scenes={content.scenes}
                onSave={async (scenes) => { await updateStepContent(domain, runId, step.id, { scenes }, owner); onSaved() }}
              />
            ) : content.kind === 'subtitles' ? (
              <SubtitleEditor
                captions={content.captions}
                onSave={async (captions) => { await updateStepContent(domain, runId, step.id, { captions }, owner); onSaved() }}
              />
            ) : content.kind === 'asset_manifest' || content.kind === 'asset_acquisition' ? (
              <AssetPlanEditor
                scenes={content.scenes}
                onSave={async (asset_scenes) => { await updateStepContent(domain, runId, step.id, { asset_scenes }, owner); onSaved() }}
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
