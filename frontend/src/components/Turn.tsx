import { ArrowClockwise, CaretDown, Check, CircleNotch, Copy, Sparkle, User, Warning } from '@phosphor-icons/react'
import { Fragment, useState, type ReactNode } from 'react'

import type { Source } from '../api'
import { clockTime, hostOf, shortModel } from '../format'
import type { Turn as TurnData } from '../useThread'
import { Skeleton } from './ui'

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g

export function Turn({ turn, onAskAgain }: { turn: TurnData; onAskAgain: (question: string) => void }) {
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [activeRef, setActiveRef] = useState<number | null>(null)
  const sources = turn.result?.sources ?? []
  const citable = new Set(turn.retrieved.map((source) => source.ref))
  const streaming = turn.status === 'streaming'

  // Clicking [n] in the answer opens the source list with that link highlighted.
  function cite(ref: number) {
    setSourcesOpen(true)
    setActiveRef(ref)
  }

  return (
    <li className="animate-fade-in flex flex-col gap-6">
      <Message
        avatar={<User size={15} aria-hidden />}
        name="You"
        time={turn.createdAt}
      >
        <p className="text-[0.9375rem] leading-relaxed whitespace-pre-line">{turn.question}</p>
      </Message>

      <Message
        avatar={<Sparkle size={15} weight="fill" aria-hidden />}
        accent
        name="Inbox assistant"
        time={turn.createdAt}
      >
        {turn.status === 'retrieving' && (
          <div className="flex flex-col gap-2.5 pt-0.5" aria-label="Searching your inbox">
            <p className="flex items-center gap-2 text-sm text-ink-muted">
              <CircleNotch size={14} aria-hidden className="animate-spin text-accent" /> Searching your inbox
            </p>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        )}

        {streaming && !turn.answer && (
          <p className="text-sm text-ink-muted">
            Reading {turn.retrieved.length} {turn.retrieved.length === 1 ? 'passage' : 'passages'}
          </p>
        )}

        {turn.answer && (
          <p
            className={`max-w-[72ch] text-[0.96875rem] leading-[1.75] whitespace-pre-line ${streaming ? 'caret' : ''}`}
            aria-busy={streaming}
          >
            {renderCitations(turn.answer, citable, activeRef, cite)}
          </p>
        )}

        {turn.status === 'error' && (
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Warning size={16} aria-hidden className="shrink-0" />
            <span>{turn.error}</span>
            <button type="button" onClick={() => onAskAgain(turn.question)} className="font-medium text-accent-ink hover:underline">
              Try again
            </button>
          </p>
        )}

        {(turn.status === 'done' || turn.status === 'stopped') && (
          <TurnFooter
            turn={turn}
            sourceCount={sources.length}
            sourcesOpen={sourcesOpen}
            onToggleSources={() => setSourcesOpen((open) => !open)}
            onAskAgain={() => onAskAgain(turn.question)}
          />
        )}

        {sourcesOpen && sources.length > 0 && <SourceLinks sources={sources} activeRef={activeRef} />}
      </Message>
    </li>
  )
}

function Message({
  avatar,
  accent = false,
  name,
  time,
  children,
}: {
  avatar: ReactNode
  accent?: boolean
  name: string
  time: number
  children: ReactNode
}) {
  return (
    <div className="flex gap-3">
      <span
        aria-hidden
        className={`flex size-7 shrink-0 items-center justify-center rounded-full ${
          accent ? 'bg-accent text-on-accent' : 'bg-surface-muted text-ink-muted'
        }`}
      >
        {avatar}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="flex items-baseline gap-2 text-sm leading-7">
          <span className="font-semibold">{name}</span>
          <time className="text-xs text-ink-muted tabular-nums">{clockTime(time)}</time>
        </p>
        {children}
      </div>
    </div>
  )
}

function TurnFooter({
  turn,
  sourceCount,
  sourcesOpen,
  onToggleSources,
  onAskAgain,
}: {
  turn: TurnData
  sourceCount: number
  sourcesOpen: boolean
  onToggleSources: () => void
  onAskAgain: () => void
}) {
  const [copied, setCopied] = useState(false)
  const meta = turn.result?.meta

  async function copy() {
    await navigator.clipboard.writeText(turn.answer)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const action =
    'tap inline-flex h-7 items-center gap-1 rounded-md px-2 text-xs font-medium text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink'

  return (
    <div className="-ml-2 flex flex-wrap items-center gap-x-0.5 gap-y-1">
      {sourceCount > 0 && (
        <button type="button" onClick={onToggleSources} aria-expanded={sourcesOpen} className={action}>
          Sources ({sourceCount})
          <CaretDown size={12} aria-hidden className={`transition-transform duration-200 ${sourcesOpen ? 'rotate-180' : ''}`} />
        </button>
      )}
      {turn.answer && (
        <button type="button" onClick={copy} className={action}>
          {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      )}
      <button type="button" onClick={onAskAgain} className={action}>
        <ArrowClockwise size={14} aria-hidden /> Ask again
      </button>
      <span className="ml-1.5 text-xs text-ink-muted tabular-nums">
        {turn.status === 'stopped'
          ? 'Stopped'
          : meta && `${(meta.latency_ms / 1000).toFixed(1)}s · ${shortModel(meta.model)}`}
      </span>
      {meta?.search_query && (
        <span className="ml-1.5 min-w-0 basis-full truncate pl-2 text-xs text-ink-muted sm:basis-auto">
          Searched for “{meta.search_query}”
        </span>
      )}
    </div>
  )
}

/** Plain numbered links, like footnotes. Hover shows the exact passage that was used. */
function SourceLinks({ sources, activeRef }: { sources: Source[]; activeRef: number | null }) {
  return (
    <ol aria-label="Sources" className="animate-fade-in flex flex-col gap-0.5 text-sm">
      {sources.map((source) => (
        <li
          key={source.ref}
          title={source.snippet}
          className={`flex min-w-0 items-baseline gap-2 rounded-md px-2 py-1 -ml-2 transition-colors duration-200 ${
            activeRef === source.ref ? 'bg-accent-soft' : ''
          }`}
        >
          <span className="w-4 shrink-0 text-right text-xs text-ink-muted tabular-nums">{source.ref}.</span>
          {source.url ? (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="truncate text-accent-ink underline decoration-accent/40 underline-offset-2 hover:decoration-accent"
            >
              {source.title}
            </a>
          ) : (
            <span className="truncate">{source.title}</span>
          )}
          <span className="shrink-0 text-xs text-ink-muted">
            {source.url ? hostOf(source.url) : source.source_type === 'file' ? 'File' : 'Note'} · {Math.round(source.score * 100)}% match
          </span>
        </li>
      ))}
    </ol>
  )
}

/** Turns [n] and [1, 3] markers into small buttons that reveal the matching source. */
function renderCitations(text: string, refs: Set<number>, activeRef: number | null, onSelect: (ref: number) => void) {
  const parts: ReactNode[] = []
  let last = 0
  for (const match of text.matchAll(CITATION)) {
    parts.push(text.slice(last, match.index))
    const numbers = match[1].split(',').map((n) => Number(n.trim()))
    parts.push(
      <Fragment key={match.index}>
        {numbers.map((n) =>
          refs.has(n) ? (
            <button
              key={n}
              type="button"
              onClick={() => onSelect(n)}
              aria-label={`Show source ${n}`}
              className={`hit mx-0.5 inline-flex h-[1.125rem] min-w-[1.125rem] -translate-y-px items-center justify-center rounded px-1 align-middle text-[0.6875rem] font-semibold tabular-nums transition-colors duration-150 ${
                activeRef === n ? 'bg-accent text-on-accent' : 'bg-accent-soft text-accent-ink hover:bg-accent hover:text-on-accent'
              }`}
            >
              {n}
            </button>
          ) : (
            <span key={n}>[{n}]</span>
          ),
        )}
      </Fragment>,
    )
    last = match.index + match[0].length
  }
  parts.push(text.slice(last))
  return parts
}
