/**
 * Typed API client for the Indeed Job Scraper backend.
 *
 * Every interface below mirrors `docs/api-contract.md` section 6 **verbatim**:
 * snake_case field names, `""` for missing strings, `null` only where the
 * contract says so (`SessionInfo.expires_at`).
 *
 * The backend is read-only: there are no POST/PUT/DELETE calls here.
 */

export interface Job {
  jk: string
  title: string
  company: string
  location: string
  salary: string
  schedule: string
  posted: string
  snippet: string
  url: string
  matches: string[]
  fingerprint: string
  short_id: string
  status: string
  first_seen: string
  last_seen: string
  seen_count: number
  duplicate_of: string
}

export interface JobListResponse {
  total: number
  limit: number
  offset: number
  items: Job[]
}

export interface JobFacets {
  total: number
  locations: string[]
  companies: string[]
  status_counts: Record<string, number>
}

export interface SessionInfo {
  has_session: boolean
  session_id: string
  status: string
  source: string
  created_at: string
  updated_at: string
  cookie_count: number
  auth_cookie_count: number
  expires_at: string | null
  expired: boolean
}

export interface RunInfo {
  file: string
  scraped_at: string
  query: string
  locations: string[]
  pages_fetched: number
  total_jobs: number
  stopped_reason: string
}

export interface RunListResponse {
  total: number
  limit: number
  offset: number
  items: RunInfo[]
}

export interface ApplicationEntry {
  jk: string
  company: string
  title: string
  status: string
  at: string
  indeed_url: string
}

export interface ApplicationListResponse {
  total: number
  limit: number
  offset: number
  items: ApplicationEntry[]
}

export interface ApplicationSummary {
  total: number
  status_counts: Record<string, number>
}

export interface MessageEntry {
  conversation_id: string
  company: string
  kind: string
  status: string
  body: string
  detail: string
  at: string
}

export interface MessageListResponse {
  total: number
  limit: number
  offset: number
  items: MessageEntry[]
}

export interface HealthInfo {
  status: string
  version: string
  state_dir: string
}

/** Query parameters accepted by `GET /api/jobs` (contract section 4.2). */
export interface JobQuery {
  q?: string
  location?: string
  company?: string
  status?: string
  limit?: number
  offset?: number
  sort?: string
  order?: string
}

/** Sort keys accepted by `GET /api/jobs`. */
export const JOB_SORT_FIELDS = [
  'last_seen',
  'first_seen',
  'title',
  'company',
  'salary',
] as const

export type JobSortField = (typeof JOB_SORT_FIELDS)[number]

/** Statuses recognised by the dataset (contract section 4.2). */
export const JOB_STATUSES = ['new', 'updated', 'unchanged'] as const

export type JobStatus = (typeof JOB_STATUSES)[number]

export type SortOrder = 'asc' | 'desc'

/**
 * A non-2xx response, a network failure, or a body that is not the JSON we
 * expect. Views catch this and render `<ErrorState>` with a retry action.
 */
export class ApiError extends Error {
  readonly status: number
  readonly url: string
  readonly detail: string

  constructor(message: string, status: number, url: string, detail = '') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
    this.detail = detail
  }

  /** True when the request never reached the backend (server down / proxy). */
  get isNetworkError(): boolean {
    return this.status === 0
  }
}

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')

/** Default request timeout in milliseconds. */
const REQUEST_TIMEOUT_MS = 15_000

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue
    const asString = String(value)
    if (asString === '') continue
    search.set(key, asString)
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const url = `${API_BASE_URL}${path}`
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  const onExternalAbort = (): void => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onExternalAbort, { once: true })
  }

  let response: Response
  try {
    response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === 'AbortError'
    if (aborted && signal?.aborted) {
      throw new ApiError('Request cancelled', 0, url)
    }
    const reason = error instanceof Error ? error.message : String(error)
    throw new ApiError(
      aborted
        ? `Request to ${url} timed out after ${REQUEST_TIMEOUT_MS} ms`
        : `Could not reach the API at ${url} (${reason})`,
      0,
      url,
      reason,
    )
  } finally {
    window.clearTimeout(timeoutId)
    if (signal) signal.removeEventListener('abort', onExternalAbort)
  }

  if (!response.ok) {
    let detail = ''
    try {
      const raw = await response.text()
      if (raw) {
        try {
          const parsed: unknown = JSON.parse(raw)
          if (parsed && typeof parsed === 'object' && 'detail' in parsed) {
            const value = (parsed as { detail: unknown }).detail
            detail = typeof value === 'string' ? value : JSON.stringify(value)
          } else {
            detail = raw
          }
        } catch {
          detail = raw
        }
      }
    } catch {
      /* body already consumed or unreadable — the status is enough */
    }
    throw new ApiError(
      `API request failed with ${response.status} ${response.statusText}`.trim(),
      response.status,
      url,
      detail,
    )
  }

  try {
    return (await response.json()) as T
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error)
    throw new ApiError(
      `API returned a malformed JSON body for ${url}`,
      response.status,
      url,
      reason,
    )
  }
}

/* ------------------------------------------------------------------ */
/* Endpoints — one function per contract section.                       */
/* ------------------------------------------------------------------ */

/** Section 4.1 */
export function getHealth(signal?: AbortSignal): Promise<HealthInfo> {
  return request<HealthInfo>('/health', signal)
}

/** Section 4.2 */
export function getJobs(query: JobQuery = {}, signal?: AbortSignal): Promise<JobListResponse> {
  return request<JobListResponse>(
    `/jobs${buildQuery({
      q: query.q,
      location: query.location,
      company: query.company,
      status: query.status,
      limit: query.limit,
      offset: query.offset,
      sort: query.sort,
      order: query.order,
    })}`,
    signal,
  )
}

/** Section 4.3 — throws `ApiError` with status 404 when the id is unknown. */
export function getJob(shortId: string, signal?: AbortSignal): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(shortId)}`, signal)
}

/** Section 4.4 */
export function getJobFacets(signal?: AbortSignal): Promise<JobFacets> {
  return request<JobFacets>('/jobs/facets', signal)
}

/** Section 4.5 — metadata only, never cookie values. */
export function getSession(signal?: AbortSignal): Promise<SessionInfo> {
  return request<SessionInfo>('/session', signal)
}

/** Section 4.6 */
export function getRuns(
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<RunListResponse> {
  return request<RunListResponse>(
    `/runs${buildQuery({ limit: params.limit, offset: params.offset })}`,
    signal,
  )
}

/** Section 4.7 */
export function getApplications(
  params: { limit?: number; offset?: number; status?: string } = {},
  signal?: AbortSignal,
): Promise<ApplicationListResponse> {
  return request<ApplicationListResponse>(
    `/applications${buildQuery({
      limit: params.limit,
      offset: params.offset,
      status: params.status,
    })}`,
    signal,
  )
}

/** Section 4.8 */
export function getApplicationSummary(signal?: AbortSignal): Promise<ApplicationSummary> {
  return request<ApplicationSummary>('/applications/summary', signal)
}

/** Section 4.9 */
export function getMessages(
  params: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<MessageListResponse> {
  return request<MessageListResponse>(
    `/messages${buildQuery({ limit: params.limit, offset: params.offset })}`,
    signal,
  )
}
