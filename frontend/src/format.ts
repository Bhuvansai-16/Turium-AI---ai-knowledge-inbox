const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['day', 86_400],
  ['hour', 3_600],
  ['minute', 60],
]

export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

export function clockTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/** Library sections, like chat history: Today, Yesterday, Earlier. */
export function dayGroup(iso: string, now = new Date()): 'Today' | 'Yesterday' | 'Earlier' {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const time = new Date(iso).getTime()
  if (time >= startOfToday) return 'Today'
  if (time >= startOfToday - 86_400_000) return 'Yesterday'
  return 'Earlier'
}

/** "Qwen/Qwen3-235B-A22B-Instruct-2507" -> "Qwen3-235B-A22B-Instruct-2507". */
export function shortModel(name: string | undefined): string {
  return name?.split('/').pop() ?? ''
}

export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export function isHttpUrl(value: string): boolean {
  try {
    const { protocol } = new URL(value)
    return protocol === 'http:' || protocol === 'https:'
  } catch {
    return false
  }
}

/** A single pasted/typed link with no other text. */
export function isLoneUrl(value: string): boolean {
  const text = value.trim()
  return text !== '' && !/\s/.test(text) && isHttpUrl(text)
}
