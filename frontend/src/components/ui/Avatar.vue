<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/utils/cn'

interface Props {
  src?: string
  alt?: string
  fallback?: string
  size?: 'sm' | 'md' | 'lg'
  class?: string
  showIcon?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  fallback: 'U',
  showIcon: false,
})

const sizeClasses = {
  sm: 'size-6 text-xs',
  md: 'size-8 text-sm',
  lg: 'size-10 text-base',
}

const avatarClasses = computed(() => {
  return cn(
    'flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-gradient-to-br font-semibold',
    sizeClasses[props.size],
    props.class,
  )
})
</script>

<template>
  <div :class="avatarClasses">
    <img v-if="src" :src="src" :alt="alt || fallback" class="size-full object-cover" />
    <slot v-else-if="$slots.default" />
    <span v-else>{{ fallback }}</span>
  </div>
</template>
