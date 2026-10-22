<script setup lang="ts">
import { computed } from 'vue'

/**
 * A small coloured pill for a status string.
 * Unknown statuses fall back to a neutral tone.
 */
const props = withDefaults(
  defineProps<{
    /** The raw status value, e.g. "new", "submitted", "active". */
    status: string
    /** Optional override for the visible text. */
    label?: string
  }>(),
  { label: '' },
)

type Tone = 'success' | 'info' | 'warning' | 'danger' | 'neutral' | 'accent'

const tone = computed<Tone>(() => {
  switch (props.status.toLowerCase()) {
    case 'new':
    case 'active':
    case 'sent':
    case 'submitted':
    case 'ok':
      return 'success'
    case 'updated':
    case 'reserved':
    case 'general':
    case 'pending':
      return 'info'
    case 'unchanged':
      return 'neutral'
    case 'expiring':
    case 'expired':
    case 'warning':
      return 'warning'
    case 'failed':
    case 'revoked':
    case 'error':
      return 'danger'
    default:
      return 'accent'
  }
})

const text = computed(() => {
  if (props.label) return props.label
  if (!props.status) return 'unknown'
  return props.status
})
</script>

<template>
  <span class="badge" :class="`badge-${tone}`">{{ text }}</span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.15rem 0.5rem;
  border-radius: var(--radius-pill);
  border: 1px solid transparent;
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  line-height: 1.5;
  white-space: nowrap;
  text-transform: lowercase;
}

.badge-success {
  background: var(--color-success-soft);
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.badge-info {
  background: var(--color-info-soft);
  border-color: var(--color-info-border);
  color: var(--color-info);
}

.badge-warning {
  background: var(--color-warning-soft);
  border-color: var(--color-warning-border);
  color: var(--color-warning);
}

.badge-danger {
  background: var(--color-danger-soft);
  border-color: var(--color-danger-border);
  color: var(--color-danger);
}

.badge-neutral {
  background: var(--color-neutral-soft);
  border-color: var(--color-neutral-border);
  color: var(--color-text-muted);
}

.badge-accent {
  background: var(--color-accent-soft);
  border-color: var(--color-accent-border);
  color: var(--color-accent);
}
</style>
