import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, RefreshCw, X } from 'lucide-react'
import { deleteRun, getRunStatus, getStepContent, runStep, startRun } from '@/api/tasks'
import { DOMAIN_DESCRIPTIONS } from '@/lib/domainDescriptions'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import MarkdownViewer from '@/components/viewers/MarkdownViewer'

// ─── Constants ────────────────────────────────────────────────────────────────

const SUPPORTED_DOMAINS = [
  { value: 'political',         label: 'Political' },
  { value: 'general_knowledge', label: 'General Knowledge' },
  { value: 'science',           label: 'Science' },
  { value: 'business',          label: 'Business' },
  { value: 'history',           label: 'History' },
  { value: 'sports',            label: 'Sports' },
  { value: 'technology',        label: 'Technology' },
  { value: 'general',           label: 'General' },
]

// ─── Stage types ──────────────────────────────────────────────────────────────

type Stage = 'form' | 'waiting' | 'preview' | 'regenerating'

interface PendingRun {
  domain: string
  run_id: string
}

// ─── Subcomponents ────────────────────────────────────────────────────────────

function Spinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16">
      <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      <p className="text-sm text-muted-foreground">{label}</p>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function GeneratePage() {
  const navigate = useNavigate()

  // Form state
  const [domain, setDomain] = useState('political')
  const [fresh, setFresh] = useState(false)

  // Flow state
  const [stage, setStage] = useState<Stage>('form')
  const [pendingRun, setPendingRun] = useState<PendingRun | null>(null)
  const [previewContent, setPreviewContent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function stopPolling() {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  // Poll step 1 until it's done, then fetch and show its content
  async function waitForStep1(run: PendingRun) {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const status = await getRunStatus(run.domain, run.run_id)
        const step1 = status.steps.find(s => s.id === '1')
        if (step1?.status === 'done') {
          stopPolling()
          const content = await getStepContent(run.domain, run.run_id, '1')
          const text =
            content.kind === 'markdown'
              ? content.content
              : content.kind === 'research' && content.sections?.length
              ? content.sections.map((s: { label: string; content: string }) => `${s.label}\n\n${s.content}`).join('\n\n')
              : null
          setPreviewContent(text)
          setStage('preview')
        } else if (step1?.status === 'failed') {
          stopPolling()
          setError('Step 1 failed to generate research. Please try again.')
          setStage('form')
        }
      } catch {
        // keep polling
      }
    }, 2000)
  }

  useEffect(() => () => stopPolling(), [])

  // ─── Actions ───────────────────────────────────────────────────────────────

  async function handleStart() {
    setError(null)
    if (fresh) {
      // Fresh start: preview flow — run step 1 only, then wait for approval
      setStage('waiting')
      try {
        const res = await startRun(domain, true, true)
        const run = { domain: res.domain, run_id: res.run_id }
        setPendingRun(run)
        await waitForStep1(run)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Something went wrong')
        setStage('form')
      }
    } else {
      // Resume: start full pipeline and navigate immediately
      try {
        const res = await startRun(domain, false)
        navigate(`/tasks/${res.domain}/${res.run_id}`)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Something went wrong')
      }
    }
  }

  function handleApprove() {
    if (!pendingRun) return
    navigate(`/tasks/${pendingRun.domain}/${pendingRun.run_id}`)
  }

  async function handleRegenerate() {
    if (!pendingRun) return
    setStage('regenerating')
    setPreviewContent(null)
    try {
      await runStep(pendingRun.domain, pendingRun.run_id, '1', true)
      await waitForStep1(pendingRun)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setStage('preview')
    }
  }

  async function handleCancel() {
    stopPolling()
    // Delete the workspace so it doesn't appear in the runs list
    if (pendingRun) {
      try { await deleteRun(pendingRun.domain, pendingRun.run_id) } catch { /* best-effort */ }
    }
    setPendingRun(null)
    setPreviewContent(null)
    setError(null)
    setStage('form')
  }

  // ─── Render ────────────────────────────────────────────────────────────────

  // Preview / regenerating: full-width card
  if (stage === 'preview' || stage === 'regenerating') {
    return (
      <div className="min-h-[calc(100vh-56px)] bg-background flex items-center justify-center p-6">
        <Card className="w-full max-w-2xl">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Research Overview</CardTitle>
                <CardDescription>
                  {stage === 'regenerating'
                    ? 'Generating a new topic…'
                    : 'Review the topic, then open the pipeline to run the remaining steps.'}
                </CardDescription>
              </div>
              <button
                onClick={handleCancel}
                className="text-muted-foreground hover:text-foreground transition-colors"
                title="Cancel"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </CardHeader>

          <CardContent className="space-y-5">
            {stage === 'regenerating' ? (
              <Spinner label="Generating new topic…" />
            ) : (
              <>
                <ScrollArea className="h-80 rounded-lg border p-4 bg-muted/30">
                  {previewContent
                    ? <MarkdownViewer content={previewContent} />
                    : <p className="text-sm text-muted-foreground">No content available.</p>
                  }
                </ScrollArea>

                {error && <p className="text-sm text-destructive">{error}</p>}

                <div className="flex gap-2">
                  <Button variant="outline" className="gap-1.5" onClick={handleRegenerate}>
                    <RefreshCw className="w-3.5 h-3.5" />
                    Try Different Topic
                  </Button>
                  <div className="flex-1" />
                  <Button variant="ghost" onClick={handleCancel}>Cancel</Button>
                  <Button onClick={handleApprove}>Approve & Open Pipeline</Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    )
  }

  // Waiting: step 1 running
  if (stage === 'waiting') {
    return (
      <div className="min-h-[calc(100vh-56px)] bg-background flex items-center justify-center p-6">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>Generating Research</CardTitle>
            <CardDescription>Researching the topic for <strong>{domain.replace('_', ' ')}</strong>…</CardDescription>
          </CardHeader>
          <CardContent>
            <Spinner label="This usually takes 20–40 seconds." />
            <Button variant="outline" className="w-full mt-2" onClick={handleCancel}>Cancel</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Default: form
  return (
    <div className="min-h-[calc(100vh-56px)] bg-background flex items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>New Pipeline Run</CardTitle>
          <CardDescription>Select a domain and choose whether to resume or start fresh.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-1.5">
            <Label>Domain</Label>
            <Select value={domain} onValueChange={setDomain}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SUPPORTED_DOMAINS.map((d) => (
                  <SelectItem key={d.value} value={d.value}>{d.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {DOMAIN_DESCRIPTIONS[domain] && (
              <div className="rounded-lg bg-muted/50 border px-3 py-2.5 space-y-1.5">
                <p className="text-xs text-foreground leading-relaxed">{DOMAIN_DESCRIPTIONS[domain].role}</p>
                <p className="text-xs text-muted-foreground leading-relaxed">{DOMAIN_DESCRIPTIONS[domain].task}</p>
              </div>
            )}
          </div>

          <div className="space-y-1.5">
            <Label>Mode</Label>
            <div className="flex rounded-lg border overflow-hidden">
              <button
                onClick={() => setFresh(false)}
                className={`flex-1 px-3 py-2 text-sm transition-colors ${!fresh ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
              >
                Resume latest
              </button>
              <button
                onClick={() => setFresh(true)}
                className={`flex-1 px-3 py-2 text-sm transition-colors border-l ${fresh ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'}`}
              >
                Fresh start
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              {fresh
                ? 'Generates a research overview for your approval, then opens the pipeline for you to run steps individually.'
                : 'Resumes the latest workspace for this domain — run each step individually from there.'}
            </p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <Button className="w-full" onClick={handleStart}>
            {fresh ? 'Generate Preview' : 'Start Run'}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
