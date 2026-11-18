import { SidebarSimple, Warning } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'

import type { Item } from './api'
import { Composer } from './components/Composer'
import { IngestStatus } from './components/IngestStatus'
import { LibraryPanel } from './components/LibraryPanel'
import { SettingsPage, type SavedResult } from './components/SettingsPage'
import { Sidebar } from './components/Sidebar'
import { Thread } from './components/Thread'
import { useHealth, useMediaQuery, useSettings, useThreads } from './hooks'
import { useTheme } from './theme'
import { useThread } from './useThread'

const TOAST_MS = 4500
const MODEL_KEY = 'model'

function savedModel(): string | null {
  try {
    return localStorage.getItem(MODEL_KEY)
  } catch {
    return null
  }
}

export default function App() {
  const conversation = useThread()
  const { data: threads } = useThreads()
  const { data: settings } = useSettings()
  const [theme, setTheme] = useTheme()
  const [draft, setDraft] = useState('')
  const [model, setModel] = useState<string | null>(savedModel)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [watched, setWatched] = useState<string[]>([])
  const [drawerRequested, setDrawerRequested] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const wide = useMediaQuery('(min-width: 1024px)')
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const addRef = useRef<HTMLTextAreaElement>(null)

  const drawerOpen = drawerRequested && !wide
  const showSidebar = (wide && !sidebarCollapsed) || drawerOpen
  const title = threads?.find((thread) => thread.id === conversation.threadId)?.title

  // The remembered model may belong to a provider used before; then the default is used.
  const activeModel = model && settings?.chat_models.includes(model) ? model : (settings?.chat_model ?? null)

  function submit(question: string) {
    conversation.ask(question, activeModel)
    setDraft('')
  }

  function askAbout(item: Item) {
    setDraft(`What are the key points of "${item.title}"?`)
    setLibraryOpen(false)
    setDrawerRequested(false)
    composerRef.current?.focus()
  }

  function openLibrary() {
    setLibraryOpen(true)
    setDrawerRequested(false)
    addRef.current?.focus()
  }

  function openSettings() {
    setSettingsOpen(true)
    setLibraryOpen(false)
    setDrawerRequested(false)
  }

  function chooseModel(name: string) {
    setModel(name)
    try {
      localStorage.setItem(MODEL_KEY, name)
    } catch {
      // Not remembered across visits; still used for this session.
    }
  }

  function onSettingsSaved({ settings, reindexing }: SavedResult) {
    const label = settings.presets[settings.provider].label
    setToast(
      reindexing > 0
        ? `Connected to ${label}. Re-indexing ${reindexing} ${reindexing === 1 ? 'item' : 'items'} for the new embedding model.`
        : `Connected to ${label}.`,
    )
  }

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => setToast(null), TOAST_MS)
    return () => clearTimeout(timer)
  }, [toast])

  // "/" focuses the question box from anywhere; Escape closes the mobile drawer.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const typing = event.target instanceof HTMLElement && event.target.closest('input, textarea, select, [contenteditable]')
      if (event.key === '/' && !typing && !settingsOpen) {
        event.preventDefault()
        composerRef.current?.focus()
      } else if (event.key === 'Escape') {
        setDrawerRequested(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [settingsOpen])

  return (
    <div className="flex h-dvh bg-bg">
      <a
        href="#composer"
        className="sr-only z-50 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-on-accent focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to question box
      </a>

      {(drawerOpen || (libraryOpen && !wide)) && (
        <div
          aria-hidden
          className="animate-fade-in fixed inset-0 z-20 bg-scrim"
          onClick={() => {
            setDrawerRequested(false)
            setLibraryOpen(false)
          }}
        />
      )}
      {showSidebar && (
        <Sidebar
          drawer={drawerOpen}
          activeThreadId={conversation.threadId}
          libraryOpen={libraryOpen}
          onHide={() => (drawerOpen ? setDrawerRequested(false) : setSidebarCollapsed(true))}
          onNewChat={() => {
            conversation.startNew()
            setSettingsOpen(false)
            setDrawerRequested(false)
            composerRef.current?.focus()
          }}
          onOpenThread={(id) => {
            conversation.open(id)
            setSettingsOpen(false)
            setDrawerRequested(false)
          }}
          onThreadDeleted={(id) => id === conversation.threadId && conversation.startNew()}
          onToggleLibrary={() => (libraryOpen ? setLibraryOpen(false) : openLibrary())}
          onOpenSettings={openSettings}
        />
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        {settingsOpen ? (
          <SettingsPage
            onClose={() => setSettingsOpen(false)}
            theme={theme}
            onThemeChange={setTheme}
            onSaved={(result) => {
              onSettingsSaved(result)
              setSettingsOpen(false)
            }}
          />
        ) : (
          <>
            <header className="flex h-14 shrink-0 items-center gap-2 px-4">
              {!showSidebar && (
                <button
                  type="button"
                  onClick={() => (wide ? setSidebarCollapsed(false) : setDrawerRequested(true))}
                  aria-label="Show sidebar"
                  title="Show sidebar"
                  className="tap flex size-8 items-center justify-center rounded-lg text-ink-muted hover:bg-surface-muted hover:text-ink"
                >
                  <SidebarSimple size={18} aria-hidden />
                </button>
              )}
              <p className="min-w-0 truncate text-sm text-ink-muted">{title ?? 'New chat'}</p>
            </header>

            <BackendBanner />

            <Thread
              turns={conversation.turns}
              loading={conversation.loading}
              onAsk={submit}
              onAdd={openLibrary}
              onOpenSettings={openSettings}
            />

            <div className="mx-auto w-full max-w-3xl px-4 pb-3 sm:px-6">
              <IngestStatus
                watched={watched}
                onDismiss={(id) => setWatched((ids) => ids.filter((watchedId) => watchedId !== id))}
                onAskAbout={askAbout}
              />
              <Composer
                value={draft}
                onChange={setDraft}
                onSubmit={submit}
                onStop={conversation.stop}
                busy={conversation.busy}
                model={activeModel}
                onModelChange={chooseModel}
                onAdd={openLibrary}
                inputRef={composerRef}
              />
            </div>
          </>
        )}
      </main>

      {libraryOpen && (
        <LibraryPanel
          addRef={addRef}
          onClose={() => {
            setLibraryOpen(false)
            composerRef.current?.focus()
          }}
          onSaved={(item) => setWatched((ids) => [...ids, item.id])}
          onAskAbout={askAbout}
        />
      )}

      <div role="status" aria-live="polite" className="pointer-events-none fixed inset-x-0 top-4 z-40 flex justify-center px-4">
        {toast && (
          <p className="animate-fade-in pointer-events-auto max-w-md rounded-xl bg-ink px-4 py-2.5 text-sm text-bg shadow-panel">
            {toast}
          </p>
        )}
      </div>
    </div>
  )
}

function BackendBanner() {
  const { isError } = useHealth()
  if (!isError) return null
  return (
    <div role="alert" className="mx-4 mb-2 flex items-start gap-2 rounded-xl border border-line px-3 py-2.5 text-sm">
      <Warning size={18} aria-hidden className="mt-px shrink-0" />
      Cannot reach the backend. Start it on port 8000 (see README).
    </div>
  )
}
