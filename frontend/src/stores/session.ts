import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import { getRuns, getSession, type RunInfo, type SessionInfo } from '../api/client'

/** Default page size for the run history table. */
export const DEFAULT_RUN_PAGE_SIZE = 20

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'An unexpected error occurred.'
}

export const useSessionStore = defineStore('session', () => {
  /* ---------------- state ---------------- */

  const session = ref<SessionInfo | null>(null)
  const sessionLoading = ref(false)
  const sessionError = ref<string | null>(null)

  const runs = ref<RunInfo[]>([])
  const runsTotal = ref(0)
  const runsLimit = ref(DEFAULT_RUN_PAGE_SIZE)
  const runsOffset = ref(0)
  const runsLoading = ref(false)
  const runsError = ref<string | null>(null)

  const requestId = ref(0)
  const runsRequestId = ref(0)
  const lastRunsQuery = shallowRef<{ limit: number; offset: number }>({
    limit: DEFAULT_RUN_PAGE_SIZE,
    offset: 0,
  })

  /* ---------------- computed ---------------- */

  const hasSession = computed(() => session.value?.has_session ?? false)

  const sessionStatus = computed(() => session.value?.status ?? 'none')

  const isExpired = computed(() => session.value?.expired ?? false)

  /** A session that exists, is not expired, and is not explicitly revoked. */
  const isHealthy = computed(
    () => hasSession.value && !isExpired.value && sessionStatus.value === 'active',
  )

  const runsPageCount = computed(() =>
    runsLimit.value > 0 ? Math.max(1, Math.ceil(runsTotal.value / runsLimit.value)) : 1,
  )

  const runsPage = computed(() =>
    runsLimit.value > 0 ? Math.floor(runsOffset.value / runsLimit.value) + 1 : 1,
  )

  const runsEmpty = computed(
    () => !runsLoading.value && runsError.value === null && runs.value.length === 0,
  )

  /* ---------------- actions ---------------- */

  async function loadSession(): Promise<void> {
    const currentRequest = requestId.value + 1
    requestId.value = currentRequest
    sessionLoading.value = true
    sessionError.value = null
    try {
      session.value = await getSession()
    } catch (caught) {
      if (requestId.value !== currentRequest) return
      sessionError.value = toErrorMessage(caught)
      session.value = null
    } finally {
      if (requestId.value === currentRequest) sessionLoading.value = false
    }
  }

  async function retrySession(): Promise<void> {
    await loadSession()
  }

  async function loadRuns(): Promise<void> {
    const query = { limit: runsLimit.value, offset: runsOffset.value }
    lastRunsQuery.value = query
    await fetchRuns(query)
  }

  async function fetchRuns(query: { limit: number; offset: number }): Promise<void> {
    const currentRequest = runsRequestId.value + 1
    runsRequestId.value = currentRequest
    runsLoading.value = true
    runsError.value = null
    try {
      const response = await getRuns(query)
      if (runsRequestId.value !== currentRequest) return
      runs.value = response.items
      runsTotal.value = response.total
      runsLimit.value = response.limit
      runsOffset.value = response.offset
    } catch (caught) {
      if (runsRequestId.value !== currentRequest) return
      runsError.value = toErrorMessage(caught)
      runs.value = []
      runsTotal.value = 0
    } finally {
      if (runsRequestId.value === currentRequest) runsLoading.value = false
    }
  }

  async function retryRuns(): Promise<void> {
    await fetchRuns(lastRunsQuery.value)
  }

  async function goToRunsPage(pageNumber: number): Promise<void> {
    const clamped = Math.min(Math.max(1, pageNumber), runsPageCount.value)
    const nextOffset = (clamped - 1) * runsLimit.value
    if (nextOffset === runsOffset.value && runs.value.length > 0) return
    runsOffset.value = nextOffset
    await loadRuns()
  }

  async function loadAll(): Promise<void> {
    await Promise.all([loadSession(), loadRuns()])
  }

  return {
    // state
    session,
    sessionLoading,
    sessionError,
    runs,
    runsTotal,
    runsLimit,
    runsOffset,
    runsLoading,
    runsError,
    // computed
    hasSession,
    sessionStatus,
    isExpired,
    isHealthy,
    runsPageCount,
    runsPage,
    runsEmpty,
    // actions
    loadSession,
    retrySession,
    loadRuns,
    retryRuns,
    goToRunsPage,
    loadAll,
  }
})
