<script setup lang="ts">
/**
 * Shown when a request succeeded but returned nothing.
 * Always offers a way out when an action is supplied.
 */
withDefaults(
  defineProps<{
    title?: string
    message?: string
    actionLabel?: string
  }>(),
  {
    title: 'Nothing to show',
    message: 'There is no data here yet.',
    actionLabel: '',
  },
)

const emit = defineEmits<{ action: [] }>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.6">
        <rect x="3" y="5" width="18" height="14" rx="2.5" />
        <path d="M3 10h18" stroke-linecap="round" />
        <path d="M8.5 14.5h7" stroke-linecap="round" />
      </svg>
    </div>
    <h3 class="empty-title">{{ title }}</h3>
    <p class="empty-message">{{ message }}</p>
    <button v-if="actionLabel" type="button" class="btn" @click="emit('action')">
      {{ actionLabel }}
    </button>
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-8) var(--space-5);
  text-align: center;
}

.empty-icon {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: var(--radius-pill);
  background: var(--color-bg-sunken);
  color: var(--color-text-subtle);
}

.empty-title {
  font-size: var(--text-md);
  font-weight: var(--weight-semibold);
}

.empty-message {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  max-width: 52ch;
}
</style>
