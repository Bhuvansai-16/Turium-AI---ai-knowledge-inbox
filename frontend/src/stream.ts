// Client for POST /query/stream (Server-Sent Events over a POST body, so EventSource can't be used).

import { ApiError, NETWORK_ERROR, type QueryResult, type Source } from './api'

export interface StreamHandlers {
  onThread: (thread: { id: string; title: string }) => void
  onSources: (sources: Source[]) => void
  onToken: (text: string) => void
  onDone: (result: QueryResult) => void
}

export interface StreamRequest {
  question: string
  threadId: string | null
  model: string | null
}

export async function askStream(
  { question, threadId, model }: StreamRequest,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, ...(threadId && { thread_id: threadId }), ...(model && { model }) }),
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError(0, 'network_error', NETWORK_ERROR)
  }

  // Validation, configuration and retrieval errors arrive as normal JSON error responses.
  if (!response.ok || !response.body) {
    const error = (await response.json().catch(() => null))?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? `Request failed with status ${response.status}`,
    )
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value

    let boundary: number
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const event = parseEvent(buffer.slice(0, boundary))
      buffer = buffer.slice(boundary + 2)
      if (!event) continue

      if (event.name === 'thread') handlers.onThread(event.data)
      else if (event.name === 'sources') handlers.onSources(event.data.sources)
      else if (event.name === 'token') handlers.onToken(event.data.text)
      else if (event.name === 'done') return handlers.onDone(event.data)
      else if (event.name === 'error') throw new ApiError(502, event.data.code, event.data.message)
    }
  }
  throw new ApiError(0, 'stream_interrupted', 'The answer stopped before it finished. Try again.')
}

function parseEvent(block: string): { name: string; data: any } | null {
  let name = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) name = line.slice(7)
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  return data ? { name, data: JSON.parse(data) } : null
}
