import {
  ChevronRight,
  FileArchive,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileType2,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { AUTO_THRESHOLD, type FileKind, type FileStatus } from '@/lib/filemind-data'

export function Panel({
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLElement> & { as?: 'section' | 'div' }) {
  return (
    <section
      className={cn('rounded-xl border border-border bg-card', className)}
      {...props}
    >
      {children}
    </section>
  )
}

export function PanelHeader({
  title,
  description,
  icon: Icon,
  action,
}: {
  title: string
  description?: string
  icon?: LucideIcon
  action?: React.ReactNode
}) {
  return (
    <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div className="flex items-start gap-3">
        {Icon ? (
          <span className="mt-0.5 flex size-7 items-center justify-center rounded-md bg-surface-2 text-primary">
            <Icon className="size-4" aria-hidden />
          </span>
        ) : null}
        <div>
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
        </div>
      </div>
      {action}
    </header>
  )
}

const kindStyles: Record<FileKind, { icon: LucideIcon; label: string; className: string }> = {
  pdf: { icon: FileText, label: 'PDF', className: 'text-[#e07a6e] bg-[#e07a6e]/10' },
  image: { icon: FileImage, label: 'Image', className: 'text-[#9db4e8] bg-[#9db4e8]/10' },
  doc: { icon: FileType2, label: 'Document', className: 'text-[#8fb7f0] bg-[#8fb7f0]/10' },
  sheet: { icon: FileSpreadsheet, label: 'Spreadsheet', className: 'text-primary bg-primary/10' },
  archive: { icon: FileArchive, label: 'Archive', className: 'text-warning bg-warning/10' },
}

export function FileIcon({ kind, size = 'md' }: { kind: FileKind; size?: 'sm' | 'md' | 'lg' }) {
  const { icon: Icon, label, className } = kindStyles[kind]
  return (
    <span
      className={cn(
        'flex shrink-0 items-center justify-center rounded-lg',
        size === 'sm' && 'size-7',
        size === 'md' && 'size-9',
        size === 'lg' && 'size-11',
        className,
      )}
    >
      <Icon className={cn(size === 'lg' ? 'size-5' : 'size-4')} aria-hidden />
      <span className="sr-only">{label}</span>
    </span>
  )
}

export function confidenceTone(value: number) {
  if (value >= AUTO_THRESHOLD) return 'high' as const
  if (value >= 65) return 'medium' as const
  return 'low' as const
}

const toneText = { high: 'text-primary', medium: 'text-warning', low: 'text-destructive' }
const toneBar = { high: 'bg-primary', medium: 'bg-warning', low: 'bg-destructive' }

export function ConfidenceMeter({
  value,
  showThreshold = true,
  className,
}: {
  value: number
  showThreshold?: boolean
  className?: string
}) {
  const tone = confidenceTone(value)
  return (
    <div className={cn('flex items-center gap-3', className)}>
      <div
        className="relative h-1.5 w-full min-w-16 overflow-visible rounded-full bg-surface-2"
        role="meter"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="AI confidence"
      >
        <div className={cn('h-full rounded-full', toneBar[tone])} style={{ width: `${value}%` }} />
        {showThreshold ? (
          <span
            className="absolute -top-1 h-3.5 w-px bg-muted-foreground/60"
            style={{ left: `${AUTO_THRESHOLD}%` }}
            aria-hidden
          />
        ) : null}
      </div>
      <span className={cn('w-9 shrink-0 text-right font-mono text-xs tabular-nums', toneText[tone])}>
        {value}%
      </span>
    </div>
  )
}

const statusStyles: Record<FileStatus, { label: string; className: string; dot: string }> = {
  organized: { label: 'Organized', className: 'text-primary bg-primary/10', dot: 'bg-primary' },
  review: { label: 'Needs Review', className: 'text-warning bg-warning/10', dot: 'bg-warning' },
  accepted: { label: 'Accepted', className: 'text-primary bg-primary/10', dot: 'bg-primary' },
  ignored: { label: 'Ignored', className: 'text-muted-foreground bg-surface-2', dot: 'bg-muted-foreground' },
}

export function StatusBadge({ status }: { status: FileStatus }) {
  const s = statusStyles[status]
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium',
        s.className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', s.dot)} aria-hidden />
      {s.label}
    </span>
  )
}

export function CategoryPath({ path, className }: { path: string[]; className?: string }) {
  return (
    <span className={cn('inline-flex flex-wrap items-center gap-1 text-sm text-foreground', className)}>
      {path.map((segment, i) => (
        <span key={segment} className="inline-flex items-center gap-1">
          {i > 0 ? <ChevronRight className="size-3 text-muted-foreground" aria-hidden /> : null}
          <span className={i === path.length - 1 ? 'font-medium' : 'text-muted-foreground'}>{segment}</span>
        </span>
      ))}
    </span>
  )
}

export function TopicChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-border bg-surface-2 px-2 py-0.5 text-xs text-foreground/90">
      {children}
    </span>
  )
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost'

export function FmButton({
  variant = 'secondary',
  size = 'md',
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: 'sm' | 'md' }) {
  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-xs' : 'h-9 px-4 text-sm',
        variant === 'primary' && 'bg-primary text-primary-foreground hover:bg-primary/90',
        variant === 'secondary' && 'border border-input bg-surface-2 text-foreground hover:bg-accent',
        variant === 'ghost' && 'text-muted-foreground hover:bg-surface-2 hover:text-foreground',
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring',
        checked ? 'border-primary bg-primary' : 'border-input bg-surface-2',
      )}
    >
      <span
        className={cn(
          'inline-block size-4 rounded-full transition-transform',
          checked ? 'translate-x-6 bg-primary-foreground' : 'translate-x-1 bg-muted-foreground',
        )}
      />
    </button>
  )
}

export function PageIntro({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string
  title: string
  description: string
  action?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="max-w-2xl">
        {eyebrow ? (
          <p className="text-xs font-medium uppercase tracking-wider text-primary">{eyebrow}</p>
        ) : null}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-balance text-foreground">{title}</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground text-pretty">{description}</p>
      </div>
      {action}
    </div>
  )
}
