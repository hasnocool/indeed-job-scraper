<script setup lang="ts">
import { computed } from 'vue'

import type { SessionInfo } from '../api/client'
import { dash, formatRelative, formatTimestamp } from '../api/format'
import StatusBadge from './StatusBadge.vue'

/**
 * Cookie session health card. Shows **metadata only** — the backend never
 * returns cookie names or values, and neither does this component.
 */
const props = defineProps<{ session: SessionInfo }>()

const health = computed(() => {
  if (!props.session.has_session) {
    return { tone: 'danger' as const, label: 'No session', headline: 'No cookie session on disk' }
  }
  if (props.session.expired) {
    return { tone: 'warning' as const, label: 'Expired', headline: 'Session has expired' }
  }
  if (props.session.status === 'revoked') {
    return { tone: 'danger' as const, label: 'Revoked', headline: 'Session was revoked' }
  }
  if (props.session.status === 'active') {
    return { tone: 'success' as const, label: 'Active', headline: 'Session is active' }
  }
  return { tone: 'info' as const, label: props.session.status, headline: `Session is ${props.session.status}` }
})
</script>

<template>
  <article class="card session-card" :class="`tone-${health.tone}`">
    <header class="session-header">
      <div>
        <h2 class="card-title">Cookie session</h2>
        <p class="session-headline">{{ health.headline }}</p>
      </div>
      <StatusBadge :status="health.label" />
    </header>

    <dl class="deflist">
      <dt>Session ID</dt>
      <dd class="mono">{{ dash(session.session_id) }}</dd>

      <dt>Status</dt>
      <dd><StatusBadge :status="session.status" /></dd>

      <dt>Source</dt>
      <dd>{{ dash(session.source) }}</dd>

      <dt>Created at</dt>
      <dd>
        {{ formatTimestamp(session.created_at) }}
        <span v-if="session.created_at" class="subtle"> ({{ formatRelative(session.created_at) }})</span>
      </dd>

      <dt>Updated at</dt>
      <dd>
        {{ formatTimestamp(session.updated_at) }}
        <span v-if="session.updated_at" class="subtle"> ({{ formatRelative(session.updated_at) }})</span>
      </dd>

      <dt>Expires at</dt>
      <dd>
        <template v-if="session.expires_at">
          {{ formatTimestamp(session.expires_at) }}
          <span class="subtle"> ({{ formatRelative(session.expires_at) }})</span>
        </template>
        <template v-else>—</template>
      </dd>

      <dt>Expired</dt>
      <dd>{{ session.expired ? 'Yes' : 'No' }}</dd>

      <dt>Cookies</dt>
      <dd>{{ session.cookie_count }} total</dd>

      <dt>Auth cookies</dt>
      <dd>{{ session.auth_cookie_count }} recognised</dd>
    </dl>
  </article>
</template>

<style scoped>
.session-card {
  border-top: 3px solid var(--color-border-strong);
}

.tone-success {
  border-top-color: var(--color-success);
}

.tone-warning {
  border-top-color: var(--color-warning);
}

.tone-danger {
  border-top-color: var(--color-danger);
}

.tone-info {
  border-top-color: var(--color-info);
}

.session-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border-subtle);
}

.session-headline {
  margin-top: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.deflist {
  padding: var(--space-5);
}
</style>
