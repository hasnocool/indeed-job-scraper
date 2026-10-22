import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import {
  getApplicationSummary,
  getApplications,
  getMessages,
  type ApplicationEntry,
  type ApplicationSummary,
  type MessageEntry,
} from '../api/client'

/** Default page size for the ledger and message tables. */
export const DEFAULT_APPLICATION_PAGE_SIZE = 50
export const DEFAULT_MESSAGE_PAGE_SIZE = 50

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

export const useApplicationsStore = defineStore('applications', () => {
  /* ---------------- state ---------------- */

  const items = ref<ApplicationEntry[]>([])
  const total = ref(0)
  const limit = ref(DEFAULT_APPLICATION_PAGE_SIZE)
  const offset = ref(0)
  const statusFilter = ref('')

  const summary = ref<ApplicationSummary | null>(null)
  const summaryError = ref<string | null>(null)

  const messages = ref<MessageEntry[]>([])
  const messagesTotal = ref(0)
  const messagesLimit = ref(DEFAULT_MESSAGE_PAGE_SIZE)
  const messagesOffset = ref(0)

  const loading = ref(false)
  const error = ref<string | null>(null)
  const messagesLoading = ref(false)
  const messagesError = ref<string | null>(null)

  const requestId = ref(0)
  const messagesRequestId = ref(0)
  const lastQuery = shallowRef<{ limit: number; offset: number; status: string }>({
    limit: DEFAULT_APPLICATION_PAGE_SIZE,
    offset: 0,
    status: '',
  })
  const lastMessagesQuery = shallowRef<{ limit: number; offset: number }>({
    limit: DEFAULT_MESSAGE_PAGE_SIZE,
    offset: 0,
  })

  /* ---------------- computed ---------------- */

  const pageCount = computed(() =>
    limit.value > 0 ? Math.max(1, Math.ceil(total.value / limit.value)) : 1,
  )

  const page = computed(() =>
    limit.value > 0 ? Math.floor(offset.value / limit.value) + 1 : 1,
  )

  const isEmpty = computed(
    () => !loading.value && error.value === null && items.value.length === 0,
  )

  const messagesPageCount = computed(() =>
    messagesLimit.value > 0
      ? Math.max(1, Math.ceil(messagesTotal.value / messagesLimit.value))
      : 1,
  )

  const messagesPage = computed(() =>
    messagesLimit.value > 0 ? Math.floor(messagesOffset.value / messagesLimit.value) + 1 : 1,
  )

  const messagesEmpty = computed(
    () =>
      !messagesLoading.value && messagesError.value === null && messages.value.length === 0,
  )

  /** Statuses present in the ledger, derived from the summary. */
  const statusOptions = computed(() => {
    const counts = summary.value?.status_counts ?? {}
    return Object.keys(counts).sort((a, b) => (counts[b] ?? 0) - (counts[a] ?? 0))
  })

  /* ---------------- actions ---------------- */

  async function load(): Promise<void> {
    const query = {
      limit: limit.value,
      offset: offset.value,
      status: statusFilter.value,
    }
    lastQuery.value = query
    await fetchApplications(query)
  }

  async function fetchApplications(query: {
    limit: number
    offset: number
    status: string
  }): Promise<void> {
    const currentRequest = requestId.value + 1
    requestId.value = currentRequest
    loading.value = true
    error.value = null
    try {
      const response = await getApplications(query)
      if (requestId.value !== currentRequest) return
      items.value = response.items
      total.value = response.total
      limit.value = response.limit
      offset.value = response.offset
    } catch (caught) {
      if (requestId.value !== currentRequest) return
      error.value = toErrorMessage(caught)
      items.value = []
      total.value = 0
    } finally {
      if (requestId.value === currentRequest) loading.value = false
    }
  }

  async function retry(): Promise<void> {
    await fetchApplications(lastQuery.value)
  }

  async function loadSummary(): Promise<void> {
    summaryError.value = null
    try {
      summary.value = await getApplicationSummary()
    } catch (caught) {
      summaryError.value = toErrorMessage(caught)
    }
  }

  async function loadMessages(): Promise<void> {
    const query = { limit: messagesLimit.value, offset: messagesOffset.value }
    lastMessagesQuery.value = query
    await fetchMessages(query)
  }

  async function fetchMessages(query: { limit: number; offset: number }): Promise<void> {
    const currentRequest = messagesRequestId.value + 1
    messagesRequestId.value = currentRequest
    messagesLoading.value = true
    messagesError.value = null
    try {
      const response = await getMessages(query)
      if (messagesRequestId.value !== currentRequest) return
      messages.value = response.items
      messagesTotal.value = response.total
      messagesLimit.value = response.limit
      messagesOffset.value = response.offset
    } catch (caught) {
      if (messagesRequestId.value !== currentRequest) return
      messagesError.value = toErrorMessage(caught)
      messages.value = []
      messagesTotal.value = 0
    } finally {
      if (messagesRequestId.value === currentRequest) messagesLoading.value = false
    }
  }

  async function retryMessages(): Promise<void> {
    await fetchMessages(lastMessagesQuery.value)
  }

  async function setStatusFilter(status: string): Promise<void> {
    if (statusFilter.value === status) return
    statusFilter.value = status
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

  async function goToMessagesPage(pageNumber: number): Promise<void> {
    const clamped = Math.min(Math.max(1, pageNumber), messagesPageCount.value)
    const nextOffset = (clamped - 1) * messagesLimit.value
    if (nextOffset === messagesOffset.value && messages.value.length > 0) return
    messagesOffset.value = nextOffset
    await loadMessages()
  }

  async function loadAll(): Promise<void> {
    await Promise.all([load(), loadSummary(), loadMessages()])
  }

  return {
    // state
    items,
    total,
    limit,
    offset,
    statusFilter,
    summary,
    summaryError,
    messages,
    messagesTotal,
    messagesLimit,
    messagesOffset,
    loading,
    error,
    messagesLoading,
    messagesError,
    // computed
    pageCount,
    page,
    isEmpty,
    messagesPageCount,
    messagesPage,
    messagesEmpty,
    statusOptions,
    // actions
    load,
    retry,
    loadSummary,
    loadMessages,
    retryMessages,
    setStatusFilter,
    goToPage,
    goToMessagesPage,
    loadAll,
  }
})
