import {
  Activity,
  Folder,
  FolderOpen,
  Inbox,
  LayoutDashboard,
  Search,
  Settings,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

export type PageId = 'dashboard' | 'files' | 'review' | 'search' | 'activity' | 'settings'

export const navItems: { id: PageId; label: string; icon: LucideIcon }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'files', label: 'Files', icon: Folder },
  { id: 'review', label: 'Review Queue', icon: Inbox },
  { id: 'search', label: 'Search', icon: Search },
  { id: 'activity', label: 'Activity', icon: Activity },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export function FileMindLogo() {
  return (
    <span className="relative flex size-9 items-center justify-center rounded-lg border border-primary/30 bg-gradient-to-br from-primary/25 to-primary/5">
      <svg viewBox="0 0 24 24" className="size-5 text-primary" fill="none" aria-hidden>
        <path
          d="M4 7.5A2.5 2.5 0 0 1 6.5 5h3.2l1.8 2h6A2.5 2.5 0 0 1 20 9.5v7a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-9Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <circle cx="12" cy="13" r="2.2" fill="currentColor" />
      </svg>
    </span>
  )
}

export function Sidebar({
  current,
  onNavigate,
  reviewCount,
}: {
  current: PageId
  onNavigate: (id: PageId) => void
  reviewCount: number
}) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
      <div className="flex items-center gap-3 px-5 pb-6 pt-5">
        <FileMindLogo />
        <div>
          <p className="text-[15px] font-semibold tracking-tight text-foreground">FileMind</p>
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="size-1.5 rounded-full bg-primary" aria-hidden />
            Gemma 4 · Local
          </p>
        </div>
      </div>

      <nav aria-label="Main" className="flex-1 px-3">
        <ul className="flex flex-col gap-0.5">
          {navItems.map(({ id, label, icon: Icon }) => {
            const active = current === id
            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onNavigate(id)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative flex h-9 w-full items-center gap-3 rounded-lg px-3 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-ring',
                    active
                      ? 'bg-sidebar-accent font-medium text-foreground'
                      : 'text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-foreground',
                  )}
                >
                  {active ? (
                    <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" aria-hidden />
                  ) : null}
                  <Icon className={cn('size-4', active ? 'text-primary' : 'text-muted-foreground')} aria-hidden />
                  <span className="flex-1 text-left">{label}</span>
                  {id === 'review' && reviewCount > 0 ? (
                    <span className="rounded-md bg-warning/15 px-1.5 py-0.5 font-mono text-[11px] text-warning">
                      {reviewCount}
                    </span>
                  ) : null}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="m-3 rounded-xl border border-sidebar-border bg-card p-4">
        <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Watched Folder</p>
        <div className="mt-2.5 flex items-center gap-2.5">
          <FolderOpen className="size-4 text-foreground" aria-hidden />
          <span className="text-sm font-medium text-foreground">Downloads</span>
        </div>
        <div className="mt-3 flex items-center gap-2 text-xs text-primary">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
          Watching
        </div>
      </div>
    </aside>
  )
}
