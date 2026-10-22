<script setup lang="ts">
import type { MessageEntry } from '../api/client'
import { dash, formatTimestamp } from '../api/format'
import StatusBadge from './StatusBadge.vue'

/**
 * Sent Indeed messages.
 *
 * The message body is rendered as **text** with `white-space: pre-wrap` so the
 * line breaks survive. It is never interpreted as HTML — the contract's
 * message bodies are plain text and must not be able to inject markup.
 */
defineProps<{ messages: MessageEntry[] }>()
</script>

<template>
  <ul class="message-list">
    <li v-for="(message, index) in messages" :key="`${message.conversation_id}-${index}`" class="message">
      <header class="message-header">
        <div class="message-ident">
          <span class="message-company">{{ dash(message.company) }}</span>
          <StatusBadge :status="message.status" />
          <span v-if="message.kind" class="message-kind">{{ message.kind }}</span>
        </div>
        <time class="message-time" :datetime="message.at">{{ formatTimestamp(message.at) }}</time>
      </header>

      <!-- Plain text only: interpolation + pre-wrap, never v-html. -->
      <pre class="message-body">{{ message.body }}</pre>

      <p v-if="message.detail" class="message-detail">{{ message.detail }}</p>

      <p v-if="message.conversation_id" class="message-conversation mono">
        conversation: {{ message.conversation_id }}
      </p>
    </li>
  </ul>
</template>

<style scoped>
.message-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.message {
  padding: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.message-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.message-ident {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.message-company {
  font-weight: var(--weight-semibold);
  font-size: var(--text-sm);
}

.message-kind {
  padding: 0.1rem 0.4rem;
  border-radius: var(--radius-sm);
  background: var(--color-bg-sunken);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.message-time {
  font-size: var(--text-xs);
  color: var(--color-text-subtle);
  white-space: nowrap;
}

.message-body {
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-sunken);
  color: var(--color-text);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  line-height: var(--leading-relaxed);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.message-detail {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.message-conversation {
  margin-top: var(--space-2);
  color: var(--color-text-subtle);
  overflow-wrap: anywhere;
}
</style>
