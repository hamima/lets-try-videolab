import { Film } from 'lucide-react'

interface VideoItem {
  path: string
  url: string
  label: string
}

interface Props {
  url?: string | null
  videos?: VideoItem[]
}

export default function VideoPlayer({ url, videos }: Props) {
  // Single video mode
  if (url !== undefined) {
    if (!url) return <p className="text-sm text-muted-foreground">Video not yet generated.</p>
    return (
      <video controls className="w-full rounded-lg border" src={url}>
        Your browser does not support the video element.
      </video>
    )
  }

  // Video list mode (step 9 — animated clips)
  if (!videos || videos.length === 0) {
    return <p className="text-sm text-muted-foreground">No animated videos generated yet.</p>
  }

  return (
    <div className="space-y-4">
      {videos.map((v) => (
        <div key={v.path} className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Film className="w-3.5 h-3.5" />
            <span>{v.label}</span>
          </div>
          <video controls className="w-full rounded-lg border" src={v.url}>
            Your browser does not support the video element.
          </video>
        </div>
      ))}
    </div>
  )
}
