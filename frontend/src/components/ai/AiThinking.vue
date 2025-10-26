<script setup lang="ts">
import { cn } from '@/utils/cn'
import AiLoader from './AiLoader.vue'

interface Props {
  message?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  message: '正在思考如何回答...',
})
</script>

<template>
  <div
    :class="
      cn(
        'flex items-center gap-2 rounded-xl bg-zinc-100/80 px-4 py-2.5 text-sm text-zinc-600 backdrop-blur-sm dark:bg-zinc-800/50 dark:text-zinc-400',
        props.class,
      )
    "
  >
    <AiLoader :size="14" />
    <span>{{ message }}</span>
  </div>
</template>
