<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, defineExpose } from 'vue'
import { cn } from '@/utils/cn'
import { ArrowDown } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'

interface Props {
  autoScroll?: boolean
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  autoScroll: true,
})

const containerRef = ref<HTMLDivElement>()
const isAtBottom = ref(true)

let isAutoScrolling = false
let autoScrollTimeout: number | null = null

/**
 * 立即滚动到底部
 * ✅ 关键：滚动时设置标志，避免 scroll 事件误判
 */
function scrollToBottom(behavior: ScrollBehavior = 'auto') {
  if (!containerRef.value) return

  isAutoScrolling = true

  if (autoScrollTimeout) {
    clearTimeout(autoScrollTimeout)
  }

  requestAnimationFrame(() => {
    if (!containerRef.value) return

    containerRef.value.scrollTo({
      top: containerRef.value.scrollHeight,
      behavior,
    })

    autoScrollTimeout = window.setTimeout(() => {
      isAutoScrolling = false
    }, 500)
  })
}

/**
 * 处理用户手动滚动
 * ✅ 如果是自动滚动产生的 scroll 事件，直接忽略
 */
function handleScroll() {
  if (!containerRef.value) return

  if (isAutoScrolling) {
    return
  }

  const { scrollTop, scrollHeight, clientHeight } = containerRef.value
  const distanceFromBottom = scrollHeight - clientHeight - scrollTop

  isAtBottom.value = distanceFromBottom < 100
}

onMounted(() => {
  requestAnimationFrame(() => {
    scrollToBottom('auto')
    isAtBottom.value = true
  })
})

onBeforeUnmount(() => {
  if (autoScrollTimeout) {
    clearTimeout(autoScrollTimeout)
  }
})

defineExpose({
  scrollToBottom,
  isUserNearBottom: () => {
    if (!containerRef.value) return true
    const { scrollTop, scrollHeight, clientHeight } = containerRef.value
    const distanceFromBottom = scrollHeight - clientHeight - scrollTop
    return distanceFromBottom < 100
  },
})
</script>

<template>
  <div class="relative flex flex-1 flex-col overflow-hidden">
    <div
      ref="containerRef"
      :class="cn('relative flex-1 overflow-y-auto overflow-x-hidden', props.class)"
      role="log"
      @scroll="handleScroll"
    >
      <div class="min-w-0 max-w-full p-6">
        <slot />
      </div>
    </div>
    <Transition
      enter-active-class="transition-all duration-200"
      leave-active-class="transition-all duration-200"
      enter-from-class="opacity-0 translate-y-2"
      leave-to-class="opacity-0 translate-y-2"
    >
      <Button
        v-if="!isAtBottom"
        variant="outline"
        size="icon"
        class="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full shadow-lg"
        @click="scrollToBottom('smooth')"
      >
        <ArrowDown :size="16" />
      </Button>
    </Transition>
  </div>
</template>
