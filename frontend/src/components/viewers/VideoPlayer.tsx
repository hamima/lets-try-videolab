import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  url: string | null
}

export default function VideoPlayer({ url }: Props) {
  if (!url) return <p className="text-sm text-muted-foreground">Video not yet generated.</p>
  return (
    <div className="space-y-3">
      <video controls className="w-full rounded-lg border" src={url}>
        Your browser does not support the video element.
      </video>
      <Button asChild size="sm" variant="outline" className="gap-1.5">
        <a href={url} download="final_video.mp4">
          <Download className="w-3.5 h-3.5" />
          Download video
        </a>
      </Button>
    </div>
  )
}
