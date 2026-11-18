// Typed client for the FastAPI backend. Shapes mirror backend/app/schemas.py.

export type ItemStatus = 'pending' | 'processing' | 'ready' | 'failed'
export type SourceType = 'note' | 'url' | 'file'

export interface Item {
  id: string
  title: string
  source_type: SourceType
  url: string | null
  status: ItemStatus
  error: string | null
  preview: string
  chunk_count: number
  created_at: string
}

export interface Source {
  ref: number
  item_id: string
  title: string
  source_type: SourceType
  url: string | null
  snippet: string
  score: number
}

export interface QueryResult {
  answer: string
  sources: Source[]
  meta: { model: string; retrieved: number; latency_ms: number; search_query?: string | null }
}

export interface Health {
  status: string
  db: string
  llm_configured: boolean
  provider: ProviderName
  chat_model: string
  embed_model: string
}

export type ProviderName = 'openai' | 'gemini' | 'custom'

export interface ProviderPreset {
  label: string
  base_url: string
  chat_model: string
  embed_model: string
  needs_key: boolean
}

export interface Settings {
  provider: ProviderName
  base_url: string
  chat_model: string
  /** Chat models offered in the question box's picker (the default first). */
  chat_models: string[]
  embed_model: string
  api_key_set: boolean
  api_key_hint: string | null
  /** Masked key saved for each provider, so switching back needs no key. */
  key_hints: Partial<Record<ProviderName, string>>
  presets: Record<ProviderName, ProviderPreset>
}

export interface SettingsInput {
  provider: ProviderName
  base_url: string
  api_key?: string
  chat_model: string
  chat_models: string[]
  embed_model: string
}

export interface ThreadSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  status: 'done' | 'stopped' | 'error'
  sources: Source[]
  meta: QueryResult['meta'] | null
  created_at: string
}

export interface ThreadDetail extends ThreadSummary {
  messages: Message[]
}

export type IngestInput =
  | { type: 'note'; content: string; title?: string }
  | { type: 'url'; url: string }

/** Error envelope from the backend: { error: { code, message, details, request_id } } */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: any

  constructor(status: number, code: string, message: string, details: any = null) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export const NETWORK_ERROR = 'Cannot reach the server. Is the backend running on port 8000?'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    // FormData bodies (file uploads) set their own multipart Content-Type.
    const json = !(init?.body instanceof FormData)
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { ...(json && { 'Content-Type': 'application/json' }), ...init?.headers },
    })
  } catch {
    throw new ApiError(0, 'network_error', NETWORK_ERROR)
  }

  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const error = body?.error
    throw new ApiError(
      response.status,
      error?.code ?? 'http_error',
      error?.message ?? `Request failed with status ${response.status}`,
      error?.details ?? null,
    )
  }
  return body as T
}

export const api = {
  health: () => request<Health>('/health'),
  items: () => request<{ items: Item[] }>('/items').then((body) => body.items),
  ingest: (input: IngestInput) => request<Item>('/ingest', { method: 'POST', body: JSON.stringify(input) }),
  deleteItem: (id: string) => request<null>(`/items/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  retryItem: (id: string) => request<Item>(`/items/${encodeURIComponent(id)}/retry`, { method: 'POST' }),
  uploadFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Item>('/ingest/file', { method: 'POST', body: form })
  },
  threads: () => request<{ threads: ThreadSummary[] }>('/threads').then((body) => body.threads),
  thread: (id: string) => request<ThreadDetail>(`/threads/${encodeURIComponent(id)}`),
  deleteThread: (id: string) => request<null>(`/threads/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  settings: () => request<Settings>('/settings'),
  saveSettings: (input: SettingsInput) =>
    request<{ settings: Settings; reindexing: number }>('/settings', { method: 'PUT', body: JSON.stringify(input) }),
}
