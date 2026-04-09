import { createRouter, createWebHistory, type RouteLocationNormalized, type NavigationGuardNext } from 'vue-router'
import Home from '../views/Home.vue'
import { authService } from '../services/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/Login.vue'),
      meta: { public: true }
    },
    {
      path: '/',
      name: 'home',
      component: Home
    },
    {
      path: '/docs/:service',
      name: 'docs',
      component: () => import('../views/Docs.vue'),
      props: true
    },
    {
      path: '/registry',
      name: 'registry',
      component: () => import('../views/Registry.vue')
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('../views/Profile.vue')
    },
    {
      path: '/user/:id',
      name: 'user-detail',
      component: () => import('../views/UserDetail.vue'),
      props: true
    },
    {
      path: '/competencies',
      name: 'competencies',
      component: () => import('../views/Competencies.vue')
    },
    {
      path: '/specs',
      name: 'specs',
      component: () => import('../views/Specs.vue')
    },
    {
      path: '/import-cv',
      name: 'import-cv',
      component: () => import('../views/ImportCV.vue')
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('../views/Admin.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/prompts',
      name: 'prompts-admin',
      component: () => import('../views/PromptsAdmin.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../views/AdminUsers.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/admin/deduplication',
      name: 'admin-deduplication',
      component: () => import('../views/AdminDeduplication.vue'),
      meta: { adminOnly: true }
    },
    {
      path: '/help',
      name: 'help',
      component: () => import('../views/Help.vue')
    }
  ]
})

// Navigation Guard
router.beforeEach(async (to: RouteLocationNormalized, _from: RouteLocationNormalized, next: NavigationGuardNext) => {
  // Check auth on every navigation if not already loaded
  if (authService.state.isLoading) {
    await authService.checkAuth()
  }

  if (to.meta.public) {
    next()
  } else if (!authService.state.isAuthenticated) {
    next({ name: 'login' })
  } else if (to.meta.adminOnly && authService.state.user?.role !== 'admin') {
    next({ name: 'home' })
  } else {
    next()
  }
})

// Handle dynamic import failures (e.g. after a deployment)
router.onError((error: Error, to: RouteLocationNormalized) => {
  if (
    error.message.includes('Failed to fetch dynamically imported module') ||
    error.message.includes('Importing a module script failed') ||
    error.name === 'ChunkLoadError'
  ) {
    window.location.href = to.fullPath
  }
})

export default router
