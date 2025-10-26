<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/utils/cn'

interface Props {
  variant?: 'default' | 'outline' | 'ghost' | 'destructive'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'default',
  disabled: false,
})

const buttonClasses = computed(() => {
  const base =
    'inline-flex items-center justify-center rounded-xl font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50'

  const variants = {
    default:
      'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-md hover:shadow-lg hover:from-blue-600 hover:to-blue-700',
    outline:
      'border border-zinc-300 bg-white/80 backdrop-blur-sm hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/80 dark:hover:bg-zinc-800',
    ghost: 'hover:bg-zinc-100/80 dark:hover:bg-zinc-800/80',
    destructive: 'bg-red-500 text-white shadow-md hover:bg-red-600 hover:shadow-lg',
  }

  const sizes = {
    default: 'h-10 px-4 py-2 text-sm',
    sm: 'h-8 px-3 text-xs',
    lg: 'h-11 px-8 text-base',
    icon: 'h-10 w-10',
  }

  return cn(base, variants[props.variant], sizes[props.size])
})
</script>

<template>
  <button :class="buttonClasses" :disabled="disabled">
    <slot />
  </button>
</template>
