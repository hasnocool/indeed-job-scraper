<script setup lang="ts">
import { RouterLink } from 'vue-router'

import type { Job, JobSortField, SortOrder } from '../api/client'
import { dash, formatRelative } from '../api/format'
import StatusBadge from './StatusBadge.vue'

/**
 * The master job list table. Rows link to `/jobs/:shortId`.
 * Sorting is controlled by the parent (the store owns the query state).
 */
withDefaults(
  defineProps<{
    jobs: Job[]
    sort?: JobSortField
    order?: SortOrder
    /** Set while a new page is loading so the table can dim. */
    busy?: boolean
  }>(),
  {
    sort: 'last_seen',
    order: 'desc',
    busy: false,
  },
)

const emit = defineEmits<{ sort: [field: JobSortField] }>()

interface Column {
  key: string
  label: string
  sortable: boolean
  field?: JobSortField
}

const columns: Column[] = [
  { key: 'title', label: 'Title', sortable: true, field: 'title' },
  { key: 'company', label: 'Company', sortable: true, field: 'company' },
  { key: 'location', label: 'Location', sortable: false },
  { key: 'salary', label: 'Salary', sortable: true, field: 'salary' },
  { key: 'schedule', label: 'Schedule', sortable: false },
  { key: 'status', label: 'Status', sortable: false },
  { key: 'seen_count', label: 'Seen', sortable: false },
  { key: 'last_seen', label: 'Last seen', sortable: true, field: 'last_seen' },
]

function ariaSort(
  field: JobSortField,
  sort: JobSortField,
  order: SortOrder,
): 'ascending' | 'descending' | 'none' | undefined {
  if (field !== sort) return undefined
  return order === 'asc' ? 'ascending' : 'descending'
}
</script>

<template>
  <div class="table-wrap" :class="{ 'is-busy': busy }">
    <table class="table">
      <caption class="visually-hidden">
        Master job list. Sortable columns: title, company, salary and last seen.
      </caption>
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column.key"
            :aria-sort="column.field ? ariaSort(column.field, sort, order) : undefined"
            :class="{ 'is-sortable': column.sortable }"
          >
            <button
              v-if="column.sortable && column.field"
              type="button"
              class="sort-button"
              @click="emit('sort', column.field)"
            >
              <span>{{ column.label }}</span>
              <span class="sort-icon" aria-hidden="true">
                {{ sort === column.field ? (order === 'asc' ? '↑' : '↓') : '↕' }}
              </span>
            </button>
            <span v-else>{{ column.label }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="job in jobs" :key="job.jk || job.short_id">
          <td class="cell-strong">
            <RouterLink class="job-link" :to="{ name: 'job-detail', params: { shortId: job.short_id } }">
              {{ dash(job.title) }}
            </RouterLink>
            <div v-if="job.posted" class="cell-sub">{{ job.posted }}</div>
          </td>
          <td class="cell-muted">{{ dash(job.company) }}</td>
          <td class="cell-muted">{{ dash(job.location) }}</td>
          <td class="cell-muted">{{ dash(job.salary) }}</td>
          <td class="cell-muted">{{ dash(job.schedule) }}</td>
          <td><StatusBadge :status="job.status" /></td>
          <td class="num cell-muted">{{ job.seen_count }}</td>
          <td class="cell-muted nowrap" :title="job.last_seen">
            {{ formatRelative(job.last_seen) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.is-busy {
  opacity: 0.55;
  transition: opacity var(--transition-base);
  pointer-events: none;
}

.job-link {
  color: var(--color-text);
  font-weight: var(--weight-semibold);
}

.job-link:hover {
  color: var(--color-accent);
}

.cell-sub {
  margin-top: 2px;
  font-size: var(--text-xs);
  color: var(--color-text-subtle);
}

.sort-button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 0;
  border: none;
  background: none;
  color: inherit;
  font: inherit;
  text-transform: inherit;
  letter-spacing: inherit;
  cursor: pointer;
}

.sort-button:hover {
  color: var(--color-text);
}

.sort-icon {
  font-size: var(--text-xs);
  opacity: 0.7;
}
</style>
