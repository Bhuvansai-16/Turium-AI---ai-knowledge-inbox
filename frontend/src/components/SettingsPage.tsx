import { ArrowLeft, Desktop, Eye, EyeSlash, Moon, Sun, Warning, X } from '@phosphor-icons/react'
import { useEffect, useId, useState, type FormEvent, type ReactNode } from 'react'

import { ApiError, type ProviderName, type Settings } from '../api'
import { useSaveSettings, useSettings } from '../hooks'
import type { Theme } from '../theme'
import { Button, inputClass } from './ui'

const PROVIDER_ORDER: ProviderName[] = ['openai', 'gemini', 'custom']
const PROVIDER_NOTES: Record<ProviderName, string> = {
  openai: 'Needs an OpenAI API key',
  gemini: 'Needs a Google AI Studio key',
  custom: 'Ollama, Nebius, Groq and others',
}

export interface SavedResult {
  settings: Settings
  reindexing: number
}

/** Settings as a page in the main area (the sidebar stays), with room for each section. */
export function SettingsPage({
  onClose,
  theme,
  onThemeChange,
  onSaved,
}: {
  onClose: () => void
  theme: Theme
  onThemeChange: (theme: Theme) => void
  onSaved: (result: SavedResult) => void
}) {
  const { data: saved } = useSettings()
  const save = useSaveSettings()
  const ids = {
    url: useId(),
    key: useId(),
    chat: useId(),
    embed: useId(),
    add: useId(),
    error: useId(),
  }

  const [provider, setProvider] = useState<ProviderName>('openai')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [chatModel, setChatModel] = useState('')
  const [chatModels, setChatModels] = useState<string[]>([])
  const [embedModel, setEmbedModel] = useState('')
  const [newModel, setNewModel] = useState('')

  // Start from the saved settings when the page opens (and once they load).
  useEffect(() => {
    if (!saved) return
    setProvider(saved.provider)
    setBaseUrl(saved.base_url)
    setChatModel(saved.chat_model)
    setChatModels(saved.chat_models)
    setEmbedModel(saved.embed_model)
    setApiKey('')
    setNewModel('')
    save.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [saved])

  if (!saved) return null
  const preset = saved.presets[provider]
  const savedKeyHint = saved.key_hints[provider]
  const embedChanges = embedModel.trim() !== saved.embed_model
  const error = save.error as ApiError | null

  function chooseProvider(next: ProviderName) {
    setProvider(next)
    save.reset()
    const source = next === saved!.provider ? saved! : saved!.presets[next]
    setBaseUrl(source.base_url)
    setChatModel(source.chat_model)
    setChatModels(next === saved!.provider ? saved!.chat_models : [source.chat_model])
    setEmbedModel(source.embed_model)
  }

  // Chat models offered in the question box: the default, plus any IDs the user adds.
  const defaultModel = chatModel.trim()
  const extraModels = chatModels.filter((name) => name !== defaultModel)

  function addModel() {
    const name = newModel.trim()
    if (name && name !== defaultModel && !chatModels.includes(name)) setChatModels([...chatModels, name])
    setNewModel('')
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    save.mutate(
      {
        provider,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || undefined,
        chat_model: defaultModel,
        chat_models: [...new Set([defaultModel, ...chatModels])],
        embed_model: embedModel.trim(),
      },
      {
        onSuccess: (result) => {
          onSaved(result)
          onClose()
        },
      },
    )
  }

  return (
    <form onSubmit={submit} aria-labelledby="settings-title" className="flex min-h-0 flex-1 flex-col">
      <header className="flex h-14 shrink-0 items-center px-4">
        <button
          type="button"
          onClick={onClose}
          className="tap inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-sm text-ink-muted hover:bg-surface-muted hover:text-ink"
        >
          <ArrowLeft size={16} aria-hidden /> Back to chat
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-10 px-6 pt-4 pb-12">
          <div>
            <h1 id="settings-title" className="text-2xl font-semibold tracking-tight">
              Settings
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              Appearance, the AI provider, and the models you can pick from.
            </p>
          </div>

          <Section title="Appearance" hint="Follows your system by default.">
            <div
              role="radiogroup"
              aria-label="Theme"
              className="grid grid-cols-3 gap-1 rounded-xl bg-surface-muted p-1"
            >
              {(
                [
                  ['system', 'System', <Desktop key="d" size={16} aria-hidden />],
                  ['light', 'Light', <Sun key="s" size={16} aria-hidden />],
                  ['dark', 'Dark', <Moon key="m" size={16} aria-hidden />],
                ] as const
              ).map(([value, label, icon]) => (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={theme === value}
                  onClick={() => onThemeChange(value)}
                  className={`tap flex h-9 items-center justify-center gap-1.5 rounded-lg text-sm font-medium transition-colors duration-150 ${
                    theme === value ? 'bg-surface text-ink shadow-panel' : 'text-ink-muted hover:text-ink'
                  }`}
                >
                  {icon}
                  {label}
                </button>
              ))}
            </div>
          </Section>

          <Section title="AI provider" hint="Embeddings and answers both come from this provider.">
            <fieldset className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              <legend className="sr-only">Provider</legend>
              {PROVIDER_ORDER.map((name) => (
                <label
                  key={name}
                  className={`flex cursor-pointer flex-col gap-0.5 rounded-xl border p-3 transition-colors duration-150 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-accent ${
                    provider === name ? 'border-accent bg-accent-soft' : 'border-line hover:border-ink-muted'
                  }`}
                >
                  <input
                    type="radio"
                    name="provider"
                    value={name}
                    checked={provider === name}
                    onChange={() => chooseProvider(name)}
                    className="sr-only"
                  />
                  <span className="text-sm font-medium">{saved.presets[name].label}</span>
                  <span className="text-xs text-ink-muted">{PROVIDER_NOTES[name]}</span>
                </label>
              ))}
            </fieldset>

            {provider === 'custom' && (
              <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-xs leading-relaxed text-ink-muted">
                Any server that speaks the OpenAI API. For free local models, install Ollama, run{' '}
                <code className="font-mono text-ink">ollama pull llama3.1</code> and{' '}
                <code className="font-mono text-ink">ollama pull nomic-embed-text</code>, then use{' '}
                <code className="font-mono text-ink">http://localhost:11434/v1/</code> with those two model IDs.
              </p>
            )}

            <Field id={ids.url} label="API base URL">
              <input
                id={ids.url}
                type="url"
                required
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.example.com/v1/"
                className={`${inputClass} text-base sm:text-sm`}
              />
            </Field>

            <Field
              id={ids.key}
              label={preset.needs_key ? 'API key' : 'API key (optional)'}
              hint="Kept by the backend on this machine. It is never sent back to the browser."
            >
              <div className="relative">
                <input
                  id={ids.key}
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  placeholder={
                    savedKeyHint ? `Saved key ${savedKeyHint}, leave blank to keep it` : 'Paste your API key'
                  }
                  className={`${inputClass} pr-10 font-mono text-base sm:text-sm`}
                />
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  aria-label={showKey ? 'Hide API key' : 'Show API key'}
                  className="tap absolute top-1/2 right-1 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-ink-muted hover:text-ink"
                >
                  {showKey ? <EyeSlash size={16} aria-hidden /> : <Eye size={16} aria-hidden />}
                </button>
              </div>
            </Field>
          </Section>

          <Section
            title="Models"
            hint="Type model IDs exactly as your provider lists them. Each one is tested when you save."
          >
            <Field id={ids.chat} label="Default chat model">
              <input
                id={ids.chat}
                required
                value={chatModel}
                onChange={(e) => setChatModel(e.target.value)}
                spellCheck={false}
                className={`${inputClass} font-mono text-base sm:text-sm`}
              />
            </Field>
            <div className="flex flex-col gap-1.5">
              <label htmlFor={ids.add} className="text-sm font-medium">
                More models for the question box
              </label>
              {extraModels.length > 0 && (
                <ul className="flex flex-col gap-px rounded-xl border border-line p-1">
                  {extraModels.map((name) => (
                    <li key={name} className="flex h-9 items-center gap-2 rounded-lg pr-1 pl-2.5">
                      <span className="min-w-0 flex-1 truncate font-mono text-xs">{name}</span>
                      <button
                        type="button"
                        onClick={() => setChatModels(chatModels.filter((m) => m !== name))}
                        aria-label={`Remove ${name}`}
                        className="tap flex size-7 items-center justify-center rounded-md text-ink-muted hover:bg-surface-muted hover:text-ink"
                      >
                        <X size={14} aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex gap-2">
                <input
                  id={ids.add}
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      addModel()
                    }
                  }}
                  spellCheck={false}
                  placeholder="Model ID"
                  className={`${inputClass} font-mono text-base sm:text-sm`}
                />
                <button
                  type="button"
                  onClick={addModel}
                  disabled={!newModel.trim()}
                  className="tap h-9 shrink-0 rounded-lg border border-line px-3.5 text-sm font-medium hover:bg-surface-muted disabled:opacity-45"
                >
                  Add
                </button>
              </div>
              <p className="text-xs text-ink-muted">These appear in the dropdown under the question box.</p>
            </div>
            <Field
              id={ids.embed}
              label="Embedding model"
              hint={
                embedChanges
                  ? 'Changing this re-indexes every saved item in the background.'
                  : 'Used for both your saved items and your questions.'
              }
              hintTone={embedChanges ? 'warn' : 'muted'}
            >
              <input
                id={ids.embed}
                required
                value={embedModel}
                onChange={(e) => setEmbedModel(e.target.value)}
                className={`${inputClass} font-mono text-base sm:text-sm`}
              />
            </Field>
          </Section>
        </div>
      </div>

      <footer className="shrink-0 border-t border-line bg-bg">
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-end gap-3 px-6 py-3">
          {error && (
            <div id={ids.error} role="alert" className="mr-auto flex min-w-0 items-start gap-2 text-sm">
              <Warning size={16} aria-hidden className="mt-0.5 shrink-0" />
              <div className="min-w-0">
                <p>{error.message}</p>
                {typeof error.details?.reason === 'string' && (
                  <p
                    className="mt-0.5 line-clamp-2 font-mono text-xs break-all text-ink-muted"
                    title={error.details.reason}
                  >
                    {error.details.reason}
                  </p>
                )}
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={onClose}
            className="tap h-9 rounded-lg px-3.5 text-sm font-medium text-ink-muted hover:bg-surface-muted hover:text-ink"
          >
            Cancel
          </button>
          <Button type="submit" disabled={save.isPending} aria-describedby={error ? ids.error : undefined}>
            {save.isPending ? 'Testing connection...' : 'Test and save'}
          </Button>
        </div>
      </footer>
    </form>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-line pt-8 md:grid-cols-[13rem_minmax(0,1fr)] md:gap-10">
      <div>
        <h2 className="text-base font-semibold">{title}</h2>
        {hint && <p className="mt-1 text-sm leading-relaxed text-ink-muted">{hint}</p>}
      </div>
      <div className="flex min-w-0 flex-col gap-4">{children}</div>
    </section>
  )
}

function Field({
  id,
  label,
  hint,
  hintTone = 'muted',
  children,
}: {
  id: string
  label: string
  hint?: string
  hintTone?: 'muted' | 'warn'
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className={`text-xs ${hintTone === 'warn' ? 'text-accent-ink' : 'text-ink-muted'}`}>{hint}</p>}
    </div>
  )
}
