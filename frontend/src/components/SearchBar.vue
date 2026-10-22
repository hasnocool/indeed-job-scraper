<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

/**
 * Debounced search input.
 *
 * The user types freely; `search` is emitted ~250 ms after the last
 * keystroke. Pressing Enter flushes the query immediately.
 */
const props = withDefaults(
  defineProps<{
    /** Current query value (v-model style). */
    modelValue: string
    placeholder?: string
    label?: string
    /** Debounce delay in milliseconds. */
    debounce?: number
    disabled?: boolean
  }>(),
  {
    placeholder: 'Search title, company, location, snippet…',
    label: 'Search jobs',
    debounce: 250,
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  search: [value: string]
  clear: []
}>()

const localValue = ref(props.modelValue)
let timer: number | undefined

watch(
  () => props.modelValue,
  (next) => {
    if (next !== localValue.value) localValue.value = next
  },
)

function schedule(value: string): void {
  if (timer !== undefined) window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    timer = undefined
    emit('search', value)
  }, props.debounce)
}

function onInput(event: Event): void {
  const target = event.target
  if (!(target instanceof HTMLInputElement)) return
  localValue.value = target.value
  emit('update:modelValue', target.value)
  schedule(target.value)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter') return
  event.preventDefault()
  if (timer !== undefined) {
    window.clearTimeout(timer)
    timer = undefined
  }
  emit('search', localValue.value)
}

function clear(): void {
  if (timer !== undefined) {
    window.clearTimeout(timer)
    timer = undefined
  }
  localValue.value = ''
  emit('update:modelValue', '')
  emit('clear')
  emit('search', '')
}

onBeforeUnmount(() => {
  if (timer !== undefined) window.clearTimeout(timer)
})
</script>

<template>
  <div class="search-bar">
    <label class="visually-hidden" :for="`search-${label}`">{{ label }}</label>
    <div class="search-field">
      <svg
        class="search-icon"
        viewBox="0 0 24 24"
        width="16"
        height="16"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" stroke-linecap="round" />
      </svg>
      <input
        :id="`search-${label}`"
        class="input search-input"
        type="search"
        :value="localValue"
        :placeholder="placeholder"
        :disabled="disabled"
        autocomplete="off"
        @input="onInput"
        @keydown="onKeydown"
      />
      <button
        v-if="localValue !== ''"
        type="button"
        class="search-clear"
        aria-label="Clear search"
        :disabled="disabled"
        @click="clear"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.search-bar {
  flex: 1 1 320px;
  min-width: 220px;
}

.search-field {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 0.7rem;
  color: var(--color-text-subtle);
  pointer-events: none;
}

.search-input {
  padding-left: 2.1rem;
  padding-right: 2.1rem;
  appearance: none;
}

.search-input::-webkit-search-cancel-button {
  display: none;
}

.search-clear {
  position: absolute;
  right: 0.4rem;
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: var(--radius-pill);
  background: var(--color-bg-sunken);
  color: var(--color-text-muted);
  font-size: var(--text-md);
  line-height: 1;
  cursor: pointer;
}

.search-clear:hover:not(:disabled) {
  background: var(--color-bg-hover);
  color: var(--color-text);
}
</style>
