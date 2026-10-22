<script setup lang="ts">
import type { RunInfo } from '../api/client'
import { dash, formatCount, formatTimestamp } from '../api/format'

/** Scrape run history table (contract section 4.6). */
defineProps<{ runs: RunInfo[] }>()
</script>

<template>
  <div class="table-wrap">
    <table class="table">
      <caption class="visually-hidden">Scrape run history, newest first.</caption>
      <thead>
        <tr>
          <th scope="col">Scraped at</th>
          <th scope="col">File</th>
          <th scope="col">Query</th>
          <th scope="col">Locations</th>
          <th scope="col" class="num">Pages</th>
          <th scope="col" class="num">Jobs</th>
          <th scope="col">Stopped reason</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="run in runs" :key="run.file">
          <td class="cell-strong nowrap">{{ formatTimestamp(run.scraped_at) }}</td>
          <td class="cell-mono">{{ dash(run.file) }}</td>
          <td class="cell-muted">{{ dash(run.query) }}</td>
          <td class="cell-muted">
            <span v-if="run.locations.length > 0">{{ run.locations.join(', ') }}</span>
            <span v-else>—</span>
          </td>
          <td class="num cell-muted">{{ formatCount(run.pages_fetched) }}</td>
          <td class="num cell-muted">{{ formatCount(run.total_jobs) }}</td>
          <td class="cell-muted">{{ dash(run.stopped_reason) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
