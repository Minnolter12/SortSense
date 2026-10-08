'use client'

import { useState } from 'react'
import { FolderOpen, Lightbulb, Search, ShieldCheck, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { searchResults } from '@/lib/filemind-data'
import { CategoryPath, FileIcon, FmButton, Panel, TopicChip } from './primitives'

const suggestions = [
  'Find my Fourier transform notes',
  'Bills I paid in September',
  'My latest offer letter',
  'Screenshots of flight bookings',
]

export function SearchView({ initialQuery }: { initialQuery: string }) {
  const [query, setQuery] = useState(initialQuery || 'Find my Fourier transform notes')
  const [submitted, setSubmitted] = useState(query)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="text-xs font-medium uppercase tracking-wider text-primary">Semantic search</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">Search by meaning, not filename</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Describe what&apos;s inside a file. FileMind searches its local understanding of every document.
        </p>
      </div>

      <form
        role="search"
        onSubmit={(e) => {
          e.preventDefault()
          setSubmitted(query)
        }}
        className="flex items-center gap-3 rounded-xl border border-primary/40 bg-card p-2 pl-4 shadow-[0_0_0_4px] shadow-primary/5"
      >
        <Sparkles className="size-5 shrink-0 text-primary" aria-hidden />
        <label htmlFor="semantic-search" className="sr-only">
          Describe the file you are looking for
        </label>
        <input
          id="semantic-search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="h-10 flex-1 bg-transparent text-base text-foreground placeholder:text-muted-foreground focus:outline-none"
          placeholder="Describe the file you're looking for..."
        />
        <FmButton type="submit" variant="primary">
          <Search className="size-4" aria-hidden />
          Search
        </FmButton>
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Try:</span>
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => {
              setQuery(s)
              setSubmitted(s)
            }}
            className={cn(
              'rounded-md border px-2.5 py-1 text-xs transition-colors',
              submitted === s
                ? 'border-primary/50 bg-primary/10 text-primary'
                : 'border-border bg-card text-muted-foreground hover:text-foreground',
            )}
          >
            {s}
          </button>
        ))}
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <p>
          <span className="text-foreground">{searchResults.length} results</span> for &ldquo;{submitted}&rdquo;
        </p>
        <p className="flex items-center gap-1.5">
          <ShieldCheck className="size-3.5 text-primary" aria-hidden />
          Searched 342 files locally in 0.4s
        </p>
      </div>

      <ul className="flex flex-col gap-3">
        {searchResults.map((r, i) => (
          <li key={r.id}>
            <Panel className={cn('p-5', i === 0 && 'border-primary/40')}>
              <div className="flex items-start gap-4">
                <FileIcon kind={r.kind} size="lg" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <p className="font-mono text-sm font-medium text-foreground">{r.name}</p>
                    {i === 0 ? (
                      <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] font-medium text-primary">
                        Best match
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-muted-foreground">
                    <CategoryPath path={r.category} className="text-xs" />
                    <span aria-hidden>·</span>
                    <span>Modified {r.modified}</span>
                  </div>

                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <span className="mr-1 text-xs text-muted-foreground">Matched topics</span>
                    {r.topics.map((t) => (
                      <TopicChip key={t}>{t}</TopicChip>
                    ))}
                  </div>

                  <p className="mt-3 flex items-start gap-2 rounded-lg bg-background/60 px-3 py-2.5 text-sm leading-relaxed text-foreground/90">
                    <Lightbulb className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                    {r.explanation}
                  </p>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-3">
                  <div className="text-right">
                    <p className="font-mono text-lg font-semibold tabular-nums text-foreground">{r.match}%</p>
                    <p className="text-[11px] text-muted-foreground">relevance</p>
                  </div>
                  <FmButton size="sm">
                    <FolderOpen className="size-3.5" aria-hidden />
                    Open
                  </FmButton>
                </div>
              </div>
            </Panel>
          </li>
        ))}
      </ul>
    </div>
  )
}
