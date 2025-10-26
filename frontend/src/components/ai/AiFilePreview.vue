<script setup lang="ts">
import { computed } from 'vue'
import { cn } from '@/utils/cn'
import { FileText, FileImage, Presentation, X } from 'lucide-vue-next'
import type { FileAttachment } from '@/types/chat'

interface Props {
  file: FileAttachment
  removable?: boolean
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  removable: false,
})

const emit = defineEmits<{
  remove: []
}>()

const fileConfig = computed(() => {
  const configs = {
    image: {
      icon: FileImage,
      color: 'text-blue-600 bg-blue-50 dark:bg-blue-950/30',
      label: '图片',
    },
    pdf: {
      icon: FileText,
      color: 'text-red-600 bg-red-50 dark:bg-red-950/30',
      label: 'PDF',
    },
    docx: {
      icon: FileText,
      color: 'text-blue-600 bg-blue-50 dark:bg-blue-950/30',
      label: 'Word',
    },
    pptx: {
      icon: Presentation,
      color: 'text-orange-600 bg-orange-50 dark:bg-orange-950/30',
      label: 'PPT',
    },
  }
  return configs[props.file.type]
})

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<template>
  <div
    :class="
      cn(
        'group relative flex items-center gap-2 rounded-xl border border-zinc-200 bg-white p-2.5 dark:border-zinc-700 dark:bg-zinc-900',
        props.class,
      )
    "
  >
    <div
      :class="cn('flex size-8 shrink-0 items-center justify-center rounded-lg', fileConfig.color)"
    >
      <component :is="fileConfig.icon" :size="16" />
    </div>
    <div class="min-w-0 flex-1">
      <p class="truncate text-xs font-medium text-zinc-900 dark:text-zinc-100">
        {{ file.name }}
      </p>
      <p class="text-[10px] text-zinc-500">
        {{ fileConfig.label }}<template v-if="file.size"> · {{ formatSize(file.size) }}</template>
      </p>
    </div>
    <button
      v-if="removable"
      class="shrink-0 rounded-lg p-1 opacity-0 transition-opacity hover:bg-zinc-100 group-hover:opacity-100 dark:hover:bg-zinc-800"
      @click="emit('remove')"
    >
      <X :size="14" class="text-zinc-500" />
    </button>
  </div>
</template>
