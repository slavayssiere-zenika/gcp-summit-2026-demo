<script setup lang="ts">
import { Bot, Search, BrainCircuit, FileText, Building2, Terminal, Lightbulb } from 'lucide-vue-next'

const categories = [
  {
    title: "Recherche d'Experts & Profils",
    icon: Search,
    color: "#E31937",
    examples: [
      "Trouve-moi un développeur Senior Vue.js disponible à Lyon.",
      "Qui a de l'expérience avec Kubernetes et Terraform ?",
      "Combien y a-t-il d'experts data sur l'agence de Paris ?"
    ]
  },
  {
    title: "Génération de Contenus et CV",
    icon: FileText,
    color: "#3B82F6",
    examples: [
      "Génère une synthèse de profil pour Sébastien Lavayssière.",
      "Rédige une proposition commerciale pour une mission d'architecture Cloud.",
      "Peux-tu extraire et lister les 3 compétences clés de ce document ?"
    ]
  },
  {
    title: "Analyse & Métriques Zenika",
    icon: BrainCircuit,
    color: "#10B981",
    examples: [
      "Quelles sont les compétences les plus rares chez Zenika ?",
      "Affiche un diagnostic des compétences de la practice Cloud.",
      "Quelles sont les tendances du marché Data à l'aide de France Travail ?"
    ]
  },
  {
    title: "Agences & Opérations Techniques",
    icon: Terminal,
    color: "#8B5CF6",
    examples: [
      "Peux-tu m'en dire plus sur l'agence de Brest ?",
      "Vérifie l'état de santé du Load Balancer et des API en ligne.",
      "As-tu accès à la documentation de l'API Compétences ?"
    ]
  },
  {
    title: "Intelligence Sémantique & RAG",
    icon: BrainCircuit,
    color: "#F59E0B",
    examples: [
      "Explique pourquoi ce candidat correspond à ma recherche Kubernetes.",
      "Fais-moi un résumé des missions marquantes de ce consultant.",
      "Quels sont les points forts extraits du CV de cette personne ?"
    ]
  }
]
</script>

<template>
  <div class="help-container">
    <div class="help-header">
      <div class="icon-wrapper">
        <Lightbulb size="36" class="text-zenika-red" />
      </div>
      <h1 class="help-title">Comment interagir avec l'<span class="highlight">Agent Intelligent</span> ?</h1>
      <p class="help-subtitle">Découvrez le potentiel du Console Agent Zenika à travers des cas d'usage concrets et explorez les questions types que vous pouvez formuler.</p>
    </div>

    <div class="categories-grid">
      <div v-for="(category, index) in categories" :key="index" class="category-card" :style="{ '--theme-color': category.color }">
        <div class="card-header">
          <div class="card-icon" :style="{ color: category.color, background: category.color + '15' }">
            <component :is="category.icon" size="24" />
          </div>
          <h2>{{ category.title }}</h2>
        </div>
        <div class="card-body">
          <ul class="example-list">
            <li v-for="(example, idx) in category.examples" :key="idx" class="example-item">
              <Bot size="16" class="example-icon" />
              <span>"{{ example }}"</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.help-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 0;
  animation: fadeIn 0.6s cubic-bezier(0.16, 1.08, 0.38, 0.98);
}

.help-header {
  text-align: center;
  margin-bottom: 4rem;
}

.icon-wrapper {
  background: rgba(227, 25, 55, 0.08);
  width: 90px;
  height: 90px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1.5rem;
  box-shadow: 0 8px 32px rgba(227, 25, 55, 0.12);
  border: 1px solid rgba(227, 25, 55, 0.15);
}

.text-zenika-red {
  color: var(--zenika-red);
}

.help-title {
  font-size: 2.8rem;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 1rem;
  letter-spacing: -1px;
}

.highlight {
  color: var(--zenika-red);
  position: relative;
  display: inline-block;
}

.highlight::after {
  content: '';
  position: absolute;
  bottom: 0.2rem;
  left: 0;
  width: 100%;
  height: 10px;
  background: rgba(227, 25, 55, 0.15);
  border-radius: 6px;
  z-index: -1;
}

.help-subtitle {
  font-size: 1.15rem;
  color: var(--text-secondary);
  max-width: 700px;
  margin: 0 auto;
  line-height: 1.6;
}

.categories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 2.5rem;
}

.category-card {
  background: rgba(255, 255, 255, 0.6);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.8);
  border-radius: 28px;
  padding: 2.5rem;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.04);
  transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.category-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 5px;
  background: var(--theme-color);
  opacity: 0.9;
}

.category-card:hover {
  transform: translateY(-8px);
  box-shadow: 0 24px 50px rgba(0, 0, 0, 0.08);
  background: rgba(255, 255, 255, 0.95);
  border-color: rgba(0, 0, 0, 0.05);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 1.2rem;
  margin-bottom: 2rem;
}

.card-icon {
  width: 54px;
  height: 54px;
  border-radius: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.5);
}

.card-header h2 {
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.example-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  flex: 1;
}

.example-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  background: rgba(255, 255, 255, 0.5);
  padding: 1.2rem;
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  font-size: 0.95rem;
  color: var(--text-secondary);
  line-height: 1.5;
  transition: all 0.25s ease;
}

.example-item:hover {
  background: #ffffff;
  border-color: var(--theme-color);
  color: var(--text-primary);
  transform: translateX(6px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.06);
}

.example-icon {
  flex-shrink: 0;
  color: var(--theme-color);
  margin-top: 2px;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(30px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* Responsiveness */
@media (max-width: 768px) {
  .help-title {
    font-size: 2.2rem;
  }
  
  .categories-grid {
    grid-template-columns: 1fr;
  }
  
  .help-container {
    padding: 1rem;
  }
}
</style>
