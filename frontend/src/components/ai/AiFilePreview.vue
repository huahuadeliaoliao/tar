<script setup lang="ts">
import { computed, ref } from 'vue'
import { cn } from '@/utils/cn'
import { FileText, FileImage, Presentation, X } from 'lucide-vue-next'
import AiImagePreview from './AiImagePreview.vue'
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
      color: 'text-zinc-700 bg-zinc-100 dark:bg-zinc-800/60',
      label: '图片',
    },
    pdf: {
      icon: FileText,
      color: 'text-zinc-700 bg-zinc-100 dark:bg-zinc-800/60',
      label: 'PDF',
    },
    docx: {
      icon: FileText,
      color: 'text-zinc-700 bg-zinc-100 dark:bg-zinc-800/60',
      label: 'Word',
    },
    pptx: {
      icon: Presentation,
      color: 'text-zinc-700 bg-zinc-100 dark:bg-zinc-800/60',
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

const isImageAttachment = computed(() => props.file.type === 'image' && Boolean(props.file.url))
const imagePreviewRef = ref<InstanceType<typeof AiImagePreview> | null>(null)
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
    <div class="flex size-12 shrink-0 items-center justify-center">
      <AiImagePreview
        v-if="isImageAttachment"
        ref="imagePreviewRef"
        :src="file.url as string"
        :alt="file.name"
        thumbnail
        max-height="48px"
        thumbnail-overlay="icon"
        class="size-12 !rounded-lg !border-none"
      />
      <div
        v-else
        :class="cn('flex size-12 items-center justify-center rounded-lg', fileConfig.color)"
      >
        <component :is="fileConfig.icon" :size="18" />
      </div>
    </div>
    <div class="min-w-0 flex-1">
      <p class="truncate text-xs font-medium text-zinc-900 dark:text-zinc-100">
        {{ file.name }}
      </p>
      <p class="text-[10px] text-zinc-500 dark:text-zinc-400">
        {{ fileConfig.label }}<template v-if="file.size"> · {{ formatSize(file.size) }}</template>
      </p>
    </div>
    <button
      v-if="removable"
      class="shrink-0 rounded-lg p-1 opacity-0 transition-opacity hover:bg-zinc-100 group-hover:opacity-100 dark:hover:bg-zinc-800"
      @click="emit('remove')"
    >
      <X :size="14" class="text-zinc-500 dark:text-zinc-400" />
    </button>
  </div>
</template>
