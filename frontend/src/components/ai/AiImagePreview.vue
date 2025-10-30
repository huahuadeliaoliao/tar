<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { cn } from '@/utils/cn'
import { ExternalLink, X, ZoomIn } from 'lucide-vue-next'

type ThumbnailOverlay = 'default' | 'icon' | 'none'

interface Props {
  src: string
  alt?: string
  class?: string
  thumbnail?: boolean
  maxHeight?: string
  thumbnailOverlay?: ThumbnailOverlay
}

const props = withDefaults(defineProps<Props>(), {
  thumbnail: false,
  maxHeight: '200px',
  thumbnailOverlay: 'default',
})

const showModal = ref(false)
const loadError = ref(false)

const preferredSrc = computed(() => {
  if (props.src.startsWith('//')) {
    return `https:${props.src}`
  }
  if (props.src.startsWith('http://')) {
    return `https://${props.src.slice('http://'.length)}`
  }
  return props.src
})

const currentSrc = ref(preferredSrc.value)

watch(
  () => props.src,
  () => {
    currentSrc.value = preferredSrc.value
    loadError.value = false
  },
)

watch(preferredSrc, (value) => {
  currentSrc.value = value
  loadError.value = false
})

function openPreview() {
  if (loadError.value) return
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

function handleImageError() {
  if (currentSrc.value !== props.src) {
    currentSrc.value = props.src
  } else {
    loadError.value = true
  }
}

defineExpose({
  openPreview,
  closePreview,
})
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
      @click="thumbnail && !loadError ? openPreview() : undefined"
    >
      <template v-if="!loadError">
        <img
          :src="currentSrc"
          :alt="alt || 'Image'"
          :class="
            cn(
              'object-cover transition-transform duration-200',
              thumbnail ? 'h-full w-full group-hover:scale-105' : 'w-full object-contain',
            )
          "
          loading="lazy"
          @error="handleImageError"
        />
        <template v-if="thumbnail">
          <div
            v-if="props.thumbnailOverlay === 'default'"
            class="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100"
          >
            <div
              class="flex items-center gap-2 rounded-lg bg-white/90 px-3 py-2 text-sm font-medium text-zinc-900 dark:bg-zinc-900/90 dark:text-white"
            >
              <ZoomIn :size="16" />
              <span>Click to view</span>
            </div>
          </div>
          <div
            v-else-if="props.thumbnailOverlay === 'icon'"
            class="pointer-events-none absolute right-2 top-2 flex size-6 items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity group-hover:opacity-100"
          >
            <ZoomIn :size="14" />
          </div>
        </template>
      </template>
      <div
        v-else
        class="flex h-full w-full flex-col items-center justify-center gap-3 bg-zinc-50 px-4 py-6 text-center text-sm text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
      >
        <ExternalLink :size="20" />
        <div class="flex flex-col gap-1">
          <span>图片加载失败</span>
          <a
            :href="props.src"
            target="_blank"
            rel="noopener noreferrer"
            class="text-zinc-700 hover:text-zinc-900 hover:underline dark:text-zinc-100 dark:hover:text-white"
          >
            在新标签页打开
          </a>
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
          v-if="showModal && !loadError"
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
            :src="currentSrc"
            :alt="alt || 'Image'"
            class="max-h-[90vh] max-w-[90vw] rounded-lg object-contain shadow-2xl"
            @click.stop
          />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
