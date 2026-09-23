import { useState } from 'react'
import { X } from 'lucide-react'

interface Image {
  path: string
  url: string
  label: string
}

interface Props {
  images: Image[]
}

export default function ImageGridViewer({ images }: Props) {
  const [lightbox, setLightbox] = useState<Image | null>(null)

  if (images.length === 0) {
    return <p className="text-sm text-muted-foreground">No images generated yet.</p>
  }

  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        {images.map((img) => (
          <button
            key={img.path}
            onClick={() => setLightbox(img)}
            className="group relative rounded-lg overflow-hidden border bg-muted aspect-video focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <img
              src={img.url}
              alt={img.label}
              className="w-full h-full object-cover transition-transform group-hover:scale-105"
              onError={(e) => { (e.target as HTMLImageElement).src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="%23f0f0f0"/></svg>' }}
            />
            <div className="absolute bottom-0 left-0 right-0 bg-black/50 px-2 py-1">
              <p className="text-xs text-white truncate">{img.label}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setLightbox(null)}
        >
          <button
            className="absolute top-4 right-4 text-white/70 hover:text-white"
            onClick={() => setLightbox(null)}
          >
            <X className="w-6 h-6" />
          </button>
          <img
            src={lightbox.url}
            alt={lightbox.label}
            className="max-w-full max-h-full rounded-lg object-contain"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  )
}
