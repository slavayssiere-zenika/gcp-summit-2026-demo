import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { createHead } from '@vueuse/head'
import { i18n, currentLocale } from './i18n'
import './style.css'

const app = createApp(App)
const head = createHead()
const pinia = createPinia()

// Initialise l'attribut lang sur <html> dès le démarrage
document.documentElement.lang = currentLocale()

app.use(pinia)
app.use(router)
app.use(head)
app.use(i18n)
app.mount('#app')
