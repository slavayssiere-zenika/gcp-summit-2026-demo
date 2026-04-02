import { reactive, readonly } from 'vue'
import axios from 'axios'

// 1. JWT Interceptor: Automatically inject the stored token into Authorization headers
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

interface User {
  id: number
  username: string
  email: string
  full_name: string
  is_active: boolean
  role?: string
  allowed_category_ids: number[]
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
}

const state = reactive<AuthState>({
  user: null,
  isAuthenticated: false,
  isLoading: true
})

const API_BASE = '/auth'

export const authService = {
  get state() {
    return readonly(state)
  },

  async checkAuth() {
    state.isLoading = true
    try {
      const response = await axios.get(`${API_BASE}/me`)
      // Strict validation: if the response is not a proper JSON object with an id (e.g. we hit a proxy or dummy container returning 200 HTML), reject it.
      if (!response.data || typeof response.data !== 'object' || !('id' in response.data)) {
        throw new Error("Invalid payload received from /auth/me")
      }
      if (response.data.access_token) {
        localStorage.setItem('access_token', response.data.access_token)
      }
      state.user = response.data
      state.isAuthenticated = true
    } catch (error) {
      state.user = null
      state.isAuthenticated = false
    } finally {
      state.isLoading = false
    }
  },

  async login(email: string, password: string) {
    try {
      const response = await axios.post(`${API_BASE}/login`, { email, password })
      // Capture the explicit access_token from the JSON payload
      if (response.data.access_token) {
        localStorage.setItem('access_token', response.data.access_token)
      }
      // The cookie is also set automatically by the browser since it's HttpOnly
      await this.checkAuth()
      return response.data
    } catch (error: any) {
      throw error.response?.data?.detail || 'Erreur de connexion'
    }
  },

  async logout() {
    try {
      await axios.post(`${API_BASE}/logout`)
    } finally {
      localStorage.removeItem('access_token')
      state.user = null
      state.isAuthenticated = false
      window.location.href = '/login'
    }
  }
}
