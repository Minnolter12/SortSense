'use client'

import { useRef, useState } from 'react'
import { initialReviewQueue } from '@/lib/filemind-data'
import { Sidebar, navItems, type PageId } from './sidebar'
import { TopBar } from './top-bar'
import { DashboardView } from './dashboard-view'
import { ReviewView } from './review-view'
import { SearchView } from './search-view'
import { ActivityView } from './activity-view'
import { SettingsView } from './settings-view'
import { FilesView } from './files-view'

export function AppShell() {
  const [page, setPage] = useState<PageId>('dashboard')
  const [reviewQueue, setReviewQueue] = useState(initialReviewQueue)
  const [resolved, setResolved] = useState(0)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchKey, setSearchKey] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  const navigate = (id: PageId) => {
    setPage(id)
    scrollRef.current?.scrollTo({ top: 0 })
  }

  const [organizedCount, setOrganizedCount] = useState(127)

  const resolve = (id: string, action: 'accepted' | 'ignored') => {
    setReviewQueue((q) => q.filter((f) => f.id !== id))
    setResolved((n) => n + 1)
    if (action === 'accepted') setOrganizedCount((n) => n + 1)
  }

  const title = navItems.find((n) => n.id === page)?.label ?? 'Dashboard'

  return (
    <main className="flex min-h-dvh items-center justify-center p-0 lg:p-6">
      <div className="flex h-dvh w-full max-w-[1440px] flex-col overflow-hidden bg-background lg:h-[min(900px,calc(100dvh-3rem))] lg:rounded-xl lg:border lg:border-border lg:shadow-2xl lg:shadow-black/60">
        <div className="flex h-8 shrink-0 items-center gap-2 border-b border-sidebar-border bg-sidebar px-3" aria-hidden>
          <span className="size-3 rounded-full bg-[#3a414b]" />
          <span className="size-3 rounded-full bg-[#3a414b]" />
          <span className="size-3 rounded-full bg-[#3a414b]" />
          <span className="flex-1 text-center text-xs text-muted-foreground">FileMind</span>
          <span className="w-[52px]" />
        </div>

        <div className="flex min-h-0 flex-1">
          <Sidebar current={page} onNavigate={navigate} reviewCount={reviewQueue.length} />

          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar
              title={title}
              onSettings={() => navigate('settings')}
              onSearch={(q) => {
                setSearchQuery(q)
                setSearchKey((k) => k + 1)
                navigate('search')
              }}
            />
            <div ref={scrollRef} className="fm-scroll min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto max-w-[1160px] px-8 py-7">
                {page === 'dashboard' && (
                  <DashboardView
                    reviewQueue={reviewQueue}
                    organizedCount={organizedCount}
                    onResolve={resolve}
                    onOpenReview={() => navigate('review')}
                  />
                )}
                {page === 'files' && <FilesView />}
                {page === 'review' && (
                  <ReviewView reviewQueue={reviewQueue} resolvedCount={resolved} onResolve={resolve} />
                )}
                {page === 'search' && <SearchView key={searchKey} initialQuery={searchQuery} />}
                {page === 'activity' && <ActivityView />}
                {page === 'settings' && <SettingsView />}
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}
