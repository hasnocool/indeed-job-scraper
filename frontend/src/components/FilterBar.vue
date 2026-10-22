<script setup lang="ts">
import { computed } from 'vue'

/**
 * The location / company / status dropdowns, populated from
 * `GET /api/jobs/facets`. Every option list is de-duplicated and free of
 * empty strings by the backend.
 */
const props = withDefaults(
  defineProps<{
    locations: readonly string[]
    companies: readonly string[]
    statuses: readonly string[]
    location: string
    company: string
    status: string
    disabled?: boolean
    /** Non-fatal problem while loading the facets (e.g. backend down). */
    facetsError?: string
  }>(),
  {
    disabled: false,
    facetsError: '',
  },
)

const emit = defineEmits<{
  'update:location': [value: string]
  'update:company': [value: string]
  'update:status': [value: string]
  clear: []
}>()

const hasAnyFilter = computed(
  () => props.location !== '' || props.company !== '' || props.status !== '',
)

function onLocationChange(event: Event): void {
  const target = event.target
  if (target instanceof HTMLSelectElement) emit('update:location', target.value)
}

function onCompanyChange(event: Event): void {
  const target = event.target
  if (target instanceof HTMLSelectElement) emit('update:company', target.value)
}

function onStatusChange(event: Event): void {
  const target = event.target
  if (target instanceof HTMLSelectElement) emit('update:status', target.value)
}
</script>

<template>
  <div class="filter-bar">
    <div class="field filter-field">
      <label class="field-label" for="filter-location">Location</label>
      <select
        id="filter-location"
        class="select"
        :value="location"
        :disabled="disabled"
        @change="onLocationChange"
      >
        <option value="">All locations</option>
        <option v-for="option in locations" :key="option" :value="option">{{ option }}</option>
      </select>
    </div>

    <div class="field filter-field">
      <label class="field-label" for="filter-company">Company</label>
      <select
        id="filter-company"
        class="select"
        :value="company"
        :disabled="disabled"
        @change="onCompanyChange"
      >
        <option value="">All companies</option>
        <option v-for="option in companies" :key="option" :value="option">{{ option }}</option>
      </select>
    </div>

    <div class="field filter-field">
      <label class="field-label" for="filter-status">Status</label>
      <select
        id="filter-status"
        class="select"
        :value="status"
        :disabled="disabled"
        @change="onStatusChange"
      >
        <option value="">All statuses</option>
        <option v-for="option in statuses" :key="option" :value="option">{{ option }}</option>
      </select>
    </div>

    <button
      v-if="hasAnyFilter"
      type="button"
      class="btn btn-ghost btn-sm clear-button"
      :disabled="disabled"
      @click="emit('clear')"
    >
      Clear filters
    </button>

    <p v-if="facetsError" class="filter-warning" role="status">
      Filter options unavailable — showing all values.
    </p>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.filter-field {
  flex: 0 1 200px;
  min-width: 150px;
}

.filter-field .select {
  min-width: 0;
}

.clear-button {
  margin-bottom: 1px;
}

.filter-warning {
  flex: 1 1 100%;
  font-size: var(--text-xs);
  color: var(--color-warning);
}
</style>
