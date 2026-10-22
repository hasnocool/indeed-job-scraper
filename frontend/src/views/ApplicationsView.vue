<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { formatCount, formatDate, dash } from '../api/format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import MessageList from '../components/MessageList.vue'
import Pagination from '../components/Pagination.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { useApplicationsStore } from '../stores/applications'

const applications = useApplicationsStore()

/** The summary's status_counts as sorted `[status, count]` pairs. */
const summaryEntries = computed<Array<[string, number]>>(() => {
  const counts = applications.summary?.status_counts ?? {}
  return Object.entries(counts).sort((a, b) => b[1] - a[1])
})

onMounted(async () => {
  await applications.loadAll()
})

async function onStatusFilter(value: string): Promise<void> {
  await applications.setStatusFilter(value)
}

async function onPage(page: number): Promise<void> {
  await applications.goToPage(page)
}

async function onMessagesPage(page: number): Promise<void> {
  await applications.goToMessagesPage(page)
}

function onStatusChange(event: Event): void {
  const target = event.target
  if (target instanceof HTMLSelectElement) void onStatusFilter(target.value)
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1 class="page-title">Applications</h1>
        <p class="page-subtitle">
          The application ledger and the messages sent from Indeed. The ledger is
          append-only; the last entry for a given job key wins.
        </p>
      </div>
      <div class="page-actions">
        <button
          type="button"
          class="btn"
          :disabled="applications.loading || applications.messagesLoading"
          @click="applications.loadAll()"
        >
          Refresh
        </button>
      </div>
    </header>

    <!-- Status summary -->
    <section class="section summary-section" aria-label="Application status summary">
      <div class="section-header">
        <h2 class="section-title">Status summary</h2>
        <span v-if="applications.summary" class="section-hint">
          {{ formatCount(applications.summary.total) }} total
        </span>
      </div>

      <ErrorState
        v-if="applications.summaryError"
        :message="applications.summaryError"
        detail="The backend may be offline. Check that it is running on http://127.0.0.1:8001."
        @retry="applications.loadSummary()"
      />
      <LoadingState
        v-else-if="applications.loading && !applications.summary"
        label="Loading summary…"
        :rows="0"
      />
      <div v-else-if="applications.summary" class="grid grid-4">
        <div
          v-for="[status, count] in summaryEntries"
          :key="status"
          class="card card-pad summary-card"
        >
          <div class="summary-count">{{ formatCount(count) }}</div>
          <div class="summary-label"><StatusBadge :status="status" /></div>
        </div>
        <div v-if="summaryEntries.length === 0" class="card card-pad summary-empty">
          <span class="muted">The ledger is empty — no applications recorded yet.</span>
        </div>
      </div>
    </section>

    <!-- Ledger table -->
    <section class="section" aria-label="Application ledger">
      <div class="section-header">
        <h2 class="section-title">Ledger</h2>
        <div class="row-tight">
          <label class="visually-hidden" for="ledger-status">Filter by status</label>
          <select
            id="ledger-status"
            class="select status-select"
            :value="applications.statusFilter"
            :disabled="applications.loading"
            @change="onStatusChange"
          >
            <option value="">All statuses</option>
            <option v-for="status in applications.statusOptions" :key="status" :value="status">
              {{ status }}
            </option>
          </select>
        </div>
      </div>

      <div class="card ledger-card">
        <ErrorState
          v-if="applications.error"
          :message="applications.error"
          detail="The backend may be offline. Check that it is running on http://127.0.0.1:8001."
          @retry="applications.retry()"
        />

        <LoadingState
          v-else-if="applications.loading && applications.items.length === 0"
          label="Loading applications…"
        />

        <EmptyState
          v-else-if="applications.isEmpty"
          title="No applications yet"
          message="The application ledger is empty. Nothing has been applied to from here yet."
        />

        <template v-else>
          <div class="table-wrap">
            <table class="table">
              <caption class="visually-hidden">Application ledger entries.</caption>
              <thead>
                <tr>
                  <th scope="col">Title</th>
                  <th scope="col">Company</th>
                  <th scope="col">Status</th>
                  <th scope="col">At</th>
                  <th scope="col">Job key</th>
                  <th scope="col">Link</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="entry in applications.items" :key="entry.jk">
                  <td class="cell-strong">{{ dash(entry.title) }}</td>
                  <td class="cell-muted">{{ dash(entry.company) }}</td>
                  <td><StatusBadge :status="entry.status" /></td>
                  <td class="cell-muted nowrap">{{ formatDate(entry.at) }}</td>
                  <td class="cell-mono">{{ dash(entry.jk) }}</td>
                  <td>
                    <a
                      v-if="entry.indeed_url"
                      :href="entry.indeed_url"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Indeed ↗
                    </a>
                    <span v-else class="muted">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <Pagination
            :total="applications.total"
            :limit="applications.limit"
            :page="applications.page"
            :page-count="applications.pageCount"
            item-label="applications"
            @update:page="onPage"
          />
        </template>
      </div>
    </section>

    <!-- Sent messages -->
    <section class="section" aria-label="Sent messages">
      <div class="section-header">
        <h2 class="section-title">Sent messages</h2>
        <span v-if="applications.messagesTotal > 0" class="section-hint">
          {{ formatCount(applications.messagesTotal) }}
          {{ applications.messagesTotal === 1 ? 'message' : 'messages' }}, newest first
        </span>
      </div>

      <div class="card messages-card">
        <div class="card-body">
          <ErrorState
            v-if="applications.messagesError"
            :message="applications.messagesError"
            detail="The backend may be offline. Check that it is running on http://127.0.0.1:8001."
            @retry="applications.retryMessages()"
          />

          <LoadingState
            v-else-if="applications.messagesLoading && applications.messages.length === 0"
            label="Loading messages…"
            :rows="0"
          />

          <EmptyState
            v-else-if="applications.messagesEmpty"
            title="No messages sent"
            message="The sent-messages log is empty."
          />

          <MessageList v-else :messages="applications.messages" />
        </div>

        <Pagination
          v-if="!applications.messagesEmpty && !applications.messagesError"
          :total="applications.messagesTotal"
          :limit="applications.messagesLimit"
          :page="applications.messagesPage"
          :page-count="applications.messagesPageCount"
          item-label="messages"
          :show-page-size="false"
          @update:page="onMessagesPage"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.summary-section {
  margin-top: 0;
}

.summary-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.summary-count {
  font-size: var(--text-2xl);
  font-weight: var(--weight-bold);
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}

.summary-label {
  display: flex;
}

.summary-empty {
  grid-column: 1 / -1;
}

.status-select {
  width: auto;
  min-width: 160px;
  padding: 0.3rem 1.8rem 0.3rem 0.6rem;
  font-size: var(--text-xs);
}

.ledger-card,
.messages-card {
  overflow: hidden;
}
</style>
