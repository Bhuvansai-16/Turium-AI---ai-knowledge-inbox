import { ArrowClockwise, ArrowRight, Sparkle, Warning, X } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

import type { Item } from '../api'
import { useItems, useRetryItem } from '../hooks'

/**
 * When something added this session finishes, a chip above the question box says so:
 * "Ready: ask about ..." (one click) or "Couldn't add ..." with Retry. Progress itself shows
 * on the sidebar's Library item and in the Library panel.
 */
export function IngestStatus({
  watched,
  onDismiss,
  onAskAbout,
}: {
  watched: string[]
  onDismiss: (id: string) => void
  onAskAbout: (item: Item) => void
}) {
  const { data: items = [] } = useItems()
  const retry = useRetryItem()

  const tracked = watched.map((id) => items.find((item) => item.id === id)).filter((item): item is Item => !!item)
  const ready = tracked.filter((item) => item.status === 'ready')
  const failed = tracked.filter((item) => item.status === 'failed')

  if (ready.length === 0 && failed.length === 0) return null

  return (
    <div className="mb-2 flex flex-wrap gap-2" aria-live="polite">
      {ready.map((item) => (
        <Chip key={item.id} tone="accent" onDismiss={() => onDismiss(item.id)} title={item.title}>
          <button
            type="button"
            onClick={() => {
              onAskAbout(item)
              onDismiss(item.id)
            }}
            className="flex min-w-0 items-center gap-1.5"
          >
            <Sparkle size={14} aria-hidden />
            <span className="truncate">Ready: ask about "{item.title}"</span>
            <ArrowRight size={14} aria-hidden className="shrink-0" />
          </button>
        </Chip>
      ))}

      {failed.map((item) => (
        <Chip key={item.id} onDismiss={() => onDismiss(item.id)} title={item.error ?? undefined}>
          <Warning size={14} aria-hidden className="shrink-0" />
          <span className="truncate">Couldn't add "{item.title}"</span>
          <button
            type="button"
            onClick={() => retry.mutate(item.id)}
            disabled={retry.isPending}
            className="inline-flex shrink-0 items-center gap-1 font-medium text-accent-ink hover:underline"
          >
            <ArrowClockwise size={14} aria-hidden /> Retry
          </button>
        </Chip>
      ))}
    </div>
  )
}

function Chip({
  tone,
  title,
  onDismiss,
  children,
}: {
  tone?: 'accent'
  title?: string
  onDismiss?: () => void
  children: ReactNode
}) {
  return (
    <span
      title={title}
      className={`animate-fade-in inline-flex h-8 max-w-full items-center gap-1.5 rounded-full border px-3 text-xs ${
        tone === 'accent' ? 'border-transparent bg-accent-soft text-accent-ink' : 'border-line bg-surface text-ink'
      }`}
    >
      {children}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="-mr-1 ml-0.5 flex size-5 shrink-0 items-center justify-center rounded-full opacity-70 hover:opacity-100"
        >
          <X size={12} aria-hidden />
        </button>
      )}
    </span>
  )
}
