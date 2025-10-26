<script setup lang="ts">
import { cn } from '@/utils/cn'
import { AlertCircle } from 'lucide-vue-next'

interface Props {
  errorCode: string
  errorMessage: string
  class?: string
}

const props = defineProps<Props>()
</script>

<template>
  <div
    :class="
      cn(
        'not-prose my-4 rounded-2xl border border-red-200 bg-red-50/80 p-4 shadow-sm backdrop-blur-sm dark:border-red-900 dark:bg-red-950/30',
        props.class,
      )
    "
  >
    <div class="flex items-start gap-3">
      <AlertCircle :size="20" class="shrink-0 text-red-600 dark:text-red-400" />
      <div class="flex-1">
        <h4 class="font-semibold text-red-900 text-sm dark:text-red-200">错误</h4>
        <p class="mt-1 text-red-700 text-xs dark:text-red-300">
          <span class="font-mono">{{ errorCode }}</span>
        </p>
        <p class="mt-1 text-red-800 text-sm dark:text-red-200">{{ errorMessage }}</p>
      </div>
    </div>
  </div>
</template>
