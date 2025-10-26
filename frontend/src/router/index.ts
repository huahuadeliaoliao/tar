import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/auth',
      name: 'auth',
      component: () => import('@/views/AuthView.vue'),
      meta: { requiresGuest: true },
    },
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/chat/:id',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

// Route guard.
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()
  const sessionsStore = useSessionsStore()

  // On first load, restore the user from persisted tokens.
  if (!authStore.user && !authStore.loading) {
    await authStore.initialize()
  }

  // Enforce authentication when required.
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return next({ name: 'auth' })
  }

  // Prevent authenticated users from visiting the auth view.
  if (to.meta.requiresGuest && authStore.isAuthenticated) {
    return next({ name: 'home' })
  }

  // Preload sessions and models when entering chat routes.
  if (authStore.isAuthenticated && (to.name === 'home' || to.name === 'chat')) {
    if (sessionsStore.sessions.length === 0) {
      await sessionsStore.loadSessions()
    }
    if (sessionsStore.models.length === 0) {
      await sessionsStore.loadModels()
    }
  }

  next()
})

export default router
