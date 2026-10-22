import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import {
  getJobFacets,
  getJobs,
  type Job,
  type JobFacets,
  type JobQuery,
  type JobSortField,
  type SortOrder,
} from '../api/client'

/** Default page size for the jobs table. */
export const DEFAULT_JOB_PAGE_SIZE = 25

/** Page sizes offered in the UI. */
export const JOB_PAGE_SIZES = [10, 25, 50, 100] as const

export interface JobFilters {
  q: string
  location: string
  company: string
  status: string
}

function emptyFilters(): JobFilters {
  return { q: '', location: '', company: '', status: '' }
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

export const useJobsStore = defineStore('jobs', () => {
  /* ---------------- state ---------------- */

  const items = ref<Job[]>([])
  const total = ref(0)
  const limit = ref(DEFAULT_JOB_PAGE_SIZE)
  const offset = ref(0)

  const facets = ref<JobFacets | null>(null)
  const facetsError = ref<string | null>(null)

  const filters = ref<JobFilters>(emptyFilters())
  const sort = ref<JobSortField>('last_seen')
  const order = ref<SortOrder>('desc')

  const loading = ref(false)
  const error = ref<string | null>(null)

  // The last successful query, replayed by `retry()`.
  const lastQuery = shallowRef<JobQuery>({})
  const requestId = ref(0)

  /* ---------------- computed ---------------- */

  const pageCount = computed(() =>
    limit.value > 0 ? Math.max(1, Math.ceil(total.value / limit.value)) : 1,
  )

  const page = computed(() =>
    limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1,
  )

  const hasFilters = computed(() => {
    const f = filters.value
    return (
      f.q.trim() !== '' ||
      f.location !== '' ||
      f.company !== '' ||
      f.status !== ''
    )
  })

  const isEmpty = computed(() => !loading.value && error.value === null && items.value.length === 0)

  /** Facet options for the dropdowns — never includes empty strings. */
  const locationOptions = computed(() => facets.value?.locations ?? [])
  const companyOptions = computed(() => facets.value?.companies ?? [])
  const statusOptions = computed(() => {
    const counts = facets.value?.status_counts ?? {}
    return Object.keys(counts).sort((a, b) => {
      if (a === 'new') return -1
      if (b === 'new') return 1
      if (a === 'updated') return -1
      if (b === 'updated') return 1
      return a.localeCompare(b)
    })
  })

  /* ---------------- actions ---------------- */

  function buildQuery(): JobQuery {
    const f = filters.value
    return {
      q: f.q.trim(),
      location: f.location,
      company: f.company,
      status: f.status,
      limit: limit.value,
      offset: offset.value,
      sort: sort.value,
      order: order.value,
    }
  }

  async function fetchJobs(query: JobQuery, signal?: AbortSignal): Promise<void> {
    const currentRequest = requestId.value + 1
    requestId.value = currentRequest
    loading.value = true
    error.value = null

    try {
      const response = await getJobs(query, signal)
      if (requestId.value !== currentRequest) return
      items.value = response.items
      total.value = response.total
      limit.value = response.limit
      offset.value = response.offset
    } catch (caught) {
      if (requestId.value !== currentRequest) return
      if (caught instanceof Error && caught.name === 'AbortError') return
      error.value = toErrorMessage(caught)
      items.value = []
      total.value = 0
    } finally {
      if (requestId.value === currentRequest) loading.value = false
    }
  }

  /** Load the job list for the current filter/sort/page state. */
  async function load(): Promise<void> {
    const query = buildQuery()
    lastQuery.value = query
    await fetchJobs(query)
  }

  /** Re-run the last request — used by the error state's retry button. */
  async function retry(): Promise<void> {
    await fetchJobs(lastQuery.value)
  }

  async function loadFacets(): Promise<void> {
    facetsError.value = null
    try {
      facets.value = await getJobFacets()
    } catch (caught) {
      facetsError.value = toErrorMessage(caught)
    }
  }

  /** Apply a filter change: reset pagination, then reload. */
  async function setFilter<K extends keyof JobFilters>(key: K, value: JobFilters[K]): Promise<void> {
    if (filters.value[key] === value) return
    filters.value[key] = value
    offset.value = 0
    await load()
  }

  function setFilters(next: Partial<JobFilters>): void {
    filters.value = { ...filters.value, ...next }
  }

  function resetFilters(): void {
    filters.value = emptyFilters()
  }

  async function clearFilters(): Promise<void> {
    filters.value = emptyFilters()
    offset.value = 0
    await load()
  }

  async function setSort(field: JobSortField, nextOrder?: SortOrder): Promise<void> {
    if (nextOrder !== undefined) {
      sort.value = field
      order.value = nextOrder
    } else if (sort.value === field) {
      order.value = order.value === 'asc' ? 'desc' : 'asc'
    } else {
      sort.value = field
      order.value = 'asc'
    }
    offset.value = 0
    await load()
  }

  async function setLimit(nextLimit: number): Promise<void> {
    if (limit.value === nextLimit) return
    limit.value = nextLimit
    offset.value = 0
    await load()
  }

  async function goToPage(pageNumber: number): Promise<void> {
    const clamped = Math.min(Math.max(1, pageNumber), pageCount.value)
    const nextOffset = (clamped - 1) * limit.value
    if (nextOffset === offset.value && items.value.length > 0) return
    offset.value = nextOffset
    await load()
  }

  async function nextPage(): Promise<void> {
    await goToPage(page.value + 1)
  }

  async function previousPage(): Promise<void> {
    await goToPage(page.value - 1)
  }

  return {
    // state
    items,
    total,
    limit,
    offset,
    facets,
    facetsError,
    filters,
    sort,
    order,
    loading,
    error,
    // computed
    pageCount,
    page,
    hasFilters,
    isEmpty,
    locationOptions,
    companyOptions,
    statusOptions,
    // actions
    load,
    retry,
    loadFacets,
    setFilter,
    setFilters,
    resetFilters,
    clearFilters,
    setSort,
    setLimit,
    goToPage,
    nextPage,
    previousPage,
  }
})
