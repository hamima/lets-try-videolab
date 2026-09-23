import { Music } from 'lucide-react'

interface Props {
  url: string | null
  label?: string
}

export default function AudioPlayer({ url, label }: Props) {
  if (!url) {
    return <p className="text-sm text-muted-foreground">Audio file not yet generated.</p>
  }

  return (
    <div className="space-y-3">
      {label && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Music className="w-4 h-4" />
          <span>{label}</span>
        </div>
      )}
      <audio
        controls
        className="w-full"
        src={url}
      >
        Your browser does not support the audio element.
      </audio>
    </div>
  )
}
