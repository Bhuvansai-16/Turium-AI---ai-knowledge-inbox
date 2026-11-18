import { ArrowUp, CaretDown, Plus, Stop } from '@phosphor-icons/react'
import type { FormEvent, KeyboardEvent, RefObject } from 'react'

import { shortModel } from '../format'
import { useSettings } from '../hooks'

const MIN_CHARS = 3
const MAX_CHARS = 1000

export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  model,
  onModelChange,
  onAdd,
  inputRef,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: (question: string) => void
  onStop: () => void
  busy: boolean
  /** Chat model for the next question; one of the models enabled in Settings. */
  model: string | null
  onModelChange: (model: string) => void
  onAdd: () => void
  inputRef: RefObject<HTMLTextAreaElement | null>
}) {
  const { data: settings } = useSettings()
  const models = settings?.chat_models ?? []
  const question = value.trim()
  const canAsk = question.length >= MIN_CHARS && !busy

  function submit(event?: FormEvent) {
    event?.preventDefault()
    if (canAsk) onSubmit(question)
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="rounded-2xl border border-line bg-bg px-3 pt-2.5 pb-2 shadow-panel transition-colors duration-150 focus-within:border-accent">
        <label htmlFor="composer" className="sr-only">
          Ask a question about your saved items
        </label>
        <textarea
          id="composer"
          ref={inputRef}
          rows={1}
          value={value}
          maxLength={MAX_CHARS}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask anything about your saved items..."
          className="max-h-48 min-h-7 w-full resize-none bg-transparent px-1 text-base leading-relaxed text-ink [field-sizing:content] placeholder:text-ink-muted focus:outline-none sm:text-[0.9375rem]"
        />
        <div className="mt-2 flex items-center gap-1.5">
          <button
            type="button"
            onClick={onAdd}
            aria-label="Add to library"
            title="Add to library"
            className="tap flex size-8 items-center justify-center rounded-lg text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
          >
            <Plus size={18} aria-hidden />
          </button>

          {models.length > 0 && (
            <label className="relative inline-flex h-8 min-w-0 items-center rounded-lg text-xs font-medium text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink">
              <span className="sr-only">Model</span>
              <select
                value={model ?? undefined}
                onChange={(e) => onModelChange(e.target.value)}
                className="h-full max-w-56 cursor-pointer appearance-none truncate bg-transparent pr-6 pl-2 focus:outline-none"
              >
                {models.map((name) => (
                  <option key={name} value={name}>
                    {shortModel(name)}
                  </option>
                ))}
              </select>
              <CaretDown size={12} aria-hidden className="pointer-events-none absolute right-2" />
            </label>
          )}

          <span className="flex-1" />
          {busy ? (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              title="Stop generating"
              className="tap flex size-8 shrink-0 items-center justify-center rounded-lg bg-ink text-bg transition-transform duration-150 active:scale-95"
            >
              <Stop size={14} weight="fill" aria-hidden />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canAsk}
              aria-label="Ask"
              title="Ask (Enter)"
              className="tap flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-on-accent transition-[background-color,transform,opacity] duration-150 hover:bg-accent-hover active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ArrowUp size={16} weight="bold" aria-hidden />
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-ink-muted">Answers use only your saved items and cite their sources.</p>
    </form>
  )
}
