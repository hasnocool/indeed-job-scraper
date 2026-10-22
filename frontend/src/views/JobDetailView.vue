<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { ApiError, getJob, type Job } from '../api/client'
import { dash, formatCount, formatRelative, formatTimestamp } from '../api/format'
import ErrorState from '../components/ErrorState.vue'
import LoadingState from '../components/LoadingState.vue'
import StatusBadge from '../components/StatusBadge.vue'

const props = defineProps<{ shortId: string }>()

const job = ref<Job | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const errorDetail = ref('')
const notFound = ref(false)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  errorDetail.value = ''
  notFound.value = false
  try {
    job.value = await getJob(props.shortId)
  } catch (caught) {
    if (caught instanceof Error && caught.name === 'AbortError') return
    job.value = null
    if (caught instanceof ApiError) {
      error.value = caught.message
      errorDetail.value = caught.detail
      notFound.value = caught.status === 404
    } else if (caught instanceof Error) {
      error.value = caught.message
      errorDetail.value = ''
      notFound.value = false
    } else {
      error.value = 'An unexpected error occurred.'
      errorDetail.value = ''
      notFound.value = false
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)

watch(() => props.shortId, load)

const hasMatches = computed(() => (job.value?.matches.length ?? 0) > 0)
</script>

<template>
  <div class="page">
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <RouterLink :to="{ name: 'jobs' }">← Back to jobs</RouterLink>
    </nav>

    <!-- Error state -->
    <ErrorState
      v-if="error"
      :message="error"
      :detail="errorDetail"
      :retry-label="notFound ? 'Try again' : 'Retry'"
      @retry="load"
    />

    <!-- Loading state -->
    <LoadingState v-else-if="loading && !job" label="Loading job…" />

    <template v-else-if="job">
      <header class="page-header">
        <div>
          <h1 class="page-title">{{ dash(job.title) }}</h1>
          <p class="page-subtitle">
            <span v-if="job.company">{{ job.company }} · </span>
            <span>{{ dash(job.location) }}</span>
          </p>
          <div class="row-tight detail-badges">
            <StatusBadge :status="job.status" />
            <span class="mono subtle">short_id: {{ job.short_id }}</span>
          </div>
        </div>
        <div class="page-actions">
          <a
            v-if="job.url"
            class="btn btn-primary"
            :href="job.url"
            target="_blank"
            rel="noopener noreferrer"
          >
            Open on Indeed ↗
          </a>
        </div>
      </header>

      <div class="detail-grid">
        <section class="card">
          <header class="card-header">
            <h2 class="card-title">Overview</h2>
          </header>
          <div class="card-body">
            <dl class="deflist">
              <dt>Job key (jk)</dt>
              <dd class="mono">{{ dash(job.jk) }}</dd>

              <dt>Title</dt>
              <dd>{{ dash(job.title) }}</dd>

              <dt>Company</dt>
              <dd>{{ dash(job.company) }}</dd>

              <dt>Location</dt>
              <dd>{{ dash(job.location) }}</dd>

              <dt>Salary</dt>
              <dd>{{ dash(job.salary) }}</dd>

              <dt>Schedule</dt>
              <dd>{{ dash(job.schedule) }}</dd>

              <dt>Posted</dt>
              <dd>{{ dash(job.posted) }}</dd>

              <dt>Status</dt>
              <dd><StatusBadge :status="job.status" /></dd>

              <dt>Seen count</dt>
              <dd>{{ formatCount(job.seen_count) }}</dd>

              <dt>Duplicate of</dt>
              <dd>
                <RouterLink
                  v-if="job.duplicate_of"
                  class="mono"
                  :to="{ name: 'job-detail', params: { shortId: job.duplicate_of } }"
                >
                  {{ job.duplicate_of }}
                </RouterLink>
                <span v-else>—</span>
              </dd>
            </dl>
          </div>
        </section>

        <section class="card">
          <header class="card-header">
            <h2 class="card-title">Tracking</h2>
          </header>
          <div class="card-body">
            <dl class="deflist">
              <dt>Short ID</dt>
              <dd class="mono">{{ dash(job.short_id) }}</dd>

              <dt>Fingerprint</dt>
              <dd class="mono fingerprint">{{ dash(job.fingerprint) }}</dd>

              <dt>First seen</dt>
              <dd>
                {{ formatTimestamp(job.first_seen) }}
                <span v-if="job.first_seen" class="subtle">
                  ({{ formatRelative(job.first_seen) }})
                </span>
              </dd>

              <dt>Last seen</dt>
              <dd>
                {{ formatTimestamp(job.last_seen) }}
                <span v-if="job.last_seen" class="subtle">
                  ({{ formatRelative(job.last_seen) }})
                </span>
              </dd>

              <dt>URL</dt>
              <dd>
                <a v-if="job.url" :href="job.url" target="_blank" rel="noopener noreferrer" class="url">
                  {{ job.url }}
                </a>
                <span v-else>—</span>
              </dd>
            </dl>
          </div>
        </section>

        <section class="card card-wide">
          <header class="card-header">
            <h2 class="card-title">Snippet</h2>
          </header>
          <div class="card-body">
            <p v-if="job.snippet" class="prewrap snippet">{{ job.snippet }}</p>
            <p v-else class="muted">—</p>
          </div>
        </section>

        <section class="card card-wide">
          <header class="card-header">
            <h2 class="card-title">Matched locations</h2>
          </header>
          <div class="card-body">
            <ul v-if="hasMatches" class="tag-list">
              <li v-for="match in job.matches" :key="match" class="tag">{{ match }}</li>
            </ul>
            <p v-else class="muted">—</p>
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.breadcrumb {
  margin-bottom: var(--space-4);
  font-size: var(--text-sm);
}

.detail-badges {
  margin-top: var(--space-3);
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: var(--space-4);
  align-items: start;
}

.card-wide {
  grid-column: 1 / -1;
}

.fingerprint {
  overflow-wrap: anywhere;
}

.url {
  overflow-wrap: anywhere;
}

.snippet {
  color: var(--color-text);
  line-height: var(--leading-relaxed);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.tag {
  padding: 0.2rem 0.6rem;
  border-radius: var(--radius-pill);
  background: var(--color-accent-soft);
  border: 1px solid var(--color-accent-border);
  color: var(--color-accent);
  font-size: var(--text-xs);
  font-weight: var(--weight-medium);
}
</style>
