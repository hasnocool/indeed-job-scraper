<script setup lang="ts">
/**
 * The single reusable error surface for the whole app.
 *
 * Every view renders this when a fetch fails, so a failed request never
 * results in a blank page. The retry button re-runs the failed request.
 */
withDefaults(
  defineProps<{
    /** The error message to show. */
    message?: string
    /** Optional secondary detail, e.g. the HTTP status or the failing URL. */
    detail?: string
    /** Label of the retry button. */
    retryLabel?: string
    /** When false the retry button is not rendered (the action is not possible). */
    retryable?: boolean
  }>(),
  {
    message: 'Something went wrong while loading this data.',
    detail: '',
    retryLabel: 'Retry',
    retryable: true,
  },
)

const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="error-state" role="alert">
    <div class="error-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.7">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5v5.5" stroke-linecap="round" />
        <circle cx="12" cy="16.4" r="0.9" fill="currentColor" stroke="none" />
      </svg>
    </div>
    <div class="error-body">
      <h3 class="error-title">Could not load this data</h3>
      <p class="error-message">{{ message }}</p>
      <p v-if="detail" class="error-detail">{{ detail }}</p>
    </div>
    <button v-if="retryable" type="button" class="btn btn-primary" @click="emit('retry')">
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 11a8 8 0 1 0-2.3 5.7" stroke-linecap="round" />
        <path d="M20 5v6h-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      {{ retryLabel }}
    </button>
  </div>
</template>

<style scoped>
.error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-7) var(--space-5);
  text-align: center;
  background: var(--color-danger-soft);
  border: 1px solid var(--color-danger-border);
  border-radius: var(--radius-lg);
}

.error-icon {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-pill);
  background: var(--color-bg-elevated);
  color: var(--color-danger);
}

.error-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.error-title {
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
  color: var(--color-danger);
}

.error-message {
  font-size: var(--text-sm);
  color: var(--color-text);
  max-width: 60ch;
  overflow-wrap: anywhere;
}

.error-detail {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  overflow-wrap: anywhere;
}
</style>
