import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { getSettings } from '@/api/tasks'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useAuth } from '@/lib/auth'

function UserMenu() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  if (!user) return null

  async function handleSignOut() {
    setOpen(false)
    await signOut()
    navigate('/signin', { replace: true })
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
      >
        {user.user_id}
        <span className="text-xs">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-56 rounded-md border bg-popover shadow-md py-1 z-50">
          <div className="px-3 py-2 border-b">
            <p className="text-sm font-medium truncate">{user.user_id}</p>
            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
          </div>
          <button
            onClick={handleSignOut}
            className="w-full text-left px-3 py-2 text-sm text-foreground hover:bg-accent transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}

export default function Layout() {
  const [mockActive, setMockActive] = useState(false)
  const { user } = useAuth()

  useEffect(() => {
    getSettings()
      .then(data => setMockActive(data.values['MOCK_AI'] === true))
      .catch(() => {})
  }, [])

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen bg-background flex flex-col">
        {/* Top nav */}
        <header className="border-b bg-background/95 backdrop-blur sticky top-0 z-40">
          {mockActive && (
            <div className="bg-amber-500 text-white text-xs font-medium text-center py-1 tracking-wide">
              ⚠ AI MOCK MODE ON — placeholder outputs only
            </div>
          )}
          <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
            <span className="font-semibold text-foreground tracking-tight">VidLife</span>
            <div className="flex items-center gap-2">
              <nav className="flex items-center gap-1">
                <NavLink
                  to="/"
                  end
                  className={({ isActive }) =>
                    cn('px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent')
                  }
                >
                  Generate
                </NavLink>
                <NavLink
                  to="/tasks"
                  className={({ isActive }) =>
                    cn('px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                      isActive
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:text-foreground hover:bg-accent')
                  }
                >
                  Pipeline
                </NavLink>
                {user?.is_admin && (
                  <NavLink
                    to="/settings"
                    className={({ isActive }) =>
                      cn('px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:text-foreground hover:bg-accent')
                    }
                  >
                    Settings
                  </NavLink>
                )}
              </nav>
              <div className="h-4 w-px bg-border" />
              <UserMenu />
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1">
          <Outlet />
        </main>
      </div>
    </TooltipProvider>
  )
}
