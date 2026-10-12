import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Film, Plus, RefreshCw } from 'lucide-react'
import { listRuns, startRun, type RunSummary } from '@/api/tasks'
import { DOMAIN_DESCRIPTIONS } from '@/lib/domainDescriptions'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

// ─── Domain colours ───────────────────────────────────────────────────────────

const DOMAIN_COLORS: Record<string, string> = {
  political:         'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  general_knowledge: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  science:           'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  business:          'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  history:           'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  sports:            'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  technology:        'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  general:           'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-400',
}

const SUPPORTED_DOMAINS = ['political', 'general_knowledge', 'science', 'business', 'history', 'sports', 'technology', 'general']

// ─── Run card ─────────────────────────────────────────────────────────────────

function runStatus(run: RunSummary): 'active' | 'done' | 'failed' | 'partial' {
  if (run.active) return 'active'
  if (run.steps_completed === run.steps_total) return 'done'
  if (run.steps_failed > 0) return 'failed'
  return 'partial'
}

function RunCard({ run, onClick }: { run: RunSummary; onClick: () => void }) {
  const status = runStatus(run)
  const pct = Math.round((run.steps_completed / run.steps_total) * 100)
  const date = run.created_at ? new Date(run.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : run.run_id

  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl border bg-card p-5 hover:border-primary/50 hover:shadow-md transition-all focus:outline-none focus:ring-2 focus:ring-ring group"
    >
      <div className="flex items-start justify-between mb-3">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${DOMAIN_COLORS[run.domain] ?? DOMAIN_COLORS.general}`}>
          {run.domain.replace('_', ' ')}
        </span>
        {status === 'active' && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Active
          </span>
        )}
        {status === 'done' && <Badge variant="success">Done</Badge>}
        {status === 'failed' && <Badge variant="destructive">Failed</Badge>}
        {status === 'partial' && <Badge variant="secondary">Partial</Badge>}
      </div>

      <p className="text-xs text-muted-foreground mb-3">{date}</p>

      <Progress value={pct} className="h-1.5 mb-2" />

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{run.steps_completed}/{run.steps_total} steps{run.steps_failed > 0 ? ` · ${run.steps_failed} failed` : ''}</span>
        {run.videos.length > 0 && (
          <span className="flex items-center gap-1">
            <Film className="w-3 h-3" />
            {run.videos.length} video{run.videos.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </button>
  )
}

// ─── New Run modal ────────────────────────────────────────────────────────────

function NewRunModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate()
  const [domain, setDomain] = useState('political')
  const [fresh, setFresh] = useState(false)
  const [loading, setLoading] = useState(false)

  async function handleStart() {
    setLoading(true)
    try {
      const res = await startRun(domain, fresh)
      onClose()
      navigate(`/tasks/${res.domain}/${res.run_id}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>New Pipeline Run</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Domain</label>
            <Select value={domain} onValueChange={setDomain}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SUPPORTED_DOMAINS.map((d) => (
                  <SelectItem key={d} value={d}>{d.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</SelectItem>
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
            <label className="text-sm font-medium">Mode</label>
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
              {fresh ? 'Creates a new workspace — run each of the 18 steps individually from there.' : 'Resumes the latest workspace, skipping completed steps.'}
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={handleStart} disabled={loading}>
            {loading ? 'Starting…' : 'Start Run'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TasksListPage() {
  const navigate = useNavigate()
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function fetchRuns() {
    try {
      const data = await listRuns()
      setRuns(data)
      return data
    } catch {
      return []
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchRuns()
  }, [])

  // Auto-poll every 5s while any run is active
  useEffect(() => {
    const hasActive = runs.some(r => r.active)
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(fetchRuns, 5000)
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [runs])

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pipeline Runs</h1>
          <p className="text-sm text-muted-foreground mt-1">{runs.length} workspace{runs.length !== 1 ? 's' : ''} across all domains</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={fetchRuns} title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </Button>
          <Button onClick={() => setShowModal(true)}>
            <Plus className="w-4 h-4 mr-1.5" />
            New Run
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-xl" />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <Film className="w-12 h-12 text-muted-foreground mb-4" />
          <p className="text-lg font-medium">No runs yet</p>
          <p className="text-sm text-muted-foreground mt-1">Start your first pipeline run to generate a documentary.</p>
          <Button className="mt-4" onClick={() => setShowModal(true)}>
            <Plus className="w-4 h-4 mr-1.5" /> New Run
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {runs.map((run) => (
            <RunCard
              key={`${run.domain}/${run.run_id}`}
              run={run}
              onClick={() => navigate(`/tasks/${run.domain}/${run.run_id}`)}
            />
          ))}
        </div>
      )}

      <NewRunModal open={showModal} onClose={() => setShowModal(false)} />
    </div>
  )
}
