<script setup lang="ts">
import {
  Bot, Search, BrainCircuit, FileText, Building2, Terminal,
  Lightbulb, Zap, AlertTriangle, ChevronRight, Star, Users,
  BarChart3, MessageSquare, Shield, Layers, BookOpen, Sparkles
} from 'lucide-vue-next'

const tips = [
  { icon: MessageSquare, text: "Parlez naturellement, comme à un collègue expert. L'agent comprend le langage courant et professionnel." },
  { icon: Layers, text: "Enchaînez les questions dans la même conversation — l'agent conserve le contexte de la session." },
  { icon: Sparkles, text: "Plus votre question est précise (compétence, niveau, localisation, période), plus la réponse est pertinente." },
  { icon: Shield, text: "Vos données restent dans l'infrastructure Zenika. Aucun contenu n'est envoyé à des tiers non-autorisés." },
]

const sections = [
  {
    id: 'experts',
    title: "Recherche d'Experts & Profils",
    icon: Search,
    color: "#E31937",
    description: "Interrogez la base RH complète de Zenika pour identifier les bons profils en quelques secondes.",
    examples: [
      { label: "Recherche par compétence", prompt: "Trouve-moi un développeur Senior Vue.js disponible à Lyon." },
      { label: "Multi-critères", prompt: "Qui maîtrise Kubernetes et Terraform avec plus de 5 ans d'expérience ?" },
      { label: "Par agence", prompt: "Combien y a-t-il d'experts Data Science sur l'agence de Paris ?" },
      { label: "Disponibilité", prompt: "Quels consultants sont disponibles en mai pour une mission Fullstack ?" },
      { label: "Séniorité", prompt: "Donne-moi la liste des consultants Senior et Expert en Cloud GCP." },
      { label: "Comparaison", prompt: "Compare les profils de Jean Dupont et Marie Martin pour une mission DevOps." },
    ],
    tips: ["Précisez la localisation pour affiner. Ex : « à Nantes », « région PACA ».", "Le niveau de séniorité (Junior/Confirmé/Senior/Expert) affine considérablement les résultats."]
  },
  {
    id: 'cv',
    title: "Génération de Contenus & CV",
    icon: FileText,
    color: "#3B82F6",
    description: "Générez des synthèses de profil, extraits de CV et propositions commerciales adaptées à chaque opportunité.",
    examples: [
      { label: "Synthèse de profil", prompt: "Génère une synthèse de profil pour Sébastien Lavayssière." },
      { label: "Profil orienté mission", prompt: "Rédige un profil consultant orienté architecture Cloud pour une proposition commerciale." },
      { label: "Extraction de compétences", prompt: "Extrais et liste les 5 compétences clés de ce consultant." },
      { label: "Proposition commerciale", prompt: "Rédige une proposition commerciale pour une mission d'architecture microservices chez un client bancaire." },
      { label: "Résumé de parcours", prompt: "Fais un résumé du parcours professionnel de ce consultant en 3 phrases." },
      { label: "Matching mission", prompt: "Ce consultant correspond-il à une mission de lead technique sur un projet GCP ?" },
    ],
    tips: ["Précisez le contexte client (secteur, durée, localisation) pour un contenu plus adapté.", "Vous pouvez demander plusieurs formats : synthèse courte, fiche détaillée, bullet points."]
  },
  {
    id: 'analytics',
    title: "Analyse & Métriques Zenika",
    icon: BarChart3,
    color: "#10B981",
    description: "Explorez les données RH agrégées, les tendances de compétences et les indicateurs par practice ou agence.",
    examples: [
      { label: "Cartographie des compétences", prompt: "Quelles sont les compétences les plus rares chez Zenika ?" },
      { label: "Diagnostic practice", prompt: "Affiche un diagnostic des compétences de la practice Cloud." },
      { label: "Répartition agences", prompt: "Quelle est la répartition des consultants par agence ?" },
      { label: "Tendances marché", prompt: "Quelles sont les tendances du marché Data en France selon France Travail ?" },
      { label: "Couverture sectorielle", prompt: "Sur quels secteurs (banque, industrie, retail) sommes-nous les plus représentés ?" },
      { label: "Évolution des profils", prompt: "Comment a évolué le nombre de consultants DevOps ces 12 derniers mois ?" },
    ],
    tips: ["Les analyses agrégées portent sur l'ensemble de la base consultant Zenika.", "Les données marché proviennent de France Travail et sont actualisées périodiquement."]
  },
  {
    id: 'missions',
    title: "Gestion des Missions",
    icon: Building2,
    color: "#F59E0B",
    description: "Retrouvez, analysez et comparez les missions passées ou en cours pour alimenter vos propositions.",
    examples: [
      { label: "Recherche de missions", prompt: "Quelles missions avons-nous réalisées dans le secteur bancaire ?" },
      { label: "Références client", prompt: "As-tu des références de missions Cloud chez des grands groupes industriels ?" },
      { label: "Analyse d'une mission", prompt: "Fais-moi un résumé de la mission Airbus démarrée en 2024." },
      { label: "Matching consultant-mission", prompt: "Quels consultants ont déjà réalisé des missions similaires à ce besoin client ?" },
      { label: "Durée et taux", prompt: "Quelle est la durée moyenne de nos missions Data chez des clients publics ?" },
      { label: "Retour d'expérience", prompt: "Quelles leçons avons-nous tirées de nos missions de transformation agile ?" },
    ],
    tips: ["Les documents de mission sont analysés par RAG — l'agent peut en extraire du contenu précis.", "Vous pouvez uploader un document d'appel d'offre et demander un matching avec nos références."]
  },
  {
    id: 'rag',
    title: "Intelligence Sémantique & RAG",
    icon: BrainCircuit,
    color: "#8B5CF6",
    description: "Exploitez la recherche vectorielle pour des requêtes sémantiques approfondies sur CVs et documents.",
    examples: [
      { label: "Matching sémantique", prompt: "Explique pourquoi ce consultant correspond à ma recherche Kubernetes." },
      { label: "Résumé de CV", prompt: "Fais-moi un résumé des missions marquantes de ce consultant." },
      { label: "Points forts", prompt: "Quels sont les points forts extraits du CV de cette personne ?" },
      { label: "Recherche conceptuelle", prompt: "Trouve un consultant qui a travaillé sur des problématiques de résilience distribuée." },
      { label: "Formation académique", prompt: "Quels consultants sont issus d'une grande école d'ingénieurs ?" },
      { label: "Expertise implicite", prompt: "Qui dans l'équipe a une expérience en sécurité applicative, même si ce n'est pas sa compétence principale ?" },
    ],
    tips: ["La recherche sémantique comprend les synonymes et concepts proches — pas besoin du mot exact.", "Les embeddings sont générés sur le contenu distillé des CVs : compétences, missions, formations."]
  },
  {
    id: 'ops',
    title: "Opérations & Monitoring",
    icon: Terminal,
    color: "#EC4899",
    description: "Interrogez l'état de l'infrastructure, les API disponibles et les métriques FinOps de la plateforme.",
    examples: [
      { label: "Santé des services", prompt: "Vérifie l'état de santé du Load Balancer et des API en ligne." },
      { label: "Coût IA", prompt: "Quel est le coût IA de la semaine dernière ventilé par modèle ?" },
      { label: "Documentation API", prompt: "As-tu accès à la documentation de l'API Compétences ?" },
      { label: "Logs d'erreurs", prompt: "Y a-t-il des erreurs récentes dans les logs de production ?" },
      { label: "Utilisation des modèles", prompt: "Quel modèle Gemini est le plus utilisé sur la plateforme ?" },
      { label: "Info agence", prompt: "Peux-tu m'en dire plus sur l'agence de Brest ?" },
    ],
    tips: ["Les infos d'infrastructure viennent du monitoring GCP Cloud Run en temps réel.", "Les métriques FinOps sont agrégées dans BigQuery — l'agent peut les filtrer par service ou par date."]
  },
]

const limits = [
  { icon: AlertTriangle, color: "#F59E0B", title: "Données en temps réel", text: "L'agent ne connaît pas les événements très récents (< 24h) si les imports n'ont pas encore été synchronisés." },
  { icon: AlertTriangle, color: "#E31937", title: "Documents externes", text: "L'agent ne peut pas accéder à des URLs ou fichiers extérieurs à la plateforme Zenika sans les avoir uploadés au préalable." },
  { icon: AlertTriangle, color: "#8B5CF6", title: "Calculs complexes", text: "Pour des calculs financiers ou statistiques très précis, préférez un export des données brutes depuis les APIs." },
  { icon: AlertTriangle, color: "#3B82F6", title: "Modifications directes", text: "L'agent peut recommander des actions mais n'exécute pas lui-même de modifications en base de données (sauf outils dédiés)." },
]

const advanced = [
  { icon: Star, title: "Chaînage de questions", text: "Demandez « et parmi eux, lesquels ont une certification AWS ? » — l'agent affine sa réponse précédente." },
  { icon: Star, title: "Format de sortie", text: "Spécifiez le format : « sous forme de tableau », « en bullet points », « en 3 phrases max »." },
  { icon: Star, title: "Contexte explicite", text: "Donnez le contexte client : « pour une mission de 6 mois à Paris dans le secteur bancaire »." },
  { icon: Star, title: "Reformulation", text: "Si la réponse n'est pas satisfaisante, reformulez ou précisez : « non, je veux uniquement des profils Fullstack »." },
  { icon: Star, title: "Demandes multi-agents", text: "L'agent routeur délègue automatiquement aux sous-agents RH, Ops ou Missions selon votre besoin." },
  { icon: Star, title: "Historique de session", text: "L'historique de la conversation est conservé — vous pouvez vous y référer : « reprends l'exemple du dessus »." },
]
</script>

<template>
  <div class="help-container">

    <!-- Header -->
    <div class="help-header">
      <div class="icon-wrapper">
        <Lightbulb size="36" class="text-zenika-red" />
      </div>
      <h1 class="help-title">Comment interagir avec l'<span class="highlight">Agent Intelligent</span> ?</h1>
      <p class="help-subtitle">
        Guide exhaustif des capacités du Console Agent Zenika — cas d'usage, formulations recommandées,
        astuces avancées et limites connues.
      </p>
    </div>

    <!-- Quick Tips Banner -->
    <div class="tips-banner">
      <div v-for="(tip, i) in tips" :key="i" class="tip-item">
        <component :is="tip.icon" size="18" class="tip-icon" />
        <span>{{ tip.text }}</span>
      </div>
    </div>

    <!-- Main Sections -->
    <div v-for="section in sections" :key="section.id" class="section-block" :style="{ '--theme-color': section.color }">
      <div class="section-header">
        <div class="section-icon" :style="{ color: section.color, background: section.color + '18' }">
          <component :is="section.icon" size="22" />
        </div>
        <div>
          <h2 class="section-title">{{ section.title }}</h2>
          <p class="section-desc">{{ section.description }}</p>
        </div>
      </div>

      <div class="examples-grid">
        <div v-for="(ex, idx) in section.examples" :key="idx" class="example-card">
          <div class="example-label">
            <ChevronRight size="13" />
            {{ ex.label }}
          </div>
          <div class="example-prompt">
            <Bot size="14" class="bot-icon" />
            <span>"{{ ex.prompt }}"</span>
          </div>
        </div>
      </div>

      <div class="section-tips">
        <div v-for="(t, i) in section.tips" :key="i" class="inline-tip">
          <Lightbulb size="13" class="inline-tip-icon" />
          {{ t }}
        </div>
      </div>
    </div>

    <!-- Advanced Tips -->
    <div class="block-card advanced-block">
      <div class="block-card-header">
        <div class="block-card-icon" style="color:#E31937; background:rgba(227,25,55,0.1)">
          <Sparkles size="20" />
        </div>
        <div>
          <h2 class="block-card-title">Astuces Avancées</h2>
          <p class="block-card-desc">Techniques pour tirer le maximum de l'agent en conversation.</p>
        </div>
      </div>
      <div class="advanced-grid">
        <div v-for="(adv, i) in advanced" :key="i" class="advanced-item">
          <Star size="14" class="advanced-star" />
          <div>
            <strong>{{ adv.title }}</strong>
            <p>{{ adv.text }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Limits -->
    <div class="block-card limits-block">
      <div class="block-card-header">
        <div class="block-card-icon" style="color:#F59E0B; background:rgba(245,158,11,0.1)">
          <AlertTriangle size="20" />
        </div>
        <div>
          <h2 class="block-card-title">Limites Connues</h2>
          <p class="block-card-desc">Situations où l'agent peut être limité — à connaître pour formuler autrement.</p>
        </div>
      </div>
      <div class="limits-grid">
        <div v-for="(lim, i) in limits" :key="i" class="limit-item">
          <component :is="lim.icon" size="16" :style="{ color: lim.color, flexShrink: 0 }" />
          <div>
            <strong>{{ lim.title }}</strong>
            <p>{{ lim.text }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Architecture note -->
    <div class="arch-note">
      <BookOpen size="16" />
      <span>
        Le Console Agent Zenika est composé d'un <strong>Router</strong> (Gemini) qui délègue dynamiquement à
        des sous-agents spécialisés : <strong>Agent RH</strong> (CVs, compétences, consultants),
        <strong>Agent Ops</strong> (items, infra, FinOps) et <strong>Agent Missions</strong> (documents client).
        Les réponses sont enrichies via RAG (pgvector) et des outils MCP en temps réel.
      </span>
    </div>

  </div>
</template>

<style scoped>
.help-container {
  max-width: 1100px;
  margin: 0 auto;
  padding: 2rem 0 4rem;
  animation: fadeIn 0.5s ease;
}

/* ── Header ── */
.help-header {
  text-align: center;
  margin-bottom: 2.5rem;
}

.icon-wrapper {
  background: rgba(227, 25, 55, 0.08);
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 1.2rem;
  box-shadow: 0 8px 32px rgba(227, 25, 55, 0.1);
  border: 1px solid rgba(227, 25, 55, 0.15);
}

.text-zenika-red { color: var(--zenika-red); }

.help-title {
  font-size: 2.4rem;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 0.8rem;
  letter-spacing: -0.5px;
}

.highlight {
  color: var(--zenika-red);
  position: relative;
}
.highlight::after {
  content: '';
  position: absolute;
  bottom: 0.1rem;
  left: 0;
  width: 100%;
  height: 8px;
  background: rgba(227, 25, 55, 0.12);
  border-radius: 4px;
  z-index: -1;
}

.help-subtitle {
  font-size: 1.05rem;
  color: var(--text-secondary);
  max-width: 680px;
  margin: 0 auto;
  line-height: 1.65;
}

/* ── Tips Banner ── */
.tips-banner {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
  margin-bottom: 2.5rem;
  background: rgba(227, 25, 55, 0.04);
  border: 1px solid rgba(227, 25, 55, 0.12);
  border-radius: 18px;
  padding: 1.4rem 1.6rem;
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.tip-icon {
  color: var(--zenika-red);
  flex-shrink: 0;
  margin-top: 1px;
}

/* ── Section Blocks ── */
.section-block {
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 22px;
  padding: 2rem 2.2rem;
  margin-bottom: 1.6rem;
  box-shadow: 0 6px 30px rgba(0, 0, 0, 0.04);
  border-top: 3px solid var(--theme-color);
  transition: box-shadow 0.3s ease;
}

.section-block:hover {
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.07);
}

.section-header {
  display: flex;
  align-items: flex-start;
  gap: 1.1rem;
  margin-bottom: 1.4rem;
}

.section-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.section-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 0.25rem;
}

.section-desc {
  font-size: 0.88rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

/* ── Examples Grid ── */
.examples-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.example-card {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  padding: 0.9rem 1rem;
  transition: all 0.2s ease;
}

.example-card:hover {
  background: #fff;
  border-color: var(--theme-color);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06);
  transform: translateY(-2px);
}

.example-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--theme-color);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 0.45rem;
}

.example-prompt {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.88rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.bot-icon {
  color: var(--theme-color);
  flex-shrink: 0;
  margin-top: 2px;
}

/* ── Inline Tips inside sections ── */
.section-tips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-top: 0.5rem;
}

.inline-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 0.8rem;
  color: var(--text-secondary);
  background: rgba(0, 0, 0, 0.04);
  border-radius: 8px;
  padding: 0.4rem 0.7rem;
  line-height: 1.45;
}

.inline-tip-icon {
  color: #F59E0B;
  flex-shrink: 0;
  margin-top: 2px;
}

/* ── Generic block card (Advanced + Limits) ── */
.block-card {
  background: rgba(255, 255, 255, 0.55);
  backdrop-filter: blur(18px);
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 22px;
  padding: 2rem 2.2rem;
  margin-bottom: 1.6rem;
  box-shadow: 0 6px 30px rgba(0, 0, 0, 0.04);
}

.block-card-header {
  display: flex;
  align-items: flex-start;
  gap: 1.1rem;
  margin-bottom: 1.4rem;
}

.block-card-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.block-card-title {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 0.25rem;
}

.block-card-desc {
  font-size: 0.88rem;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

/* ── Advanced Grid ── */
.advanced-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 0.75rem;
}

.advanced-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: rgba(227, 25, 55, 0.04);
  border: 1px solid rgba(227, 25, 55, 0.1);
  border-radius: 12px;
  padding: 0.85rem 1rem;
  font-size: 0.87rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.advanced-item strong {
  display: block;
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.2rem;
}

.advanced-item p {
  margin: 0;
}

.advanced-star {
  color: #E31937;
  flex-shrink: 0;
  margin-top: 3px;
}

/* ── Limits Grid ── */
.limits-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 0.75rem;
}

.limit-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: rgba(245, 158, 11, 0.04);
  border: 1px solid rgba(245, 158, 11, 0.15);
  border-radius: 12px;
  padding: 0.85rem 1rem;
  font-size: 0.87rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.limit-item strong {
  display: block;
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 0.2rem;
}

.limit-item p {
  margin: 0;
}

/* ── Architecture note ── */
.arch-note {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  background: rgba(139, 92, 246, 0.06);
  border: 1px solid rgba(139, 92, 246, 0.18);
  border-radius: 14px;
  padding: 1rem 1.4rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
  line-height: 1.6;
}

.arch-note svg {
  color: #8B5CF6;
  flex-shrink: 0;
  margin-top: 3px;
}

.arch-note strong {
  color: var(--text-primary);
}

/* ── Animations ── */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .help-title { font-size: 1.8rem; }
  .help-container { padding: 1rem 0 2rem; }
  .section-block, .block-card { padding: 1.3rem 1.2rem; }
  .examples-grid { grid-template-columns: 1fr; }
  .advanced-grid, .limits-grid { grid-template-columns: 1fr; }
  .tips-banner { grid-template-columns: 1fr; }
}
</style>
