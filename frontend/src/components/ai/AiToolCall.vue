<script setup lang="ts">
import { ref, computed } from 'vue'
import { cn } from '@/utils/cn'
import { ChevronDown, Wrench, CheckCircle, XCircle, Clock, Circle } from 'lucide-vue-next'
import Badge from '@/components/ui/Badge.vue'
import type { ToolCallPart } from '@/types/chat'

interface Props {
  toolCall: ToolCallPart
  defaultOpen?: boolean
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  defaultOpen: false,
})

const isOpen = ref(props.defaultOpen)

const statusConfig = computed(() => {
  const configs = {
    calling: {
      label: 'Pending',
      icon: Circle,
      variant: 'secondary' as const,
    },
    executing: {
      label: 'Running',
      icon: Clock,
      variant: 'warning' as const,
    },
    success: {
      label: 'Completed',
      icon: CheckCircle,
      variant: 'success' as const,
    },
    error: {
      label: 'Error',
      icon: XCircle,
      variant: 'error' as const,
    },
  }
  return configs[props.toolCall.status]
})
</script>

<template>
  <div
    :class="
      cn(
        'not-prose my-3 w-full max-w-full overflow-hidden rounded-2xl border border-zinc-200 shadow-sm dark:border-zinc-800 sm:my-4',
        props.class,
      )
    "
  >
    <button
      class="flex w-full items-center justify-between gap-2 p-3 text-left transition-colors hover:bg-zinc-50 dark:hover:bg-zinc-900 sm:gap-4 sm:p-4"
      @click="isOpen = !isOpen"
    >
      <div class="flex min-w-0 flex-1 items-center gap-1.5 sm:gap-2">
        <Wrench :size="16" class="shrink-0 text-zinc-500 dark:text-zinc-400" />
        <span class="truncate text-sm font-medium">{{ toolCall.name }}</span>
        <Badge :variant="statusConfig.variant" class="shrink-0">
          <component :is="statusConfig.icon" :size="14" />
          <span class="hidden sm:inline">{{ statusConfig.label }}</span>
        </Badge>
      </div>
      <ChevronDown
        :size="16"
        class="shrink-0 text-zinc-500 dark:text-zinc-400 transition-transform"
        :class="{ 'rotate-180': isOpen }"
      />
    </button>
    <Transition
      enter-active-class="transition-all duration-200"
      leave-active-class="transition-all duration-200"
      enter-from-class="opacity-0 max-h-0"
      leave-to-class="opacity-0 max-h-0"
      enter-to-class="opacity-100 max-h-[1000px]"
      leave-from-class="opacity-100 max-h-[1000px]"
    >
      <div v-if="isOpen" class="overflow-hidden border-t border-zinc-200 dark:border-zinc-800">
        <div class="space-y-2 p-3 sm:p-4">
          <h4 class="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            Parameters
          </h4>
          <div class="w-full overflow-x-auto rounded-xl bg-zinc-50 p-2.5 dark:bg-zinc-900 sm:p-3">
            <pre
              class="w-max max-w-full whitespace-pre text-xs"
            ><code>{{ JSON.stringify(toolCall.input, null, 2) }}</code></pre>
          </div>
        </div>
        <div v-if="toolCall.output" class="space-y-2 p-3 pt-0 sm:p-4 sm:pt-0">
          <h4 class="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {{ toolCall.status === 'error' ? 'Error' : 'Result' }}
          </h4>
          <div
            :class="
              cn(
                'w-full overflow-x-auto rounded-xl p-2.5 sm:p-3',
                toolCall.status === 'error'
                  ? 'bg-red-50 text-red-900 dark:bg-red-950/50 dark:text-red-200'
                  : 'bg-zinc-50 dark:bg-zinc-900',
              )
            "
          >
            <pre
              class="w-max max-w-full whitespace-pre text-xs"
            ><code>{{ JSON.stringify(toolCall.output, null, 2) }}</code></pre>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
