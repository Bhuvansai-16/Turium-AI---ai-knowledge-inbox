import {
  Books,
  CircleNotch,
  GearSix,
  MagnifyingGlass,
  NotePencil,
  SidebarSimple,
  Trash,
  Tray,
  X,
} from '@phosphor-icons/react'
import { useEffect, useState, type ReactNode } from 'react'

import type { ThreadSummary } from '../api'
import { dayGroup } from '../format'
import { useDeleteThread, useItems, useThreads } from '../hooks'
import { Skeleton } from './ui'

const GROUPS = ['Today', 'Yesterday', 'Earlier'] as const

export function Sidebar({
  drawer,
  activeThreadId,
  libraryOpen,
  onHide,
  onNewChat,
  onOpenThread,
  onThreadDeleted,
  onToggleLibrary,
  onOpenSettings,
}: {
  drawer: boolean
  activeThreadId: string | null
  libraryOpen: boolean
  onHide: () => void
  onNewChat: () => void
  onOpenThread: (id: string) => void
  onThreadDeleted: (id: string) => void
  onToggleLibrary: () => void
  onOpenSettings: () => void
}) {
  const [searching, setSearching] = useState(false)
  const [filter, setFilter] = useState('')
  const { data: items } = useItems()
  const indexing = items?.some((item) => item.status === 'pending' || item.status === 'processing')

  function toggleSearch() {
    setSearching((open) => !open)
    setFilter('')
  }

  return (
    <aside
      aria-label="Chats"
      className={`flex w-64 shrink-0 flex-col border-r border-line bg-surface xl:w-72 ${
        drawer ? 'drawer fixed inset-y-0 left-0 z-30 max-w-[86vw] shadow-panel' : ''
      }`}
    >
      <div className="flex h-14 shrink-0 items-center gap-2.5 px-4">
        <span className="flex size-7 items-center justify-center rounded-lg bg-accent text-on-accent">
          <Tray size={16} weight="bold" aria-hidden />
        </span>
        <span className="font-semibold">Knowledge Inbox</span>
        <button
          type="button"
          onClick={onHide}
          aria-label={drawer ? 'Close sidebar' : 'Collapse sidebar'}
          title={drawer ? 'Close' : 'Collapse sidebar'}
          className="tap ml-auto flex size-8 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted hover:text-ink"
        >
          {drawer ? <X size={18} aria-hidden /> : <SidebarSimple size={18} aria-hidden />}
        </button>
      </div>

      <nav aria-label="Main" className="flex flex-col gap-px px-2 pb-3">
        <NavButton icon={<NotePencil size={18} aria-hidden />} onClick={onNewChat}>
          New chat
        </NavButton>
        <NavButton icon={<Books size={18} aria-hidden />} onClick={onToggleLibrary} pressed={libraryOpen}>
          Library
          <span className="ml-auto text-xs text-ink-muted tabular-nums">
            {indexing ? (
              <CircleNotch size={14} aria-label="Indexing" className="animate-spin text-accent" />
            ) : (
              items?.length || ''
            )}
          </span>
        </NavButton>
        <NavButton icon={<MagnifyingGlass size={18} aria-hidden />} onClick={toggleSearch} pressed={searching}>
          Search chats
        </NavButton>
      </nav>

      {searching && (
        <div className="px-3 pb-3">
          <input
            type="search"
            autoFocus
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && toggleSearch()}
            aria-label="Search chats"
            placeholder="Search chat titles"
            className="h-9 w-full rounded-lg border border-line bg-bg px-3 text-base text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none sm:text-sm"
          />
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        <ChatHistory
          filter={filter}
          activeThreadId={activeThreadId}
          onOpen={onOpenThread}
          onDeleted={onThreadDeleted}
        />
      </div>

      <div className="border-t border-line px-2 py-2">
        <NavButton icon={<GearSix size={18} aria-hidden />} onClick={onOpenSettings}>
          Settings
        </NavButton>
      </div>
    </aside>
  )
}

function ChatHistory({
  filter,
  activeThreadId,
  onOpen,
  onDeleted,
}: {
  filter: string
  activeThreadId: string | null
  onOpen: (id: string) => void
  onDeleted: (id: string) => void
}) {
  const { data: threads, isPending, isError } = useThreads()

  if (isPending) {
    return (
      <div className="flex flex-col gap-3 px-3 pt-1" aria-label="Loading chats">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-4 w-4/5" />
        ))}
      </div>
    )
  }
  if (isError) return <p className="px-3 text-sm text-ink-muted">Couldn't load your chats.</p>
  if (threads.length === 0) {
    return <p className="px-3 text-sm leading-relaxed text-ink-muted">Your chats will appear here.</p>
  }

  const needle = filter.trim().toLowerCase()
  const visible = threads.filter((thread) => !needle || thread.title.toLowerCase().includes(needle))
  if (visible.length === 0) return <p className="px-3 text-sm text-ink-muted">No chats match "{filter}".</p>

  return (
    <div className="flex flex-col gap-4">
      {GROUPS.map((group) => {
        const rows = visible.filter((thread) => dayGroup(thread.updated_at) === group)
        if (rows.length === 0) return null
        return (
          <section key={group} aria-label={group}>
            <h3 className="px-3 pb-1 text-xs text-ink-muted">{group}</h3>
            <ul className="flex flex-col gap-px">
              {rows.map((thread) => (
                <ChatRow
                  key={thread.id}
                  thread={thread}
                  active={thread.id === activeThreadId}
                  onOpen={() => onOpen(thread.id)}
                  onDeleted={() => onDeleted(thread.id)}
                />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

const CONFIRM_MS = 4000

function ChatRow({
  thread,
  active,
  onOpen,
  onDeleted,
}: {
  thread: ThreadSummary
  active: boolean
  onOpen: () => void
  onDeleted: () => void
}) {
  const [confirming, setConfirming] = useState(false)
  const remove = useDeleteThread()

  useEffect(() => {
    if (!confirming) return
    const timer = setTimeout(() => setConfirming(false), CONFIRM_MS)
    return () => clearTimeout(timer)
  }, [confirming])

  return (
    <li
      className={`group flex items-center rounded-lg pr-1 transition-colors duration-150 ${
        active ? 'bg-surface-muted' : 'hover:bg-surface-muted'
      }`}
    >
      <button
        type="button"
        onClick={onOpen}
        aria-current={active ? 'page' : undefined}
        title={thread.title}
        className={`min-w-0 flex-1 truncate py-1.5 pl-3 text-left text-sm ${active ? 'font-medium' : ''}`}
      >
        {thread.title}
      </button>
      <button
        type="button"
        onClick={() => (confirming ? remove.mutate(thread.id, { onSuccess: onDeleted }) : setConfirming(true))}
        onBlur={() => setConfirming(false)}
        disabled={remove.isPending}
        aria-label={confirming ? `Confirm delete chat ${thread.title}` : `Delete chat ${thread.title}`}
        title={confirming ? 'Click again to delete' : 'Delete chat'}
        className={`tap flex h-6 shrink-0 items-center justify-center gap-1 rounded-md px-1.5 text-xs transition-opacity hover:bg-surface focus-visible:opacity-100 ${
          confirming ? 'bg-surface font-medium opacity-100' : 'text-ink-muted opacity-0 group-hover:opacity-100'
        }`}
      >
        <Trash size={14} aria-hidden />
        {confirming && 'Delete?'}
      </button>
    </li>
  )
}

function NavButton({
  icon,
  onClick,
  pressed,
  children,
}: {
  icon: ReactNode
  onClick: () => void
  pressed?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={pressed}
      className={`tap flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm transition-colors duration-150 hover:bg-surface-muted ${
        pressed ? 'bg-surface-muted' : ''
      }`}
    >
      {icon}
      {children}
    </button>
  )
}
