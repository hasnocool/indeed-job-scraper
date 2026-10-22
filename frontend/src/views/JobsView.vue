<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import type { JobSortField } from '../api/client'
import { formatCount } from '../api/format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import FilterBar from '../components/FilterBar.vue'
import JobTable from '../components/JobTable.vue'
import LoadingState from '../components/LoadingState.vue'
import Pagination from '../components/Pagination.vue'
import SearchBar from '../components/SearchBar.vue'
import { useJobsStore } from '../stores/jobs'

const jobs = useJobsStore()

/** Local mirror of the search box so the input stays responsive. */
const searchTerm = ref(jobs.filters.q)

onMounted(async () => {
  await Promise.all([jobs.loadFacets(), jobs.load()])
})

// Keep the box in sync when the store resets the filters.
watch(
  () => jobs.filters.q,
  (value) => {
    if (value !== searchTerm.value) searchTerm.value = value
  },
)

async function onSearch(value: string): Promise<void> {
  searchTerm.value = value
  await jobs.setFilter('q', value)
}

async function onLocationChange(value: string): Promise<void> {
  await jobs.setFilter('location', value)
}

async function onCompanyChange(value: string): Promise<void> {
  await jobs.setFilter('company', value)
}

async function onStatusChange(value: string): Promise<void> {
  await jobs.setFilter('status', value)
}

async function onClearFilters(): Promise<void> {
  searchTerm.value = ''
  await jobs.clearFilters()
}

async function onSort(field: JobSortField): Promise<void> {
  await jobs.setSort(field)
}

async function onPageChange(page: number): Promise<void> {
  await jobs.goToPage(page)
}

async function onLimitChange(limit: number): Promise<void> {
  await jobs.setLimit(limit)
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1 class="page-title">Jobs</h1>
        <p class="page-subtitle">
          The master job dataset, filtered and paginated by the backend.
          <template v-if="jobs.total > 0">
            <strong>{{ formatCount(jobs.total) }}</strong>
            {{ jobs.total === 1 ? 'job' : 'jobs' }} match the current filters.
          </template>
        </p>
      </div>
    </header>

    <section class="card toolbar" aria-label="Filters">
      <div class="toolbar-row">
        <SearchBar
          v-model="searchTerm"
          label="Search jobs"
          placeholder="Search title, company, location, snippet, salary…"
          :disabled="jobs.loading"
          @search="onSearch"
        />
        <FilterBar
          :locations="jobs.locationOptions"
          :companies="jobs.companyOptions"
          :statuses="jobs.statusOptions"
          :location="jobs.filters.location"
          :company="jobs.filters.company"
          :status="jobs.filters.status"
          :disabled="jobs.loading"
          :facets-error="jobs.facetsError ?? ''"
          @update:location="onLocationChange"
          @update:company="onCompanyChange"
          @update:status="onStatusChange"
          @clear="onClearFilters"
        />
      </div>
    </section>

    <section class="card results" aria-label="Job results">
      <!-- Error state: a failed fetch never renders a blank page. -->
      <ErrorState
        v-if="jobs.error"
        :message="jobs.error"
        detail="The backend may be offline. Check that it is running on http://127.0.0.1:8001."
        @retry="jobs.retry()"
      />

      <!-- Loading state -->
      <LoadingState v-else-if="jobs.loading && jobs.items.length === 0" label="Loading jobs…" />

      <!-- Empty state -->
      <EmptyState
        v-else-if="jobs.isEmpty"
        title="No jobs match these filters"
        message="Try clearing the search box or widening the location, company and status filters."
        :action-label="jobs.hasFilters ? 'Clear all filters' : ''"
        @action="onClearFilters"
      />

      <template v-else>
        <JobTable
          :jobs="jobs.items"
          :sort="jobs.sort"
          :order="jobs.order"
          :busy="jobs.loading"
          @sort="onSort"
        />
        <Pagination
          :total="jobs.total"
          :limit="jobs.limit"
          :page="jobs.page"
          :page-count="jobs.pageCount"
          item-label="jobs"
          @update:page="onPageChange"
          @update:limit="onLimitChange"
        />
      </template>
    </section>
  </div>
</template>

<style scoped>
.toolbar {
  padding: var(--space-4);
  margin-bottom: var(--space-5);
}

.toolbar-row {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.results {
  overflow: hidden;
}
</style>
