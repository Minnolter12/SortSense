'use client'

import { CheckCircle2, Gauge, Hand, ShieldCheck } from 'lucide-react'
import { AUTO_THRESHOLD, type AnalyzedFile } from '@/lib/filemind-data'
import { PageIntro, Panel, PanelHeader } from './primitives'
import { ReviewItem } from './review-item'

export function ReviewView({
  reviewQueue,
  resolvedCount,
  onResolve,
}: {
  reviewQueue: AnalyzedFile[]
  resolvedCount: number
  onResolve: (id: string, action: 'accepted' | 'ignored', category?: string[]) => void
}) {
  return (
    <div className="flex flex-col gap-6">
      <PageIntro
        eyebrow="Human in the loop"
        title={
          reviewQueue.length > 0
            ? `${reviewQueue.length} file${reviewQueue.length === 1 ? '' : 's'} need your decision`
            : 'Review queue is clear'
        }
        description={`FileMind only moves files automatically when Gemma is at least ${AUTO_THRESHOLD}% confident. Everything else stays untouched in Downloads until you decide.`}
      />

      <div className="grid grid-cols-3 gap-4">
        <RuleCard
          icon={Gauge}
          title={`${AUTO_THRESHOLD}% threshold`}
          body="Below this, nothing is moved or renamed."
        />
        <RuleCard icon={Hand} title="You stay in control" body="Accept, edit the destination, or ignore." />
        <RuleCard icon={ShieldCheck} title="Fully reversible" body="Every move is logged and can be undone." />
      </div>

      <Panel>
        <PanelHeader
          title="Pending decisions"
          description={resolvedCount > 0 ? `${resolvedCount} resolved this session` : 'Sorted by lowest confidence first'}
        />
        {reviewQueue.length > 0 ? (
          <ul className="divide-y divide-border">
            {[...reviewQueue]
              .sort((a, b) => a.confidence - b.confidence)
              .map((file) => (
                <ReviewItem key={file.id} file={file} detailed onResolve={onResolve} />
              ))}
          </ul>
        ) : (
          <div className="flex flex-col items-center gap-3 px-5 py-16 text-center">
            <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
              <CheckCircle2 className="size-6" aria-hidden />
            </span>
            <p className="text-sm font-medium text-foreground">All caught up</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              New files that FileMind isn&apos;t sure about will wait here for you.
            </p>
          </div>
        )}
      </Panel>
    </div>
  )
}

function RuleCard({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof Gauge
  title: string
  body: string
}) {
  return (
    <Panel className="flex items-start gap-3 p-4">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-primary">
        <Icon className="size-4" aria-hidden />
      </span>
      <div>
        <p className="text-sm font-medium text-foreground">{title}</p>
        <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{body}</p>
      </div>
    </Panel>
  )
}
