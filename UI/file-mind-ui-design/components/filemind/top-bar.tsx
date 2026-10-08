'use client'

import { Cpu, Search, Settings } from 'lucide-react'

export function TopBar({
  title,
  onSearch,
  onSettings,
}: {
  title: string
  onSearch: (query: string) => void
  onSettings: () => void
}) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-6 border-b border-border px-8">
      <p className="w-40 text-base font-semibold tracking-tight text-foreground">{title}</p>

      <form
        role="search"
        className="relative mx-auto w-full max-w-md"
        onSubmit={(e) => {
          e.preventDefault()
          const value = new FormData(e.currentTarget).get('q')?.toString() ?? ''
          onSearch(value)
        }}
      >
        <label htmlFor="global-search" className="sr-only">
          Search your files
        </label>
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <input
          id="global-search"
          name="q"
          placeholder="Search your files..."
          className="h-9 w-full rounded-lg border border-input bg-card pl-9 pr-14 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none"
        />
        <kbd className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
          Ctrl K
        </kbd>
      </form>

      <div className="flex items-center gap-3">
        <span className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground">
          <Cpu className="size-3.5 text-primary" aria-hidden />
          <span>
            Ollama <span className="text-foreground">running locally</span>
          </span>
        </span>
        <button
          type="button"
          onClick={onSettings}
          aria-label="Settings"
          className="flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <Settings className="size-4" aria-hidden />
        </button>
        <span
          className="flex size-8 items-center justify-center rounded-full bg-surface-2 text-xs font-semibold text-foreground"
          aria-label="Profile: Aarav S."
          role="img"
        >
          AS
        </span>
      </div>
    </header>
  )
}
