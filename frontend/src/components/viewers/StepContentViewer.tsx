import type { StepContent } from '@/api/tasks'
import MarkdownViewer from './MarkdownViewer'
import ImageGridViewer from './ImageGridViewer'
import AudioPlayer from './AudioPlayer'
import VideoPlayer from './VideoPlayer'
import TextViewer from './TextViewer'

interface Props {
  content: StepContent
}

export default function StepContentViewer({ content }: Props) {
  switch (content.kind) {
    case 'markdown':
      if (!content.content) return <p className="text-sm text-muted-foreground">No content yet.</p>
      return <MarkdownViewer content={content.content} />

    case 'text':
      if (!content.content) return <p className="text-sm text-muted-foreground">No content yet.</p>
      return <TextViewer content={content.content} />

    case 'json':
      if (content.content === null) return <p className="text-sm text-muted-foreground">No content yet.</p>
      return <TextViewer content={content.content} isJson />

    case 'audio':
      return <AudioPlayer url={content.url} />

    case 'video':
      return <VideoPlayer url={content.url} />

    case 'image_list':
      return <ImageGridViewer images={content.images} />

    case 'video_list':
      return <VideoPlayer videos={content.videos} />

    case 'animation_list':
      if (content.items.length === 0) return <p className="text-sm text-muted-foreground">No animation prompts yet.</p>
      return (
        <div className="space-y-4">
          {content.items.map((item) => (
            <div key={item.path} className="border rounded-lg p-4 space-y-1">
              <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
              <p className="text-sm leading-relaxed">{item.text}</p>
            </div>
          ))}
        </div>
      )

    case 'asset_list':
      if (content.files.length === 0) return <p className="text-sm text-muted-foreground">No asset files yet.</p>
      return (
        <div className="space-y-1">
          {content.files.map((f) => (
            <div key={f.path} className="flex items-center gap-2 text-sm py-1 border-b last:border-0">
              <span className="text-muted-foreground text-xs w-32 shrink-0 truncate">{f.folder}/</span>
              <span className="font-mono text-xs">{f.name}</span>
            </div>
          ))}
        </div>
      )

    // Structured kinds are rendered by their own editors in RunDetailPage
    case 'research':
    case 'story':
    case 'scene_plan':
    case 'asset_manifest':
    case 'asset_acquisition':
    case 'assets_viewer':
      return null

    default:
      return <p className="text-sm text-muted-foreground">Unknown content type.</p>
  }
}
