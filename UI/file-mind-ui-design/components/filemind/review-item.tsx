'use client'

import { useState } from 'react'
import { ArrowRight, Check, EyeOff, Pencil } from 'lucide-react'
import type { AnalyzedFile } from '@/lib/filemind-data'
import { CategoryPath, ConfidenceMeter, FileIcon, FmButton } from './primitives'

export function ReviewItem({
  file,
  detailed = false,
  onResolve,
}: {
  file: AnalyzedFile
  detailed?: boolean
  onResolve: (id: string, action: 'accepted' | 'ignored', category?: string[]) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(file.category.join(' / '))

  const saveEdit = () => {
    const path = draft
      .split('/')
      .map((s) => s.trim())
      .filter(Boolean)
    onResolve(file.id, 'accepted', path.length ? path : file.category)
  }

  return (
    <li className="flex flex-col gap-4 px-5 py-4">
      <div className="flex items-start gap-4">
        <FileIcon kind={file.kind} />
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-sm text-foreground">{file.original}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>AI suggests</span>
            {editing ? (
              <label className="flex items-center gap-2">
                <span className="sr-only">Edit destination</span>
                <input
                  autoFocus
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.nativeEvent.isComposing || e.keyCode === 229) return
                    if (e.key === 'Enter') saveEdit()
                    if (e.key === 'Escape') setEditing(false)
                  }}
                  className="h-7 w-56 rounded-md border border-primary/50 bg-background px-2 text-xs text-foreground focus:outline-none"
                />
              </label>
            ) : (
              <CategoryPath path={file.category} className="text-xs" />
            )}
            {!editing ? (
              <>
                <ArrowRight className="size-3" aria-hidden />
                <span className="truncate font-mono text-foreground/80">{file.suggested}</span>
              </>
            ) : null}
          </div>
        </div>
        <div className="w-40 shrink-0">
          <p className="mb-1 text-[11px] text-muted-foreground">Confidence</p>
          <ConfidenceMeter value={file.confidence} />
        </div>
      </div>

      {detailed ? (
        <div className="ml-13 rounded-lg border border-border bg-background/60 px-4 py-3">
          <p className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">Why FileMind is unsure</p>
          <p className="mt-1 text-sm leading-relaxed text-foreground/90">{file.reason}</p>
        </div>
      ) : null}

      <div className="ml-13 flex flex-wrap gap-2">
        {editing ? (
          <>
            <FmButton size="sm" variant="primary" onClick={saveEdit}>
              <Check className="size-3.5" aria-hidden />
              Save & organize
            </FmButton>
            <FmButton size="sm" variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </FmButton>
          </>
        ) : (
          <>
            <FmButton size="sm" variant="primary" onClick={() => onResolve(file.id, 'accepted')}>
              <Check className="size-3.5" aria-hidden />
              Accept
            </FmButton>
            <FmButton size="sm" onClick={() => setEditing(true)}>
              <Pencil className="size-3.5" aria-hidden />
              Edit
            </FmButton>
            <FmButton size="sm" variant="ghost" onClick={() => onResolve(file.id, 'ignored')}>
              <EyeOff className="size-3.5" aria-hidden />
              Ignore
            </FmButton>
          </>
        )}
      </div>
    </li>
  )
}
