import {
  ArrowClockwise,
  ArrowSquareOut,
  ChatCircleText,
  CircleNotch,
  DotsThree,
  Trash,
  Warning,
} from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import type { Item } from '../api'
import { dayGroup, hostOf, timeAgo } from '../format'
import { useDeleteItem, useItems, useRetryItem } from '../hooks'
import { Skeleton } from './ui'

const GROUPS = ['Today', 'Yesterday', 'Earlier'] as const

/** Saved items as a quiet list grouped by day, like chat history. Details open per row. */
export function Library({ filter, onAskAbout }: { filter: string; onAskAbout: (item: Item) => void }) {
  const { data: items, isPending, isError, error, refetch } = useItems()
  const [openId, setOpenId] = useState<string | null>(null)

  if (isPending) {
    return (
      <div className="flex flex-col gap-3 px-3 pt-2" aria-label="Loading library">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-4 w-4/5" />
        ))}
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col items-start gap-1 px-3 text-sm">
        <p>{error.message}</p>
        <button type="button" onClick={() => refetch()} className="font-medium text-accent-ink hover:underline">
          Try again
        </button>
      </div>
    )
  }

  if (items.length === 0) {
    return <p className="px-3 text-sm leading-relaxed text-ink-muted">Nothing saved yet.</p>
  }

  const needle = filter.trim().toLowerCase()
  const visible = items.filter(
    (item) => !needle || `${item.title} ${item.preview} ${item.url ?? ''}`.toLowerCase().includes(needle),
  )
  if (visible.length === 0) {
    return <p className="px-3 text-sm text-ink-muted">No items match "{filter}".</p>
  }

  return (
    <div className="flex flex-col gap-4">
      {GROUPS.map((group) => {
        const rows = visible.filter((item) => dayGroup(item.created_at) === group)
        if (rows.length === 0) return null
        return (
          <section key={group} aria-label={group}>
            <h3 className="px-3 pb-1 text-xs text-ink-muted">{group}</h3>
            <ul className="flex flex-col gap-px">
              {rows.map((item) => (
                <LibraryRow
                  key={item.id}
                  item={item}
                  open={openId === item.id}
                  onToggle={() => setOpenId((id) => (id === item.id ? null : item.id))}
                  onAskAbout={onAskAbout}
                />
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

function LibraryRow({
  item,
  open,
  onToggle,
  onAskAbout,
}: {
  item: Item
  open: boolean
  onToggle: () => void
  onAskAbout: (item: Item) => void
}) {
  const indexing = item.status === 'pending' || item.status === 'processing'
  const failed = item.status === 'failed'
  const ready = item.status === 'ready'
  const detailsId = `item-${item.id}`

  return (
    <li className={`rounded-lg transition-colors duration-150 ${open ? 'bg-surface-muted' : ''}`}>
      <div className="group flex items-center gap-1 rounded-lg pr-1 hover:bg-surface-muted">
        <button
          type="button"
          onClick={ready ? () => onAskAbout(item) : onToggle}
          title={ready ? `Ask about "${item.title}"` : item.title}
          className={`min-w-0 flex-1 truncate py-1.5 pl-3 text-left text-sm ${failed ? 'text-ink-muted' : ''}`}
        >
          {item.title}
        </button>
        {indexing && <CircleNotch size={14} aria-label="Indexing" className="shrink-0 animate-spin text-accent" />}
        {failed && <Warning size={14} aria-label="Failed" className="shrink-0" />}
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          aria-controls={detailsId}
          aria-label={`Details for ${item.title}`}
          className={`tap flex size-6 shrink-0 items-center justify-center rounded-md text-ink-muted transition-opacity hover:bg-surface hover:text-ink focus-visible:opacity-100 ${
            open ? 'opacity-100' : 'opacity-50 group-hover:opacity-100'
          }`}
        >
          <DotsThree size={16} weight="bold" aria-hidden />
        </button>
      </div>

      {open && <RowDetails id={detailsId} item={item} onAskAbout={onAskAbout} />}
    </li>
  )
}

const CONFIRM_MS = 4000
const action =
  'tap inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium transition-colors hover:bg-surface disabled:opacity-50'

function statusLabel(item: Item): string {
  if (item.status === 'ready') return `${item.chunk_count} ${item.chunk_count === 1 ? 'passage' : 'passages'}`
  if (item.status === 'failed') return 'Failed'
  if (item.status === 'processing') return item.source_type === 'url' ? 'Reading page' : 'Indexing'
  return 'Queued'
}

function RowDetails({ id, item, onAskAbout }: { id: string; item: Item; onAskAbout: (item: Item) => void }) {
  const [confirming, setConfirming] = useState(false)
  const remove = useDeleteItem()
  const retry = useRetryItem()

  useEffect(() => {
    if (!confirming) return
    const timer = setTimeout(() => setConfirming(false), CONFIRM_MS)
    return () => clearTimeout(timer)
  }, [confirming])

  return (
    <div id={id} className="flex flex-col gap-2 px-3 pt-0.5 pb-2.5">
      <p className="text-xs text-ink-muted">
        {item.url ? hostOf(item.url) : item.source_type === 'file' ? 'File' : 'Note'} · {timeAgo(item.created_at)} · {statusLabel(item)}
      </p>
      {item.error && (
        <p className="flex gap-1.5 rounded-md bg-surface px-2 py-1.5 text-xs leading-relaxed">
          <Warning size={14} aria-hidden className="mt-px shrink-0" />
          {item.error}
        </p>
      )}
      <div className="-ml-2 flex flex-wrap items-center">
        {item.status === 'ready' && (
          <button type="button" onClick={() => onAskAbout(item)} className={`${action} text-accent-ink`}>
            <ChatCircleText size={14} aria-hidden /> Ask about it
          </button>
        )}
        {item.status === 'failed' && (
          <button
            type="button"
            onClick={() => retry.mutate(item.id)}
            disabled={retry.isPending}
            className={`${action} text-accent-ink`}
          >
            <ArrowClockwise size={14} aria-hidden /> Retry
          </button>
        )}
        {item.url && (
          <a href={item.url} target="_blank" rel="noopener noreferrer" className={`${action} text-ink-muted`}>
            <ArrowSquareOut size={14} aria-hidden /> Open
          </a>
        )}
        <button
          type="button"
          onClick={() => (confirming ? remove.mutate(item.id) : setConfirming(true))}
          onBlur={() => setConfirming(false)}
          disabled={remove.isPending}
          aria-label={confirming ? `Confirm delete ${item.title}` : `Delete ${item.title}`}
          className={`${action} ${confirming ? 'bg-surface text-ink' : 'text-ink-muted'}`}
        >
          <Trash size={14} aria-hidden /> {confirming ? 'Click again to delete' : 'Delete'}
        </button>
      </div>
    </div>
  )
}
