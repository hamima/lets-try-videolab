import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { getSettings } from '@/api/tasks'

export default function Layout() {
  const [mockActive, setMockActive] = useState(false)

  useEffect(() => {
    getSettings()
      .then(data => setMockActive(data.values['MOCK_AI'] === true))
      .catch(() => {})
  }, [])

  return (
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
          </nav>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  )
}
