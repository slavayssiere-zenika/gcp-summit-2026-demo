<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { LogIn, User, Lock, AlertCircle, Mail } from 'lucide-vue-next'
import { authService } from '../services/auth'

const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const isLoading = ref(false)

onMounted(async () => {
    // If already logged in, redirect to home
    await authService.checkAuth()
    if (authService.state.isAuthenticated) {
        router.push('/')
    }
})

const handleLogin = async () => {
  if (!email.value || !password.value) {
    error.value = 'Veuillez remplir tous les champs'
    return
  }

  isLoading.value = true
  error.value = ''

  try {
    await authService.login(email.value, password.value)
    router.push('/')
  } catch (err: any) {
    error.value = err || 'Identifiants invalides'
  } finally {
    isLoading.value = false
  }
}

const loginWithGoogle = () => {
  window.location.href = '/auth/google/login'
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <div class="zenika-logo">ZENIKA</div>
        <h1>Console Agent</h1>
        <p>Identifiez-vous pour accéder à l'interface</p>
      </div>

      <div class="login-form-container">
        <!-- Google Login First -->
        <button type="button" @click="loginWithGoogle" class="google-button primary-action" :disabled="isLoading">
          <svg style="width: 20px; height: 20px;" viewBox="0 0 24 24">
             <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
             <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
             <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
             <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Connexion avec Google (Recommandé)
        </button>

        <div class="divider">
          <span>OU accès expert (identifiants)</span>
        </div>

        <form @submit.prevent="handleLogin" class="login-form">
          <div v-if="error" class="error-banner">
            <AlertCircle size="18" />
            <span>{{ error }}</span>
          </div>

          <div class="input-group">
            <label><Mail size="16" /> Adresse Email</label>
            <input 
              v-model="email" 
              type="email" 
              placeholder="Ex: admin@zenika.com"
              :disabled="isLoading"
            >
          </div>

          <div class="input-group">
            <label><Lock size="16" /> Mot de passe</label>
            <input 
              v-model="password" 
              type="password" 
              placeholder="••••••••"
              :disabled="isLoading"
            >
          </div>

          <button type="submit" :disabled="isLoading" class="login-button secondary-action">
            <span v-if="!isLoading">Connexion Expert</span>
            <span v-else class="loader"></span>
            <LogIn v-if="!isLoading" size="18" />
          </button>
        </form>
      </div>

      <div class="login-footer">
        © 2024 Zenika - Accès réservé aux collaborateurs
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
  background: var(--bg-gradient);
}

.login-card {
  background: white;
  padding: 3rem;
  border-radius: 24px;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
  width: 100%;
  max-width: 440px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  animation: slideUp 0.6s cubic-bezier(0.23, 1, 0.32, 1);
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.login-header {
  text-align: center;
  margin-bottom: 2.5rem;
}

.zenika-logo {
  font-weight: 900;
  font-size: 2rem;
  color: var(--zenika-red);
  letter-spacing: -1px;
  margin-bottom: 0.5rem;
}

h1 {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1a1a1a;
  margin-bottom: 0.5rem;
}

p {
  color: #666;
  font-size: 0.9rem;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.error-banner {
  background: #fff5f5;
  color: #e31937;
  padding: 1rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
  border: 1px solid #ffe3e3;
  animation: shake 0.4s linear;
}

@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.input-group label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: #444;
}

.input-group input {
  padding: 0.8rem 1rem;
  border-radius: 12px;
  border: 1.5px solid #eee;
  font-size: 1rem;
  transition: all 0.2s;
  background: #fcfcfc;
}

.input-group input:focus {
  border-color: var(--zenika-red);
  background: white;
  outline: none;
  box-shadow: 0 0 0 4px rgba(227, 25, 55, 0.1);
}

.login-button {
  background: var(--zenika-red);
  color: white;
  border: none;
  padding: 1rem;
  border-radius: 12px;
  font-weight: 700;
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.2);
}

.login-button:hover:not(:disabled) {
  transform: translateY(-2px);
  background: #c81530;
  box-shadow: 0 6px 15px rgba(227, 25, 55, 0.3);
}

.login-button:active:not(:disabled) {
  transform: translateY(0);
}

.login-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.login-footer {
  margin-top: 2.5rem;
  text-align: center;
  font-size: 0.75rem;
  color: #999;
}

.loader {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.divider {
  display: flex;
  align-items: center;
  text-align: center;
  color: #999;
  font-size: 0.8rem;
  font-weight: 600;
}

.divider::before, .divider::after {
  content: '';
  flex: 1;
  border-bottom: 1px solid #eee;
}

.divider span {
  padding: 0 10px;
}

.login-form-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.google-button {
  background: white;
  color: #444;
  border: 1px solid #ddd;
  padding: 1rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.google-button.primary-action {
  border: 2px solid #e2e8f0;
  box-shadow: 0 8px 16px rgba(0,0,0,0.06);
  padding: 1.1rem;
  font-weight: 700;
  color: #0f172a;
}

.google-button:hover:not(:disabled) {
  background: #f8f8f8;
  border-color: #ccc;
  transform: translateY(-2px);
}

.google-button:active:not(:disabled) {
  transform: translateY(0);
}

.google-button:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.login-button.secondary-action {
  background: #f1f5f9;
  color: #475569;
  box-shadow: none;
  font-weight: 600;
}

.login-button.secondary-action:hover:not(:disabled) {
  background: #e2e8f0;
  color: #0f172a;
}
</style>
