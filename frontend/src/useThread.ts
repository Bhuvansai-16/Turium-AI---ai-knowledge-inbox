import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { api, type Message, type QueryResult, type Source } from './api'
import { THREADS_KEY } from './hooks'
import { askStream } from './stream'

export type TurnStatus = 'retrieving' | 'streaming' | 'done' | 'stopped' | 'error'

export interface Turn {
  id: string
  question: string
  createdAt: number
  status: TurnStatus
  answer: string
  /** Passages retrieved for this question (arrives before the answer starts). */
  retrieved: Source[]
  /** Final payload; its `sources` are only the passages the answer cites. */
  result?: QueryResult
  error?: string
}

/**
 * The open conversation. New questions stream into turns; the server saves every question and
 * answer to a thread, so past threads can be reopened from the sidebar.
 */
export function useThread() {
  const queryClient = useQueryClient()
  const [threadId, setThreadId] = useState<string | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)
  const threadIdRef = useRef<string | null>(null)
  const controllers = useRef(new Map<string, AbortController>())

  useEffect(() => {
    const active = controllers.current
    return () => active.forEach((controller) => controller.abort())
  }, [])

  const update = useCallback((id: string, patch: (turn: Turn) => Partial<Turn>) => {
    setTurns((all) => all.map((turn) => (turn.id === id ? { ...turn, ...patch(turn) } : turn)))
  }, [])

  const switchTo = useCallback((id: string | null) => {
    controllers.current.forEach((controller) => controller.abort())
    threadIdRef.current = id
    setThreadId(id)
  }, [])

  const ask = useCallback(
    (question: string, model: string | null) => {
      const id = crypto.randomUUID()
      setTurns((all) => [
        ...all,
        { id, question, createdAt: Date.now(), status: 'retrieving', answer: '', retrieved: [] },
      ])

      const controller = new AbortController()
      controllers.current.set(id, controller)
      askStream(
        { question, threadId: threadIdRef.current, model },
        {
          onThread: (thread) => {
            threadIdRef.current = thread.id
            setThreadId(thread.id)
          },
          onSources: (retrieved) => update(id, () => ({ retrieved, status: 'streaming' })),
          onToken: (text) => update(id, (turn) => ({ answer: turn.answer + text, status: 'streaming' })),
          onDone: (result) => update(id, () => ({ status: 'done', answer: result.answer, result })),
        },
        controller.signal,
      )
        .catch((error: Error) => {
          if (!controller.signal.aborted) update(id, () => ({ status: 'error', error: error.message }))
        })
        .finally(() => {
          controllers.current.delete(id)
          queryClient.invalidateQueries({ queryKey: THREADS_KEY })
        })
    },
    [update, queryClient],
  )

  /** Stop generating: keeps whatever text already arrived (the server saves it as stopped). */
  const stop = useCallback(() => {
    controllers.current.forEach((controller) => controller.abort())
    setTurns((all) =>
      all.map((turn) =>
        turn.status === 'retrieving' || turn.status === 'streaming' ? { ...turn, status: 'stopped' } : turn,
      ),
    )
  }, [])

  const startNew = useCallback(() => {
    switchTo(null)
    setTurns([])
  }, [switchTo])

  const open = useCallback(
    async (id: string) => {
      switchTo(id)
      setLoading(true)
      try {
        const thread = await api.thread(id)
        if (threadIdRef.current === id) setTurns(toTurns(thread.messages))
      } catch {
        // Deleted elsewhere or the backend is down: never leave the previous chat on screen
        // under this id, or the next question would be saved to the wrong chat.
        if (threadIdRef.current === id) startNew()
      } finally {
        setLoading(false)
      }
    },
    [switchTo, startNew],
  )

  const busy = turns.some((turn) => turn.status === 'retrieving' || turn.status === 'streaming')
  return { threadId, turns, loading, busy, ask, stop, startNew, open }
}

/** Rebuild saved messages into turns: each question with the answer right after it, if any.
 *  A question can be saved without an answer (the server restarted mid-stream). */
function toTurns(messages: Message[]): Turn[] {
  const turns: Turn[] = []
  messages.forEach((question, i) => {
    if (question.role !== 'user') return
    const next = messages[i + 1]
    const answer = next?.role === 'assistant' ? next : undefined
    turns.push({
      id: String(question.id),
      question: question.content,
      createdAt: Date.parse(question.created_at),
      status: answer ? answer.status : 'stopped',
      answer: answer?.content ?? '',
      retrieved: answer?.sources ?? [],
      result:
        answer?.meta && answer.status === 'done'
          ? { answer: answer.content, sources: answer.sources, meta: answer.meta }
          : undefined,
      error: answer?.status === 'error' ? 'The AI provider stopped responding.' : undefined,
    })
  })
  return turns
}
