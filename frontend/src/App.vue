<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="app-header-inner">
        <RouterLink class="brand" :to="{ name: 'jobs' }">
          <span class="brand-mark" aria-hidden="true">IS</span>
          <span class="brand-text">
            <span class="brand-name">Indeed Job Scraper</span>
            <span class="brand-sub">read-only console</span>
          </span>
        </RouterLink>

        <nav class="app-nav" aria-label="Main">
          <RouterLink class="nav-link" :to="{ name: 'jobs' }">Jobs</RouterLink>
          <RouterLink class="nav-link" :to="{ name: 'session' }">Session</RouterLink>
          <RouterLink class="nav-link" :to="{ name: 'applications' }">Applications</RouterLink>
        </nav>
      </div>
    </header>

    <main class="app-main">
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </main>

    <footer class="app-footer">
      <span>Data comes from the local scraper state directory. Nothing is written from here.</span>
    </footer>
  </div>
</template>

<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border);
}

.app-header-inner {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: var(--space-3) var(--space-5);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-5);
  flex-wrap: wrap;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  color: inherit;
  text-decoration: none;
}

.brand:hover {
  text-decoration: none;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: #fff;
  font-size: var(--text-xs);
  font-weight: var(--weight-bold);
  letter-spacing: 0.02em;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.brand-name {
  font-size: var(--text-base);
  font-weight: var(--weight-semibold);
  letter-spacing: -0.01em;
}

.brand-sub {
  font-size: var(--text-xs);
  color: var(--color-text-subtle);
}

.app-nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.nav-link {
  padding: 0.4rem 0.7rem;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  font-weight: var(--weight-medium);
  text-decoration: none;
  transition:
    background-color var(--transition-fast),
    color var(--transition-fast);
}

.nav-link:hover {
  background: var(--color-bg-hover);
  color: var(--color-text);
  text-decoration: none;
}

.nav-link.router-link-active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.app-main {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.app-footer {
  border-top: 1px solid var(--color-border-subtle);
  padding: var(--space-4) var(--space-5);
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-subtle);
}
</style>
