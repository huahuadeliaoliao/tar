<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { Loader2, CheckCircle2 } from 'lucide-vue-next'
import { cn } from '@/utils/cn'
import type { ProcessingState } from '@/types/chat'

interface Props {
  state: ProcessingState
  class?: string
}

const props = defineProps<Props>()

const elapsedTime = ref(0)
let interval: number | null = null

const defaultMessages = {
  file_processing: {
    in_progress: '正在处理文件，请稍等',
    completed: '文件处理成功',
    error: '文件处理失败',
  },
  thinking: {
    in_progress: '正在思考',
    completed: '思考完成',
    error: '思考出错',
  },
}

const displayMessage = computed(() => {
  const step = props.state.step
  const status = props.state.status

  if (status === 'error' && props.state.errorMessage) {
    return props.state.errorMessage
  }

  return defaultMessages[step][status]
})

const formattedTime = computed(() => {
  const time = props.state.endTime
    ? props.state.endTime - props.state.startTime
    : elapsedTime.value * 1000

  const seconds = Math.floor((time / 1000) % 60)
  const minutes = Math.floor(time / 60000)

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`
  }
  return `${seconds}s`
})

const iconClasses = computed(() => {
  if (props.state.status === 'in_progress') {
    return 'animate-spin text-blue-500'
  } else if (props.state.status === 'completed') {
    return 'text-green-500'
  } else {
    return 'text-red-500'
  }
})

onMounted(() => {
  if (props.state.status === 'in_progress') {
    interval = window.setInterval(() => {
      elapsedTime.value++
    }, 1000)
  }
})

onUnmounted(() => {
  if (interval) {
    clearInterval(interval)
  }
})
</script>

<template>
  <div
    :class="
      cn(
        'flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-4 py-3 dark:bg-slate-900/30',
        props.class,
      )
    "
  >
    <div class="flex min-w-0 items-center gap-3">
      <Transition
        mode="out-in"
        enter-active-class="transition-all duration-300"
        leave-active-class="transition-all duration-300"
        enter-from-class="opacity-0 scale-50"
        leave-to-class="opacity-0 scale-50"
      >
        <Loader2
          v-if="state.status === 'in_progress'"
          key="loading"
          :size="16"
          class="shrink-0 sm:size-[18px]"
          :class="iconClasses"
        />
        <CheckCircle2
          v-else-if="state.status === 'completed'"
          key="success"
          :size="16"
          class="shrink-0 sm:size-[18px]"
          :class="iconClasses"
        />
        <div
          v-else
          key="error"
          :size="16"
          class="shrink-0 flex items-center justify-center sm:size-[18px]"
        >
          <svg
            class="h-4 w-4 text-red-500 sm:h-[18px] sm:w-[18px]"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"
            />
          </svg>
        </div>
      </Transition>
      <Transition
        mode="out-in"
        enter-active-class="transition-all duration-300"
        leave-active-class="transition-all duration-300"
        enter-from-class="opacity-0 -translate-x-2"
        leave-to-class="opacity-0 -translate-x-2"
      >
        <span
          :key="`${state.step}-${state.status}`"
          class="text-sm font-medium text-slate-700 dark:text-slate-300 sm:text-base"
        >
          {{ displayMessage }}
        </span>
      </Transition>
    </div>
    <Transition
      enter-active-class="transition-all duration-300"
      leave-active-class="transition-all duration-300"
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
    >
      <span
        v-if="state.status !== 'error'"
        key="time"
        class="shrink-0 text-xs font-medium text-slate-500 dark:text-slate-400 sm:text-sm"
      >
        {{ formattedTime }}
      </span>
    </Transition>
  </div>
</template>
