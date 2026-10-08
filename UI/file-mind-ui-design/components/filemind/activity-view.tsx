import { Download, Inbox, Pencil, UserCheck, Wand2, Zap } from 'lucide-react'
import { cn } from '@/lib/utils'
import { auditLog, type AuditEntry } from '@/lib/filemind-data'
import { ConfidenceMeter, FileIcon, FmButton, PageIntro, Panel } from './primitives'

const actionStyles: Record<AuditEntry['action'], { icon: typeof Zap; className: string }> = {
  auto: { icon: Zap, className: 'text-primary bg-primary/10 border-primary/30' },
  renamed: { icon: Wand2, className: 'text-primary bg-primary/10 border-primary/30' },
  review: { icon: Inbox, className: 'text-warning bg-warning/10 border-warning/30' },
  'human-accept': { icon: UserCheck, className: 'text-foreground bg-surface-2 border-input' },
  'human-edit': { icon: Pencil, className: 'text-foreground bg-surface-2 border-input' },
}

export function ActivityView() {
  return (
    <div className="flex flex-col gap-6">
      <PageIntro
        eyebrow="Audit log"
        title="Every decision, explained"
        description="A complete, local record of what FileMind saw, what it decided, how confident it was, and what happened next."
        action={
          <FmButton size="sm">
            <Download className="size-3.5" aria-hidden />
            Export CSV
          </FmButton>
        }
      />

      {auditLog.map((group) => (
        <section key={group.day} aria-labelledby={`day-${group.day}`}>
          <h2 id={`day-${group.day}`} className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {group.day}
          </h2>
          <Panel>
            <div className="grid grid-cols-[88px_minmax(0,1.1fr)_minmax(0,1.3fr)_140px_minmax(0,1.2fr)] gap-4 border-b border-border px-5 py-2.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              <span>Time</span>
              <span>File</span>
              <span>AI decision</span>
              <span>Confidence</span>
              <span>Action</span>
            </div>
            <ol>
              {group.entries.map((entry) => {
                const style = actionStyles[entry.action]
                const Icon = style.icon
                return (
                  <li
                    key={entry.id}
                    className="relative grid grid-cols-[88px_minmax(0,1.1fr)_minmax(0,1.3fr)_140px_minmax(0,1.2fr)] items-center gap-4 border-b border-border px-5 py-3.5 last:border-b-0"
                  >
                    <span className="relative flex items-center gap-3">
                      <span className="font-mono text-xs tabular-nums text-muted-foreground">{entry.time}</span>
                    </span>
                    <span className="flex min-w-0 items-center gap-2.5">
                      <FileIcon kind={entry.kind} size="sm" />
                      <span className="truncate font-mono text-[13px] text-foreground">{entry.file}</span>
                    </span>
                    <span className="min-w-0 text-sm text-foreground/90">{entry.decision}</span>
                    <ConfidenceMeter value={entry.confidence} />
                    <span className="min-w-0">
                      <span
                        className={cn(
                          'inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium',
                          style.className,
                        )}
                      >
                        <Icon className="size-3" aria-hidden />
                        {entry.actionLabel}
                      </span>
                      {entry.movedTo ? (
                        <span className="mt-1 block truncate font-mono text-[11px] text-muted-foreground">
                          {entry.movedTo}
                        </span>
                      ) : null}
                    </span>
                  </li>
                )
              })}
            </ol>
          </Panel>
        </section>
      ))}
    </div>
  )
}
