<script setup lang="ts">
import { ref } from 'vue'
import { cn } from '@/utils/cn'
import { X, ZoomIn } from 'lucide-vue-next'

interface Props {
  src: string
  alt?: string
  class?: string
  thumbnail?: boolean
  maxHeight?: string
}

const props = withDefaults(defineProps<Props>(), {
  thumbnail: false,
  maxHeight: '200px',
})

const showModal = ref(false)

function openPreview() {
  showModal.value = true
}

function closePreview() {
  showModal.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    closePreview()
  }
}
</script>

<template>
  <div>
    <div
      :class="
        cn(
          'not-prose group relative overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800',
          thumbnail ? 'cursor-pointer' : '',
          props.class,
        )
      "
      :style="thumbnail ? { maxHeight: maxHeight } : {}"
      @click="thumbnail ? openPreview() : undefined"
    >
      <img
        :src="src"
        :alt="alt || 'Image'"
        :class="
          cn(
            'object-cover transition-transform duration-200',
            thumbnail ? 'h-full w-full group-hover:scale-105' : 'w-full object-contain',
          )
        "
        loading="lazy"
      />
      <div
        v-if="thumbnail"
        class="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100"
      >
        <div
          class="flex items-center gap-2 rounded-lg bg-white/90 px-3 py-2 text-sm font-medium text-zinc-900 dark:bg-zinc-900/90 dark:text-white"
        >
          <ZoomIn :size="16" />
          <span>Click to view</span>
        </div>
      </div>
    </div>
    <Teleport to="body">
      <Transition
        enter-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-200"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-sm"
          @click="closePreview"
          @keydown="handleKeydown"
        >
          <button
            class="absolute top-4 right-4 rounded-full bg-white/10 p-2 text-white transition-colors hover:bg-white/20"
            @click.stop="closePreview"
          >
            <X :size="24" />
          </button>
          <img
            :src="src"
            :alt="alt || 'Image'"
            class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
            @click.stop
          />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
