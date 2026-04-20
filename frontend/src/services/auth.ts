import { reactive, readonly } from 'vue'
import axios from 'axios'

// 1. JWT Interceptor: Automatically inject the stored token into Authorization headers
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    // Axios 1.x compatibility check
    if (config.headers && typeof config.headers.set === 'function') {
      config.headers.set('Authorization', `Bearer ${token}`)
    } else {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  // Enforce sending cookies cross-origin if strictly needed, though usually same origin
  config.withCredentials = true
  return config
})

// 2. Response Interceptor for 401 & Silent Refresh
let isRefreshing = false;
let failedQueue: any[] = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  failedQueue = [];
};

axios.interceptors.response.use((response) => {
  return response;
}, async (error) => {
  const originalRequest = error.config;

  // Prevent refreshing logic if 401 comes from auth routes or if it's the refresh call itself
  const authRoutes = ['/auth/login', '/auth/refresh', '/auth/me', '/auth/logout'];
  const isAuthRoute = originalRequest.url && authRoutes.some(route => originalRequest.url.includes(route));

  if (error.response?.status === 401 && !originalRequest._retry && !isAuthRoute) {
    originalRequest._retry = true;

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then(token => {
        if (originalRequest.headers && typeof originalRequest.headers.set === 'function') {
          originalRequest.headers.set('Authorization', 'Bearer ' + token);
        } else if (originalRequest.headers) {
          originalRequest.headers.Authorization = 'Bearer ' + token;
        }
        return axios(originalRequest);
      }).catch(err => {
        return Promise.reject(err);
      });
    }

    isRefreshing = true;

    try {
      const { data } = await axios.post('/auth/refresh', {}, { 
        withCredentials: true,
        headers: { '_isRefreshCall': 'true' } as any 
      });
      const newAccessToken = data.access_token;

      localStorage.setItem('access_token', newAccessToken);
      if (state) state.token = newAccessToken;

      if (axios.defaults.headers.common && typeof (axios.defaults.headers.common as any).set === 'function') {
        (axios.defaults.headers.common as any).set('Authorization', 'Bearer ' + newAccessToken);
      } else {
        axios.defaults.headers.common['Authorization'] = 'Bearer ' + newAccessToken;
      }
      if (originalRequest.headers && typeof originalRequest.headers.set === 'function') {
        originalRequest.headers.set('Authorization', 'Bearer ' + newAccessToken);
      } else if (originalRequest.headers) {
        originalRequest.headers.Authorization = 'Bearer ' + newAccessToken;
      }

      // Libérer le verrou AVANT de traiter la queue pour éviter un double-refresh
      isRefreshing = false;
      processQueue(null, newAccessToken);
      return axios(originalRequest);
    } catch (refreshError) {
      // Libérer le verrou AVANT de rejeter la queue
      isRefreshing = false;
      processQueue(refreshError, null);
      // Logout completely if refresh fails
      localStorage.removeItem('access_token');
      if (state) {
        state.token = null;
        state.user = null;
        state.isAuthenticated = false;
      }
      // Prevent infinite redirect loop if already on login page
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
      return Promise.reject(refreshError);
    }
  }

  return Promise.reject(error);
});


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
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

const state = reactive<AuthState>({
  user: null,
  token: null,
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
        state.token = response.data.access_token
        localStorage.setItem('access_token', response.data.access_token)
      } else {
        state.token = localStorage.getItem('access_token')
      }
      state.user = response.data
      state.isAuthenticated = true
    } catch (error) {
      state.user = null
      state.token = null
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
        state.token = response.data.access_token
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
      state.token = null
      state.user = null
      state.isAuthenticated = false
      window.location.href = '/login'
    }
  }
}
