'use client'

import { useState } from 'react'
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  FileInput,
  FolderOpen,
  Gauge,
  Inbox,
  Layers,
  ListChecks,
  ScanText,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AUTO_THRESHOLD, recentActivity, type AnalyzedFile } from '@/lib/filemind-data'
import {
  CategoryPath,
  ConfidenceMeter,
  FileIcon,
  FmButton,
  Panel,
  PanelHeader,
  StatusBadge,
  TopicChip,
  confidenceTone,
} from './primitives'
import { ReviewItem } from './review-item'

const pipeline: { label: string; icon: LucideIcon }[] = [
  { label: 'File arrives', icon: FileInput },
  { label: 'Read locally', icon: ScanText },
  { label: 'Gemma understands', icon: Brain },
  { label: 'Confidence check', icon: Gauge },
  { label: 'Organize or review', icon: ListChecks },
]

export function DashboardView({
  reviewQueue,
  organizedCount,
  onResolve,
  onOpenReview,
}: {
  reviewQueue: AnalyzedFile[]
  organizedCount: number
  onResolve: (id: string, action: 'accepted' | 'ignored', category?: string[]) => void
  onOpenReview: () => void
}) {
  const [selectedId, setSelectedId] = useState(recentActivity[0].id)
  const selected = recentActivity.find((f) => f.id === selectedId) ?? recentActivity[0]

  return (
    <div className="flex flex-col gap-6">
      <Hero />

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <StatCard icon={CheckCircle2} label="Files Organized" value={organizedCount.toString()} hint="+12 today" />
        <StatCard
          icon={Inbox}
          label="Needs Review"
          value={reviewQueue.length.toString()}
          hint={`Below ${AUTO_THRESHOLD}% threshold`}
          tone="warning"
        />
        <StatCard icon={Gauge} label="AI Confidence" value="94%" hint="Average, last 7 days" />
        <StatCard icon={Layers} label="Files Processed" value="342" hint="Since 12 Sep 2026" />
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel>
          <PanelHeader
            title="Recent AI Activity"
            description="Every decision shows what Gemma understood and how sure it was."
            icon={Sparkles}
          />
          <div className="grid grid-cols-[minmax(0,1.5fr)_minmax(0,1.1fr)_150px_120px] gap-4 border-b border-border px-5 py-2.5 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            <span>File</span>
            <span>AI understanding</span>
            <span>Confidence</span>
            <span>Status</span>
          </div>
          <ul>
            {recentActivity.map((file) => (
              <li key={file.id} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => setSelectedId(file.id)}
                  aria-pressed={file.id === selectedId}
                  className={cn(
                    'grid w-full grid-cols-[minmax(0,1.5fr)_minmax(0,1.1fr)_150px_120px] items-center gap-4 px-5 py-3.5 text-left transition-colors focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring',
                    file.id === selectedId ? 'bg-surface-2' : 'hover:bg-surface-2/50',
                  )}
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <FileIcon kind={file.kind} />
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-[13px] text-foreground">{file.original}</span>
                      <span className="mt-0.5 flex items-center gap-1 truncate text-xs text-muted-foreground">
                        <ArrowRight className="size-3 shrink-0" aria-hidden />
                        <span className="truncate">{file.suggested}</span>
                      </span>
                    </span>
                  </span>
                  <span className="min-w-0">
                    {file.status === 'review' ? (
                      <span className="text-sm font-medium text-warning">Review Required</span>
                    ) : (
                      <CategoryPath path={file.category} />
                    )}
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">{file.docType}</span>
                  </span>
                  <ConfidenceMeter value={file.confidence} />
                  <span>
                    <StatusBadge status={file.status} />
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </Panel>

        <InsightPanel file={selected} />
      </div>

      <Panel>
        <PanelHeader
          title={
            reviewQueue.length > 0
              ? `${reviewQueue.length} file${reviewQueue.length === 1 ? '' : 's'} need your decision`
              : 'Nothing waiting for you'
          }
          description={`FileMind doesn't blindly trust AI. Anything below ${AUTO_THRESHOLD}% confidence waits for your decision.`}
          icon={Inbox}
          action={
            <FmButton size="sm" variant="ghost" onClick={onOpenReview}>
              Open Review Queue
              <ArrowRight className="size-3.5" aria-hidden />
            </FmButton>
          }
        />
        {reviewQueue.length > 0 ? (
          <ul className="divide-y divide-border">
            {reviewQueue.map((file) => (
              <ReviewItem key={file.id} file={file} onResolve={onResolve} />
            ))}
          </ul>
        ) : (
          <p className="px-5 py-8 text-center text-sm text-muted-foreground">
            All caught up. New low-confidence files will appear here.
          </p>
        )}
      </Panel>
    </div>
  )
}

function Hero() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <Panel className="relative overflow-hidden bg-gradient-to-br from-card via-card to-primary/[0.06] p-7">
        <p className="flex items-center gap-2 text-xs font-medium text-primary">
          <ShieldCheck className="size-3.5" aria-hidden />
          Private by design · Nothing leaves this device
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight text-balance text-foreground">
          Your files, understood.
        </h1>
        <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground text-pretty">
          Local AI that understands, organizes and helps you find your files.
        </p>

        <ol className="mt-7 flex flex-wrap items-center gap-2" aria-label="How FileMind works">
          {pipeline.map(({ label, icon: Icon }, i) => (
            <li key={label} className="flex items-center gap-2">
              <span className="flex items-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-foreground/90">
                <Icon className="size-3.5 text-primary" aria-hidden />
                {label}
              </span>
              {i < pipeline.length - 1 ? (
                <ArrowRight className="size-3.5 text-muted-foreground/60" aria-hidden />
              ) : null}
            </li>
          ))}
        </ol>
      </Panel>

      <Panel className="flex flex-col justify-between p-6">
        <div>
          <div className="flex items-center justify-between">
            <span className="flex size-11 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <FolderOpen className="size-5" aria-hidden />
            </span>
            <span className="flex items-center gap-2 rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
              <span className="relative flex size-1.5">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
                <span className="relative inline-flex size-1.5 rounded-full bg-primary" />
              </span>
              Live
            </span>
          </div>
          <p className="mt-4 text-lg font-semibold text-foreground">Downloads</p>
          <p className="text-sm text-muted-foreground">Watching for new files</p>
          <p className="mt-3 font-mono text-xs text-muted-foreground">C:\Users\Aarav\Downloads</p>
        </div>
        <div className="mt-5 flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">Last file 2 min ago</span>
          <FmButton size="sm">
            <FolderOpen className="size-3.5" aria-hidden />
            Open Folder
          </FmButton>
        </div>
      </Panel>
    </div>
  )
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  tone = 'default',
}: {
  icon: LucideIcon
  label: string
  value: string
  hint: string
  tone?: 'default' | 'warning'
}) {
  return (
    <Panel className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{label}</p>
        <Icon className={cn('size-4', tone === 'warning' ? 'text-warning' : 'text-muted-foreground')} aria-hidden />
      </div>
      <p
        className={cn(
          'mt-3 text-3xl font-semibold tracking-tight tabular-nums',
          tone === 'warning' ? 'text-warning' : 'text-foreground',
        )}
      >
        {value}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
    </Panel>
  )
}

function InsightPanel({ file }: { file: AnalyzedFile }) {
  const tone = confidenceTone(file.confidence)
  return (
    <Panel className="flex flex-col" aria-live="polite">
      <PanelHeader title="AI Understanding" description="Why Gemma made this decision" icon={Brain} />
      <div className="flex items-center gap-3 border-b border-border px-5 py-4">
        <FileIcon kind={file.kind} size="lg" />
        <div className="min-w-0">
          <p className="truncate font-mono text-[13px] text-foreground">{file.original}</p>
          <p className="text-xs text-muted-foreground">
            {file.size} · received {file.receivedAgo}
          </p>
        </div>
      </div>

      <dl className="flex flex-1 flex-col gap-4 px-5 py-4">
        <InsightRow label="Document Type">
          <span className="text-sm text-foreground">{file.docType}</span>
        </InsightRow>
        <InsightRow label="Topics">
          <span className="flex flex-wrap gap-1.5">
            {file.topics.map((t) => (
              <TopicChip key={t}>{t}</TopicChip>
            ))}
          </span>
        </InsightRow>
        <InsightRow label="Suggested Location">
          <CategoryPath path={file.category} />
        </InsightRow>
        <InsightRow label="Suggested Name">
          <span className="break-all font-mono text-xs text-foreground">{file.suggested}</span>
        </InsightRow>
        <InsightRow label="Confidence">
          <div className="flex items-baseline gap-2">
            <span
              className={cn(
                'text-2xl font-semibold tabular-nums',
                tone === 'high' ? 'text-primary' : tone === 'medium' ? 'text-warning' : 'text-destructive',
              )}
            >
              {file.confidence}%
            </span>
            <span className="text-xs text-muted-foreground">
              {file.confidence >= AUTO_THRESHOLD ? 'Above threshold · auto-organized' : 'Below threshold · sent to review'}
            </span>
          </div>
        </InsightRow>
        <InsightRow label="Reason">
          <blockquote className="border-l-2 border-primary/50 pl-3 text-sm leading-relaxed text-foreground/90">
            {file.reason}
          </blockquote>
        </InsightRow>
      </dl>

      <footer className="flex items-center gap-2 border-t border-border px-5 py-3 text-xs text-muted-foreground">
        <ShieldCheck className="size-3.5 text-primary" aria-hidden />
        Processed locally by Gemma 4 in {file.processedIn}
      </footer>
    </Panel>
  )
}

function InsightRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</dt>
      <dd className="mt-1.5">{children}</dd>
    </div>
  )
}
