<script setup lang="ts">
/** Placeholder shown while a request is in flight. */
withDefaults(
  defineProps<{
    label?: string
    /** Number of skeleton rows to draw for table-shaped loads. */
    rows?: number
  }>(),
  {
    label: 'Loading…',
    rows: 4,
  },
)
</script>

<template>
  <div class="loading-state" role="status" aria-live="polite">
    <div class="loading-spinner" aria-hidden="true" />
    <p class="loading-label">{{ label }}</p>
    <div v-if="rows > 0" class="loading-skeleton" aria-hidden="true">
      <div v-for="row in rows" :key="row" class="loading-skeleton-row" />
    </div>
  </div>
</template>

<style scoped>
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-8) var(--space-5);
  color: var(--color-text-muted);
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border-strong);
  border-top-color: var(--color-accent);
  border-radius: 50%;
  animation: loading-spin 720ms linear infinite;
}

@keyframes loading-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .loading-spinner {
    animation-duration: 2400ms;
  }
}

.loading-label {
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
}

.loading-skeleton {
  width: 100%;
  max-width: 720px;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.loading-skeleton-row {
  height: 14px;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    90deg,
    var(--color-bg-sunken) 25%,
    var(--color-bg-hover) 37%,
    var(--color-bg-sunken) 63%
  );
  background-size: 400% 100%;
  animation: loading-shimmer 1.4s ease infinite;
}

.loading-skeleton-row:nth-child(odd) {
  width: 88%;
}

@keyframes loading-shimmer {
  0% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0 50%;
  }
}
</style>
