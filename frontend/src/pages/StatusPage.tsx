import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getStatus, getDownloadUrl } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'

type Status = 'pending' | 'processing' | 'done' | 'failed'

const STATUS_LABEL: Record<Status, string> = {
  pending: 'Pending',
  processing: 'Processing',
  done: 'Done',
  failed: 'Failed',
}

const STATUS_VARIANT: Record<Status, 'secondary' | 'warning' | 'success' | 'destructive'> = {
  pending: 'secondary',
  processing: 'warning',
  done: 'success',
  failed: 'destructive',
}

const POLL_INTERVAL_MS = 3000

export default function StatusPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const [status, setStatus] = useState<Status>('pending')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!jobId) return

    let stopped = false

    async function poll() {
      if (stopped || !jobId) return
      try {
        const res = await getStatus(jobId)
        setStatus(res.status)
        if (res.status === 'failed') setError(res.error)
        if (res.status !== 'done' && res.status !== 'failed') {
          setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        if (!stopped) setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    poll()
    return () => { stopped = true }
  }, [jobId])

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <CardTitle>Job status</CardTitle>
          <CardDescription className="font-mono text-xs break-all">{jobId}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <Badge variant={STATUS_VARIANT[status]} className="text-sm px-4 py-1">
            {STATUS_LABEL[status]}
          </Badge>

          {status === 'processing' || status === 'pending' ? (
            <p className="text-sm text-muted-foreground animate-pulse">
              Generating your video… this may take a few minutes.
            </p>
          ) : null}

          {status === 'failed' && (
            <p className="text-sm text-destructive">{error ?? 'Generation failed.'}</p>
          )}

          {status === 'done' && jobId && (
            <a href={getDownloadUrl(jobId)} download={`vidlife_${jobId}.mp4`}>
              <Button className="w-full">Download video</Button>
            </a>
          )}

          <Button variant="outline" className="w-full" onClick={() => navigate('/')}>
            New generation
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
