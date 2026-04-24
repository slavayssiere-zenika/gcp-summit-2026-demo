<template>
  <div class="debug-card">
    <!-- Card header -->
    <div class="debug-header">
      <div class="debug-header-icon">
        <Bug size="16" />
      </div>
      <div class="debug-header-text">
        <span class="debug-title">Prompt de débogage suggéré</span>
        <span class="debug-subtitle">Généré par l'agent OPS · À copier dans l'assistant</span>
      </div>
      <button class="copy-prompt-btn" @click="copyPrompt" :aria-label="'Copier le prompt de débogage'">
        <template v-if="copied">
          <CheckCircle2 size="14" />
          <span>Copié !</span>
        </template>
        <template v-else>
          <Copy size="14" />
          <span>Copier</span>
        </template>
      </button>
    </div>

    <!-- Context chips -->
    <div v-if="context.service || context.error" class="context-chips">
      <span v-if="context.service" class="chip chip-service">
        <Server size="11" />
        {{ context.service }}
      </span>
      <span v-if="context.error" class="chip chip-error">
        <AlertCircle size="11" />
        {{ context.error }}
      </span>
    </div>

    <!-- Rendered prompt body (markdown) -->
    <div class="debug-body" v-html="renderedContent" />

    <!-- Action row: use prompt -->
    <div class="debug-footer">
      <button class="use-prompt-btn" @click="$emit('use-prompt', promptText)" aria-label="Utiliser ce prompt">
        <MessageSquarePlus size="14" />
        Utiliser ce prompt
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Bug, Copy, CheckCircle2, Server, AlertCircle, MessageSquarePlus } from 'lucide-vue-next'
import markdownit from 'markdown-it'

const md = markdownit({ html: false, linkify: true, typographer: true })

const props = defineProps<{
  content: string  // raw markdown of the prompt
}>()

const emit = defineEmits<{
  (e: 'use-prompt', prompt: string): void
}>()

const copied = ref(false)

// Extract useful context from the markdown
const context = computed(() => {
  const serviceMatch = props.content.match(/`([a-z0-9-]+-api[a-z0-9-]*)`/)
  const errorMatch = props.content.match(/`((?:NameError|TypeError|ValueError|ImportError|AttributeError|KeyError)[^`]*)`/)
  return {
    service: serviceMatch?.[1] || null,
    error: errorMatch?.[1] || null
  }
})

// The raw text usable as a chat prompt
const promptText = computed(() => {
  // Strip blockquote markers for cleaner usage
  return props.content
    .replace(/^>\s?/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
})

const renderedContent = computed(() => md.render(props.content))

const copyPrompt = async () => {
  try {
    await navigator.clipboard.writeText(promptText.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch { /* ignore */ }
}
</script>

<style scoped>
/* ── Card container ─────────────────────────────────────────── */
.debug-card {
  margin-top: 1rem;
  border: 1.5px solid rgba(227, 25, 55, 0.2);
  border-radius: 14px;
  overflow: hidden;
  background: linear-gradient(135deg, #fff5f6 0%, #fff 100%);
  animation: fadeIn 0.25s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ── Header ─────────────────────────────────────────────────── */
.debug-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(227,25,55,0.06) 0%, rgba(227,25,55,0.02) 100%);
  border-bottom: 1px solid rgba(227, 25, 55, 0.12);
}

.debug-header-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(227, 25, 55, 0.1);
  color: #e31937;
  flex-shrink: 0;
}

.debug-header-text {
  flex: 1;
  min-width: 0;
}

.debug-title {
  display: block;
  font-size: 0.82rem;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.01em;
}

.debug-subtitle {
  display: block;
  font-size: 0.68rem;
  color: #94a3b8;
  margin-top: 1px;
}

.copy-prompt-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 8px;
  cursor: pointer;
  background: white;
  border: 1px solid rgba(227, 25, 55, 0.25);
  color: #e31937;
  transition: all 0.15s;
  flex-shrink: 0;
}
.copy-prompt-btn:hover {
  background: rgba(227, 25, 55, 0.06);
  border-color: rgba(227, 25, 55, 0.4);
}

/* ── Context chips ───────────────────────────────────────────── */
.context-chips {
  display: flex;
  gap: 6px;
  padding: 8px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  background: rgba(255,255,255,0.6);
  flex-wrap: wrap;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 99px;
  font-family: 'JetBrains Mono', monospace;
}

.chip-service {
  background: rgba(2, 132, 199, 0.08);
  border: 1px solid rgba(2, 132, 199, 0.2);
  color: #0284c7;
}

.chip-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: #dc2626;
}

/* ── Prompt body (markdown rendered) ────────────────────────── */
.debug-body {
  padding: 16px 20px;
  font-size: 0.875rem;
  line-height: 1.75;
  color: #334155;
}

/* Markdown styles scoped inside the component */
.debug-body :deep(h3) {
  font-size: 0.82rem;
  font-weight: 700;
  color: #1e293b;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 16px 0 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #f1f5f9;
}

.debug-body :deep(h3:first-child) { margin-top: 0; }

.debug-body :deep(blockquote) {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-left: 3px solid #e31937;
  border-radius: 0 8px 8px 0;
  padding: 12px 16px;
  margin: 12px 0;
  font-size: 0.875rem;
  color: #475569;
  font-style: normal;
}

.debug-body :deep(blockquote p) { margin: 0 0 0.5em; }
.debug-body :deep(blockquote p:last-child) { margin: 0; }

.debug-body :deep(strong) { color: #1e293b; font-weight: 700; }

.debug-body :deep(code) {
  background: rgba(15, 23, 42, 0.06);
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 4px;
  padding: 1px 5px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.82em;
  color: #e31937;
}

.debug-body :deep(ol),
.debug-body :deep(ul) {
  padding-left: 20px;
  margin: 8px 0;
}

.debug-body :deep(li) {
  margin: 4px 0;
  color: #475569;
}

.debug-body :deep(p) { margin: 0.5em 0; }
.debug-body :deep(p:first-child) { margin-top: 0; }
.debug-body :deep(p:last-child)  { margin-bottom: 0; }

.debug-body :deep(hr) {
  border: none;
  border-top: 1px solid #e2e8f0;
  margin: 16px 0;
}

/* ── Footer ─────────────────────────────────────────────────── */
.debug-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 10px 16px;
  background: rgba(255,255,255,0.7);
  border-top: 1px solid rgba(0, 0, 0, 0.04);
}

.use-prompt-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.78rem;
  font-weight: 700;
  padding: 7px 16px;
  border-radius: 8px;
  cursor: pointer;
  background: #e31937;
  border: none;
  color: white;
  transition: all 0.15s;
  box-shadow: 0 4px 12px rgba(227, 25, 55, 0.25);
}
.use-prompt-btn:hover {
  background: #c4152f;
  box-shadow: 0 6px 18px rgba(227, 25, 55, 0.35);
  transform: translateY(-1px);
}
</style>
