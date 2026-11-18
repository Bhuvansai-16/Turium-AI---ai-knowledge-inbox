import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'

import { api, type IngestInput, type Item, type SettingsInput } from './api'

const ITEMS_KEY = ['items']
const POLL_MS = 1500

const isInFlight = (item: Item) => item.status === 'pending' || item.status === 'processing'

/** Saved items. Polls only while something is still being indexed, then stops. */
export function useItems() {
  return useQuery({
    queryKey: ITEMS_KEY,
    queryFn: api.items,
    refetchInterval: (query) => (query.state.data?.some(isInFlight) ? POLL_MS : false),
  })
}

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 30_000 })
}

export function useIngest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: IngestInput) => api.ingest(input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useDeleteItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.deleteItem,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useRetryItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.retryItem,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useUploadFile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => api.uploadFile(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export const THREADS_KEY = ['threads']

export function useThreads() {
  return useQuery({ queryKey: THREADS_KEY, queryFn: api.threads })
}

export function useDeleteThread() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: api.deleteThread,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: THREADS_KEY }),
  })
}

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: api.settings })
}

/** Saving a provider changes health (configured/model) and may re-index every item. */
export function useSaveSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SettingsInput) => api.saveSettings(input),
    onSuccess: () => {
      for (const key of [['settings'], ['health'], ITEMS_KEY]) queryClient.invalidateQueries({ queryKey: key })
    },
  })
}


export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const media = window.matchMedia(query)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
  )
}
