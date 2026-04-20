<template>
  <div class="star-rating" :class="`star-rating--${size}`" role="group" :aria-label="`Note: ${modelValue} sur 5`">
    <button
      v-for="star in stars"
      :key="star.index"
      class="star-btn"
      :class="{ readonly }"
      :aria-label="`${star.index} étoile${star.index > 1 ? 's' : ''}`"
      :disabled="readonly"
      @click="!readonly && emit('update:modelValue', star.value)"
      @mouseover="!readonly && (hovered = star.value)"
      @mouseleave="!readonly && (hovered = null)"
    >
      <svg
        viewBox="0 0 24 24"
        class="star-icon"
        :class="getStarClass(star)"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient :id="`half-${star.index}`" x1="0" x2="1" y1="0" y2="0">
            <stop offset="50%" stop-color="currentColor" />
            <stop offset="50%" stop-color="transparent" />
          </linearGradient>
        </defs>
        <polygon
          points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"
          :fill="getStarFill(star)"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

const props = withDefaults(defineProps<{
  modelValue: number   // 0.0 - 5.0
  readonly?: boolean
  size?: 'sm' | 'md' | 'lg'
}>(), {
  readonly: false,
  size: 'md'
})

const emit = defineEmits<{
  'update:modelValue': [value: number]
}>()

const hovered = ref<number | null>(null)

const activeValue = computed(() => hovered.value ?? props.modelValue)

// Generate 5 stars with half-star support (click on left = 0.5, right = 1.0)
const stars = computed(() =>
  [1, 2, 3, 4, 5].map(i => ({ index: i, value: i }))
)

function getStarClass(star: { index: number; value: number }) {
  const val = activeValue.value
  if (val >= star.index) return 'star--full'
  if (val >= star.index - 0.5) return 'star--half'
  return 'star--empty'
}

function getStarFill(star: { index: number; value: number }) {
  const val = activeValue.value
  if (val >= star.index) return 'currentColor'
  if (val >= star.index - 0.5) return `url(#half-${star.index})`
  return 'transparent'
}
</script>

<style scoped>
.star-rating {
  display: inline-flex;
  gap: 2px;
  align-items: center;
}

.star-btn {
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  color: #f59e0b;
  transition: transform 0.15s ease;
  line-height: 1;
}

.star-btn:hover:not(.readonly) {
  transform: scale(1.2);
}

.star-btn.readonly {
  cursor: default;
}

.star-btn:disabled {
  cursor: default;
}

.star-icon {
  display: block;
  transition: color 0.15s ease;
}

.star--empty {
  color: rgba(245, 158, 11, 0.3);
}

.star--half, .star--full {
  color: #f59e0b;
}

/* Sizes */
.star-rating--sm .star-icon { width: 14px; height: 14px; }
.star-rating--md .star-icon { width: 20px; height: 20px; }
.star-rating--lg .star-icon { width: 28px; height: 28px; }
</style>
