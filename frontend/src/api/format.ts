/**
 * Display helpers.
 *
 * The dataset is sparse: empty strings are normal, not errors. Every field that
 * may be `""` is rendered through `dash()` so the UI never shows
 * `"undefined"` or `"null"`.
 */

/** The placeholder used for every empty / missing value. */
export const EMPTY_PLACEHOLDER = '—'

/**
 * Return `value` when it holds something meaningful, otherwise the em-dash
 * placeholder. `null`/`undefined` are treated as empty as well, even though
 * the contract promises `""`.
 */
export function dash(value: string | null | undefined): string {
  if (value === null || value === undefined) return EMPTY_PLACEHOLDER
  const trimmed = value.trim()
  return trimmed === '' ? EMPTY_PLACEHOLDER : value
}

/** True when the value is a non-empty string. Acts as a type guard. */
export function hasText(value: string | null | undefined): value is string {
  if (value === null || value === undefined) return false
  return value.trim() !== ''
}

/** True when the list holds at least one non-empty entry. */
export function hasItems(values: readonly string[] | null | undefined): boolean {
  if (!values || values.length === 0) return false
  return values.some((value) => hasText(value))
}

/**
 * Format an ISO-8601 timestamp for display.
 *
 * The backend stores timestamps exactly as it found them on disk, so the
 * string is parsed as-is. An unparsable value falls back to the raw text so
 * nothing is ever lost.
 */
export function formatTimestamp(value: string | null | undefined): string {
  if (!hasText(value)) return EMPTY_PLACEHOLDER
  const raw = value.trim()
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/** Format only the date part of a timestamp. */
export function formatDate(value: string | null | undefined): string {
  if (!hasText(value)) return EMPTY_PLACEHOLDER
  const raw = value.trim()
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return parsed.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  })
}

/**
 * Human-friendly relative time, e.g. "3 days ago" / "in 2 hours".
 * Falls back to the em-dash when there is nothing to compare against.
 */
export function formatRelative(value: string | null | undefined, now: number = Date.now()): string {
  if (!hasText(value)) return EMPTY_PLACEHOLDER
  const parsed = new Date(value.trim())
  if (Number.isNaN(parsed.getTime())) return EMPTY_PLACEHOLDER

  const deltaSeconds = Math.round((parsed.getTime() - now) / 1000)
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['second', 60],
    ['minute', 60],
    ['hour', 24],
    ['day', 7],
    ['week', 4.34524],
    ['month', 12],
    ['year', Number.POSITIVE_INFINITY],
  ]

  let amount = deltaSeconds
  for (const [unit, size] of units) {
    if (Math.abs(amount) < size) {
      return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
        Math.round(amount),
        unit,
      )
    }
    amount /= size
  }
  return new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
    Math.round(amount),
    'year',
  )
}

/** Truncate long free text for table cells, adding an ellipsis when cut. */
export function truncate(value: string | null | undefined, maxLength: number): string {
  if (!hasText(value)) return EMPTY_PLACEHOLDER
  const text = value.trim()
  if (text.length <= maxLength) return text
  return `${text.slice(0, maxLength - 1).trimEnd()}…`
}

/** Format an integer count with thousands separators. */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY_PLACEHOLDER
  return value.toLocaleString()
}
