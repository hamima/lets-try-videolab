import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { signInWithGoogle } from '@/api/tasks'
import { useAuth } from '@/lib/auth'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined
const GSI_SCRIPT_SRC = 'https://accounts.google.com/gsi/client'

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (response: { credential: string }) => void }) => void
          renderButton: (parent: HTMLElement, options: Record<string, unknown>) => void
        }
      }
    }
  }
}

function loadGsiScript(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve()
  const existing = document.querySelector(`script[src="${GSI_SCRIPT_SRC}"]`)
  if (existing) {
    return new Promise((resolve) => existing.addEventListener('load', () => resolve()))
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GSI_SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load Google Sign-In'))
    document.head.appendChild(script)
  })
}

export default function SignInPage() {
  const { user, loading, refresh } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const buttonRef = useRef<HTMLDivElement>(null)
  const [error, setError] = useState<string | null>(null)

  const from = (location.state as { from?: string } | null)?.from ?? '/'

  useEffect(() => {
    if (!loading && user) {
      navigate(from, { replace: true })
    }
  }, [loading, user, from, navigate])

  useEffect(() => {
    if (loading || user) return
    if (!GOOGLE_CLIENT_ID) {
      setError('Sign-in is not configured (missing VITE_GOOGLE_CLIENT_ID).')
      return
    }

    let cancelled = false

    loadGsiScript()
      .then(() => {
        if (cancelled || !window.google || !buttonRef.current) return
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async (response) => {
            setError(null)
            try {
              await signInWithGoogle(response.credential)
              await refresh()
            } catch (err: unknown) {
              const detail =
                (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
              setError(detail ?? 'Sign-in failed. Please try again.')
            }
          },
        })
        window.google.accounts.id.renderButton(buttonRef.current, {
          theme: 'outline',
          size: 'large',
          shape: 'pill',
        })
      })
      .catch(() => setError('Failed to load Google Sign-In. Check your connection and try again.'))

    return () => {
      cancelled = true
    }
  }, [loading, user, refresh])

  if (loading || user) return null

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 px-4">
      <div className="text-center space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">VidLife</h1>
        <p className="text-muted-foreground text-sm">Sign in to view your pipeline runs</p>
      </div>

      <div ref={buttonRef} />

      {error ? (
        <p className="text-destructive text-sm text-center max-w-sm">{error}</p>
      ) : (
        <p className="text-muted-foreground text-xs">Only @gmail.com accounts are supported.</p>
      )}
    </div>
  )
}
