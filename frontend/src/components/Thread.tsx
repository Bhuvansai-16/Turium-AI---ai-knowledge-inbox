import { ArrowRight, Plugs, Plus } from '@phosphor-icons/react'
import { useEffect, useRef } from 'react'

import { useHealth, useItems } from '../hooks'
import type { Turn as TurnData } from '../useThread'
import { Turn } from './Turn'
import { Button, Skeleton } from './ui'

const NEAR_BOTTOM_PX = 120
const SUGGESTIONS = 3

export function Thread({
  turns,
  loading,
  onAsk,
  onAdd,
  onOpenSettings,
}: {
  turns: TurnData[]
  loading: boolean
  onAsk: (question: string) => void
  onAdd: () => void
  onOpenSettings: () => void
}) {
  const scroller = useRef<HTMLDivElement>(null)
  const lastAnswer = turns.at(-1)?.answer

  // Follow the streaming answer, unless the reader has scrolled up to look at something.
  useEffect(() => {
    const el = scroller.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX) el.scrollTop = el.scrollHeight
  }, [lastAnswer])

  // A new question or a reopened chat jumps to the bottom.
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight })
  }, [turns.length])

  return (
    <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
      <h2 className="sr-only">Conversation</h2>
      {/* Announce state changes once, rather than having screen readers read every streamed token. */}
      <p className="sr-only" aria-live="polite">
        {announcement(turns.at(-1))}
      </p>
      {loading ? (
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-8 sm:px-6" aria-label="Loading chat">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      ) : turns.length === 0 ? (
        <EmptyState onAsk={onAsk} onAdd={onAdd} onOpenSettings={onOpenSettings} />
      ) : (
        <ol className="mx-auto flex w-full max-w-3xl flex-col gap-10 px-4 py-8 sm:px-6">
          {turns.map((turn) => (
            <Turn key={turn.id} turn={turn} onAskAgain={onAsk} />
          ))}
        </ol>
      )}
    </div>
  )
}

function announcement(turn: TurnData | undefined): string {
  if (!turn) return ''
  if (turn.status === 'retrieving') return 'Searching your library'
  if (turn.status === 'streaming') return 'Writing the answer'
  if (turn.status === 'stopped') return 'Stopped'
  if (turn.status === 'error') return `Answer failed: ${turn.error}`
  const cited = turn.result?.sources.length ?? 0
  return `Answer ready, ${cited} ${cited === 1 ? 'source' : 'sources'} cited`
}

function greeting(): string {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
}

function EmptyState({
  onAsk,
  onAdd,
  onOpenSettings,
}: {
  onAsk: (q: string) => void
  onAdd: () => void
  onOpenSettings: () => void
}) {
  const { data: health } = useHealth()
  const { data: items } = useItems()
  const ready = items?.filter((item) => item.status === 'ready') ?? []

  // Specific items first; with two or more, one question about the whole library.
  const suggestions = ready.slice(0, SUGGESTIONS).map((item) => `What are the key points of "${item.title}"?`)
  if (ready.length >= 2) suggestions.splice(SUGGESTIONS - 1, 1, 'What do my saved items have in common?')

  return (
    <div className="mx-auto flex min-h-full w-full max-w-2xl flex-col justify-center gap-8 px-4 py-10 sm:px-6">
      <div>
        <h2 className="text-3xl font-semibold tracking-tight">{greeting()}</h2>
        <p className="mt-2 text-ink-muted">
          {ready.length > 0
            ? `You have ${ready.length} saved ${ready.length === 1 ? 'item' : 'items'}. Try a question below, or ask your own.`
            : 'Add notes, links and documents to your library, then ask questions about them.'}
        </p>
      </div>

      {health && !health.llm_configured ? (
        <div className="flex flex-col items-start gap-3 rounded-2xl border border-line p-5">
          <Plugs size={22} aria-hidden className="text-accent" />
          <div>
            <h3 className="font-semibold">Connect an AI model to get started</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">
              Paste an OpenAI or Gemini API key, or connect any OpenAI-compatible server, such as Ollama for free local models.
            </p>
          </div>
          <Button type="button" onClick={onOpenSettings}>
            Open settings
          </Button>
        </div>
      ) : items && items.length === 0 ? (
        <Button type="button" onClick={onAdd} className="self-start">
          <Plus size={16} aria-hidden /> Add to your library
        </Button>
      ) : (
        suggestions.length > 0 && (
          <ul className="flex flex-col gap-2">
            {suggestions.map((suggestion, i) => (
              <li key={suggestion} className="stagger" style={{ '--i': i } as React.CSSProperties}>
                <button
                  type="button"
                  onClick={() => onAsk(suggestion)}
                  className="group flex w-full items-center justify-between gap-3 rounded-xl border border-line px-4 py-3 text-left text-sm text-ink-muted transition-colors duration-150 hover:border-accent hover:text-ink"
                >
                  <span className="truncate">{suggestion}</span>
                  <ArrowRight
                    size={14}
                    aria-hidden
                    className="shrink-0 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-accent-ink"
                  />
                </button>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  )
}
