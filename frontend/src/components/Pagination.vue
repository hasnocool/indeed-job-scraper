<script setup lang="ts">
import { computed } from 'vue'

import { formatCount } from '../api/format'

/**
 * Pagination driven by the API's real `total` field.
 * Emits the 1-based page number the user wants to see.
 */
const props = withDefaults(
  defineProps<{
    /** Total number of matching records (after filtering). */
    total: number
    /** Page size. */
    limit: number
    /** Current 1-based page number. */
    page: number
    /** Total number of pages (at least 1). */
    pageCount: number
    /** Label for the entity being paged, e.g. "jobs". */
    itemLabel?: string
    /** When false, the per-page selector is hidden. */
    showPageSize?: boolean
    pageSizes?: readonly number[]
  }>(),
  {
    itemLabel: 'records',
    showPageSize: true,
    pageSizes: () => [10, 25, 50, 100],
  },
)

const emit = defineEmits<{
  'update:page': [page: number]
  'update:limit': [limit: number]
}>()

const firstIndex = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.limit + 1))
const lastIndex = computed(() => Math.min(props.page * props.limit, props.total))

const canPrev = computed(() => props.page > 1)
const canNext = computed(() => props.page < props.pageCount)

/** Compact page window: 1 … 4 5 6 … 20 */
const pageNumbers = computed<Array<number | 'gap'>>(() => {
  const count = props.pageCount
  const current = props.page
  if (count <= 7) {
    return Array.from({ length: count }, (_, index) => index + 1)
  }
  const pages: Array<number | 'gap'> = [1]
  const start = Math.max(2, current - 1)
  const end = Math.min(count - 1, current + 1)
  if (start > 2) pages.push('gap')
  for (let page = start; page <= end; page += 1) pages.push(page)
  if (end < count - 1) pages.push('gap')
  pages.push(count)
  return pages
})

function goTo(page: number): void {
  const clamped = Math.min(Math.max(1, page), props.pageCount)
  if (clamped === props.page) return
  emit('update:page', clamped)
}

function onPageSizeChange(event: Event): void {
  const target = event.target
  if (!(target instanceof HTMLSelectElement)) return
  const value = Number.parseInt(target.value, 10)
  if (Number.isFinite(value) && value > 0) emit('update:limit', value)
}
</script>

<template>
  <nav class="pagination" aria-label="Pagination">
    <div class="pagination-summary">
      <span v-if="total > 0">
        Showing <strong>{{ formatCount(firstIndex) }}–{{ formatCount(lastIndex) }}</strong> of
        <strong>{{ formatCount(total) }}</strong> {{ itemLabel }}
      </span>
      <span v-else>No {{ itemLabel }} to show</span>
    </div>

    <div class="pagination-controls">
      <label v-if="showPageSize" class="page-size">
        <span class="visually-hidden">Items per page</span>
        <select class="select" :value="limit" @change="onPageSizeChange">
          <option v-for="size in pageSizes" :key="size" :value="size">{{ size }} / page</option>
        </select>
      </label>

      <div class="page-buttons">
        <button
          type="button"
          class="btn btn-sm"
          :disabled="!canPrev"
          aria-label="Previous page"
          @click="goTo(page - 1)"
        >
          ←
        </button>

        <template v-for="(entry, index) in pageNumbers" :key="`${entry}-${index}`">
          <span v-if="entry === 'gap'" class="page-gap" aria-hidden="true">…</span>
          <button
            v-else
            type="button"
            class="btn btn-sm page-number"
            :class="{ 'is-current': entry === page }"
            :aria-current="entry === page ? 'page' : undefined"
            :aria-label="`Page ${entry}`"
            @click="goTo(entry)"
          >
            {{ entry }}
          </button>
        </template>

        <button
          type="button"
          class="btn btn-sm"
          :disabled="!canNext"
          aria-label="Next page"
          @click="goTo(page + 1)"
        >
          →
        </button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--color-border-subtle);
}

.pagination-summary {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.pagination-summary strong {
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

.pagination-controls {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.page-size .select {
  width: auto;
  padding: 0.3rem 1.8rem 0.3rem 0.5rem;
  font-size: var(--text-xs);
}

.page-buttons {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.page-number {
  min-width: 2rem;
  font-variant-numeric: tabular-nums;
}

.page-number.is-current {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: #fff;
}

.page-gap {
  padding: 0 0.25rem;
  color: var(--color-text-subtle);
  font-size: var(--text-sm);
}
</style>
