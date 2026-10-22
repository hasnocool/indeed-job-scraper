<script setup lang="ts">
import { onMounted } from 'vue'

import { formatCount } from '../api/format'
import EmptyState from '../components/EmptyState.vue'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import Pagination from '../components/Pagination.vue'
import RunTable from '../components/RunTable.vue'
import SessionCard from '../components/SessionCard.vue'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()

onMounted(async () => {
  await session.loadAll()
})

async function onRunsPage(page: number): Promise<void> {
  await session.goToRunsPage(page)
}
</script>

<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1 class="page-title">Session</h1>
        <p class="page-subtitle">
          Cookie session health and the scrape run history. The API returns session
          <em>metadata only</em> — cookie names and values are never exposed.
        </p>
      </div>
      <div class="page-actions">
        <button
          type="button"
          class="btn"
          :disabled="session.sessionLoading || session.runsLoading"
          @click="session.loadAll()"
        >
          Refresh
        </button>
      </div>
    </header>

    <!-- Session card: error / loading / content -->
    <ErrorState
      v-if="session.sessionError"
      :message="session.sessionError"
      detail="The backend may be offline. Check that it is running on http://127.0.0.1:8001."
      @retry="session.retrySession()"
    />
    <LoadingState
      v-else-if="session.sessionLoading && !session.session"
      label="Loading session…"
      :rows="0"
    />
    <SessionCard v-else-if="session.session" :session="session.session" />

    <section class="section">
      <div class="section-header">
        <h2 class="section-title">Scrape runs</h2>
        <span v-if="session.runsTotal > 0" class="section-hint">
          {{ formatCount(session.runsTotal) }}
          {{ session.runsTotal === 1 ? 'run' : 'runs' }} recorded, newest first
        </span>
      </div>

      <div class="card runs-card">
        <ErrorState
          v-if="session.runsError"
          :message="session.runsError"
          detail="The backend may be offline. Check that it is running on http://127.0.0.1:8001."
          @retry="session.retryRuns()"
        />

        <LoadingState
          v-else-if="session.runsLoading && session.runs.length === 0"
          label="Loading run history…"
        />

        <EmptyState
          v-else-if="session.runsEmpty"
          title="No scrape runs recorded"
          message="The runs directory is empty — no scrape has been ingested yet."
        />

        <template v-else>
          <RunTable :runs="session.runs" />
          <Pagination
            :total="session.runsTotal"
            :limit="session.runsLimit"
            :page="session.runsPage"
            :page-count="session.runsPageCount"
            item-label="runs"
            :show-page-size="false"
            @update:page="onRunsPage"
          />
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.runs-card {
  overflow: hidden;
}
</style>
