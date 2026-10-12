interface Props {
  url: string | null
}

export default function VideoPlayer({ url }: Props) {
  if (!url) return <p className="text-sm text-muted-foreground">Video not yet generated.</p>
  return (
    <video controls className="w-full rounded-lg border" src={url}>
      Your browser does not support the video element.
    </video>
  )
}
