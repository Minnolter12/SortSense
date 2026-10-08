'use client'

import { useState } from 'react'
import { Brain, Cpu, FolderOpen, Gauge, Lock, ShieldCheck, SlidersHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'
import { FmButton, PageIntro, Panel, PanelHeader, Toggle } from './primitives'

function SettingRow({
  label,
  description,
  children,
}: {
  label: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-6 px-5 py-4">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        {description ? <p className="mt-0.5 text-xs text-muted-foreground">{description}</p> : null}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

export function SettingsView() {
  const [threshold, setThreshold] = useState(85)
  const [lowAction, setLowAction] = useState<'review' | 'leave'>('review')
  const [toggles, setToggles] = useState({
    autoOrganize: true,
    rename: true,
    undo: true,
    startup: false,
    ocr: true,
  })
  const set = (key: keyof typeof toggles) => (v: boolean) => setToggles((t) => ({ ...t, [key]: v }))

  return (
    <div className="flex flex-col gap-6">
      <PageIntro
        eyebrow="Settings"
        title="Configure FileMind"
        description="Choose what FileMind watches, which local model it uses, and when it's allowed to act on its own."
      />

      <div className="flex items-start gap-4 rounded-xl border border-primary/30 bg-primary/[0.06] p-5">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/15 text-primary">
          <Lock className="size-5" aria-hidden />
        </span>
        <div>
          <p className="text-sm font-semibold text-foreground">Privacy</p>
          <p className="mt-0.5 text-sm text-foreground/80">
            Files are processed locally. No file content is uploaded.
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            Gemma runs on this machine via Ollama. Network access is used only to download model updates.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel>
          <PanelHeader title="Watched Folder" icon={FolderOpen} />
          <div className="divide-y divide-border">
            <SettingRow label="Folder" description="New files here are analyzed automatically">
              <div className="flex items-center gap-2">
                <span className="rounded-md border border-border bg-background px-3 py-1.5 font-mono text-xs text-foreground">
                  C:\Users\Aarav\Downloads
                </span>
                <FmButton size="sm">Change…</FmButton>
              </div>
            </SettingRow>
            <SettingRow label="Organize into" description="Destination root for sorted files">
              <span className="rounded-md border border-border bg-background px-3 py-1.5 font-mono text-xs text-foreground">
                ~\Documents\FileMind
              </span>
            </SettingRow>
            <SettingRow label="Launch at startup" description="Start watching when you sign in">
              <Toggle checked={toggles.startup} onChange={set('startup')} label="Launch at startup" />
            </SettingRow>
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Local AI" icon={Brain} />
          <div className="divide-y divide-border">
            <SettingRow label="AI Model" description="Multimodal, runs fully offline">
              <span className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground">
                <Brain className="size-3.5 text-primary" aria-hidden />
                Gemma 4
              </span>
            </SettingRow>
            <SettingRow label="AI Runtime" description="localhost:11434">
              <span className="flex items-center gap-2 rounded-md border border-border bg-background px-3 py-1.5 text-xs text-foreground">
                <Cpu className="size-3.5 text-primary" aria-hidden />
                Ollama
                <span className="size-1.5 rounded-full bg-primary" aria-hidden />
                <span className="text-primary">Connected</span>
              </span>
            </SettingRow>
            <SettingRow label="Read text in images" description="Use OCR for screenshots and scans">
              <Toggle checked={toggles.ocr} onChange={set('ocr')} label="Read text in images" />
            </SettingRow>
          </div>
        </Panel>

        <Panel className="xl:col-span-2">
          <PanelHeader
            title="Automation"
            description="Confidence-based rules decide when FileMind acts alone and when it asks you."
            icon={SlidersHorizontal}
          />
          <div className="divide-y divide-border">
            <div className="px-5 py-5">
              <div className="flex items-center justify-between">
                <label htmlFor="threshold" className="flex items-center gap-2 text-sm font-medium text-foreground">
                  <Gauge className="size-4 text-primary" aria-hidden />
                  Auto-organize threshold
                </label>
                <span className="font-mono text-lg font-semibold tabular-nums text-primary">{threshold}%</span>
              </div>
              <input
                id="threshold"
                type="range"
                min={50}
                max={99}
                value={threshold}
                onChange={(e) => setThreshold(Number(e.target.value))}
                className="mt-4 w-full accent-[#7fd1c1]"
              />
              <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                <span>More automatic</span>
                <span>
                  Files below <span className="text-foreground">{threshold}%</span> go to{' '}
                  {lowAction === 'review' ? 'the Review Queue' : 'stay in place'}
                </span>
                <span>More cautious</span>
              </div>
            </div>

            <SettingRow label="Low-confidence action" description="What happens when Gemma isn't sure">
              <div role="radiogroup" aria-label="Low-confidence action" className="flex rounded-lg border border-input bg-background p-0.5">
                {(
                  [
                    ['review', 'Review Queue'],
                    ['leave', 'Leave in place'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={lowAction === value}
                    onClick={() => setLowAction(value)}
                    className={cn(
                      'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                      lowAction === value ? 'bg-surface-2 text-foreground' : 'text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </SettingRow>
            <SettingRow label="Auto-organize" description="Move high-confidence files without asking">
              <Toggle checked={toggles.autoOrganize} onChange={set('autoOrganize')} label="Auto-organize" />
            </SettingRow>
            <SettingRow label="Suggest meaningful filenames" description="Rename files using detected content">
              <Toggle checked={toggles.rename} onChange={set('rename')} label="Suggest meaningful filenames" />
            </SettingRow>
            <SettingRow label="Safe mode" description="Keep an undo record for every move and rename">
              <span className="flex items-center gap-3">
                <ShieldCheck className="size-4 text-primary" aria-hidden />
                <Toggle checked={toggles.undo} onChange={set('undo')} label="Safe mode" />
              </span>
            </SettingRow>
          </div>
        </Panel>
      </div>
    </div>
  )
}
