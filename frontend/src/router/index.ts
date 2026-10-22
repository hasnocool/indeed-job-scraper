import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import ApplicationsView from '../views/ApplicationsView.vue'
import JobDetailView from '../views/JobDetailView.vue'
import JobsView from '../views/JobsView.vue'
import SessionView from '../views/SessionView.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'jobs',
    component: JobsView,
    meta: { title: 'Jobs' },
  },
  {
    path: '/jobs/:shortId',
    name: 'job-detail',
    component: JobDetailView,
    props: true,
    meta: { title: 'Job detail' },
  },
  {
    path: '/session',
    name: 'session',
    component: SessionView,
    meta: { title: 'Session' },
  },
  {
    path: '/applications',
    name: 'applications',
    component: ApplicationsView,
    meta: { title: 'Applications' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    redirect: { name: 'jobs' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 }
  },
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? ''
  document.title = title ? `${title} · Indeed Job Scraper` : 'Indeed Job Scraper'
})

export default router
