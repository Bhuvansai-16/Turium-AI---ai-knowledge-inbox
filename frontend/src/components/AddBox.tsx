import { FileArrowUp, LinkSimple, NotePencil } from '@phosphor-icons/react'
import { useId, useRef, useState, type DragEvent, type FormEvent, type KeyboardEvent, type RefObject } from 'react'

import { ApiError, type Item } from '../api'
import { hostOf, isLoneUrl } from '../format'
import { useIngest, useUploadFile } from '../hooks'
import { Button } from './ui'

const MAX_NOTE_CHARS = 20_000
const ACCEPT = '.pdf,.docx,.txt,.md,.markdown'

/**
 * One place to add anything: paste a link, write a note, or upload / drop a document.
 * A lone URL is saved as a link; other text as a note; files are parsed on the server.
 */
export function AddBox({
  inputRef,
  onSaved,
}: {
  inputRef: RefObject<HTMLTextAreaElement | null>
  onSaved: (item: Item) => void
}) {
  const [text, setText] = useState('')
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const [dragging, setDragging] = useState(false)
  const ingest = useIngest()
  const upload = useUploadFile()
  const fileInput = useRef<HTMLInputElement>(null)
  const ids = { input: useId(), message: useId() }

  const value = text.trim()
  const isUrl = isLoneUrl(value)
  const tooLong = !isUrl && text.length > MAX_NOTE_CHARS
  const busy = ingest.isPending || upload.isPending
  const canSave = value !== '' && !tooLong && !busy

  function saved(item: Item) {
    setMessage({ tone: 'ok', text: `Added "${item.title}". Indexing now.` })
    onSaved(item)
  }

  function failed(error: Error) {
    setMessage({
      tone: 'error',
      text: error instanceof ApiError && error.code === 'duplicate' ? 'This is already in your library.' : error.message,
    })
  }

  function save(event?: FormEvent) {
    event?.preventDefault()
    if (!canSave) return
    ingest.mutate(isUrl ? { type: 'url', url: value } : { type: 'note', content: value }, {
      onSuccess: (item) => {
        setText('')
        saved(item)
      },
      onError: failed,
    })
  }

  function uploadFiles(fileList: FileList | null) {
    for (const file of Array.from(fileList ?? [])) {
      setMessage(null)
      upload.mutate(file, { onSuccess: saved, onError: failed })
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    uploadFiles(event.dataTransfer.files)
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) save()
  }

  return (
    <form
      onSubmit={save}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-xl border p-2 transition-colors duration-150 ${
        dragging ? 'border-accent bg-accent-soft' : 'border-line bg-bg focus-within:border-accent'
      }`}
    >
      <label htmlFor={ids.input} className="sr-only">
        Paste a link or write a note
      </label>
      <textarea
        id={ids.input}
        ref={inputRef}
        value={text}
        onChange={(e) => {
          setText(e.target.value)
          setMessage(null)
        }}
        onKeyDown={onKeyDown}
        aria-invalid={tooLong}
        aria-describedby={message ? ids.message : undefined}
        placeholder={dragging ? 'Drop to upload' : 'Paste a link, write a note, or drop a file...'}
        className="max-h-48 min-h-16 w-full resize-none bg-transparent px-1.5 py-1 text-base leading-relaxed text-ink [field-sizing:content] placeholder:text-ink-muted focus:outline-none sm:text-sm"
      />
      <div className="flex items-center gap-2">
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPT}
          multiple
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => {
            uploadFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          disabled={busy}
          className="tap inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink disabled:opacity-50"
        >
          <FileArrowUp size={16} aria-hidden /> Upload file
        </button>
        <p className="min-w-0 flex-1 truncate text-xs text-ink-muted">
          {value === '' ? (
            'PDF, Word, TXT or Markdown'
          ) : isUrl ? (
            <span className="inline-flex items-center gap-1 text-accent-ink">
              <LinkSimple size={14} aria-hidden /> Link from {hostOf(value)}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1">
              <NotePencil size={14} aria-hidden />
              {tooLong ? `Too long: ${MAX_NOTE_CHARS.toLocaleString()} characters max` : 'Note'}
            </span>
          )}
        </p>
        <Button type="submit" disabled={!canSave}>
          {busy ? 'Adding...' : 'Add'}
        </Button>
      </div>
      <p id={ids.message} role="status" className={`min-h-5 px-1.5 pt-1 text-xs ${message?.tone === 'ok' ? 'text-accent-ink' : ''}`}>
        {message?.text}
      </p>
    </form>
  )
}
