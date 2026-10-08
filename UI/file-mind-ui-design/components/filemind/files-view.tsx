import { Folder } from 'lucide-react'
import { fileCategories, recentActivity } from '@/lib/filemind-data'
import { CategoryPath, ConfidenceMeter, FileIcon, PageIntro, Panel, PanelHeader } from './primitives'

export function FilesView() {
  const organized = recentActivity.filter((f) => f.status === 'organized')
  return (
    <div className="flex flex-col gap-6">
      <PageIntro
        eyebrow="Library"
        title="Organized by meaning"
        description="Folders FileMind created from what your files are actually about."
      />

      <div className="grid grid-cols-3 gap-4">
        {fileCategories.map((c) => (
          <Panel key={c.name} className="flex items-center gap-4 p-4">
            <span className="flex size-10 items-center justify-center rounded-lg bg-surface-2 text-primary">
              <Folder className="size-5" aria-hidden />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{c.name}</p>
              <p className="truncate text-xs text-muted-foreground">{c.sub}</p>
            </div>
            <span className="font-mono text-sm tabular-nums text-foreground">{c.count}</span>
          </Panel>
        ))}
      </div>

      <Panel>
        <PanelHeader title="Recently organized" description="Renamed and moved automatically" />
        <ul className="divide-y divide-border">
          {organized.map((f) => (
            <li key={f.id} className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_150px_80px] items-center gap-4 px-5 py-3.5">
              <span className="flex min-w-0 items-center gap-3">
                <FileIcon kind={f.kind} />
                <span className="min-w-0">
                  <span className="block truncate font-mono text-[13px] text-foreground">{f.suggested}</span>
                  <span className="block truncate text-xs text-muted-foreground">was {f.original}</span>
                </span>
              </span>
              <CategoryPath path={f.category} />
              <ConfidenceMeter value={f.confidence} />
              <span className="text-right text-xs text-muted-foreground">{f.size}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}
