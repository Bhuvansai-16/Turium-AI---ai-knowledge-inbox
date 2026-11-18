import { MagnifyingGlass, X } from '@phosphor-icons/react'
import { useEffect, useState, type KeyboardEvent, type RefObject } from 'react'

import type { Item } from '../api'
import { useItems } from '../hooks'
import { AddBox } from './AddBox'
import { Library } from './Library'

const SEARCH_THRESHOLD = 5

/** Slides over the chat from the right: add anything at the top, everything saved below. */
export function LibraryPanel({
  addRef,
  onClose,
  onSaved,
  onAskAbout,
}: {
  addRef: RefObject<HTMLTextAreaElement | null>
  onClose: () => void
  onSaved: (item: Item) => void
  onAskAbout: (item: Item) => void
}) {
  const [filter, setFilter] = useState('')
  const { data: items } = useItems()

  useEffect(() => {
    addRef.current?.focus()
  }, [addRef])

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') onClose()
  }

  return (
    <section
      aria-labelledby="library-title"
      onKeyDown={onKeyDown}
      className="slide-over fixed inset-y-0 right-0 z-30 flex w-full flex-col border-l border-line bg-surface shadow-panel sm:w-[26rem]"
    >
      <header className="flex h-14 shrink-0 items-center gap-2 px-4">
        <h2 id="library-title" className="font-semibold">
          Library
        </h2>
        {items && items.length > 0 && (
          <span className="rounded-md bg-accent-soft px-1.5 text-xs font-medium text-accent-ink tabular-nums">
            {items.length}
          </span>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close library"
          className="tap ml-auto flex size-8 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted hover:text-ink"
        >
          <X size={18} aria-hidden />
        </button>
      </header>

      <div className="px-4 pb-3">
        <AddBox inputRef={addRef} onSaved={onSaved} />
      </div>

      {items && items.length >= SEARCH_THRESHOLD && (
        <div className="px-4 pb-3">
          <div className="relative">
            <MagnifyingGlass
              size={14}
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-muted"
            />
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Search library"
              placeholder="Search library"
              className="h-9 w-full rounded-lg border border-line bg-bg pr-3 pl-8 text-base text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none sm:text-sm"
            />
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
        <Library filter={filter} onAskAbout={onAskAbout} />
      </div>
    </section>
  )
}
