<script setup lang="ts">
import { computed, ref, watch, onUnmounted, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { cn } from '@/utils/cn'
import AiImagePreview from './AiImagePreview.vue'
import AiFilePreview from './AiFilePreview.vue'
import type { FileAttachment } from '@/types/chat'

interface Props {
  content: string
  streaming?: boolean
  files?: FileAttachment[]
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  streaming: false,
  files: () => [],
})

const displayContent = ref('')
const typingInterval = ref<number>()
const typingAnimationFrame = ref<number>()
let lastContentLength = 0

marked.setOptions({
  breaks: true,
  gfm: true,
})

const renderedContent = computed(() => {
  if (!displayContent.value) return ''
  return marked.parse(displayContent.value)
})

function isValidHttpUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

function normalizeImageUrl(rawUrl: string): string | null {
  let sanitized = rawUrl.trim().replace(/&amp;/gi, '&')
  if (!sanitized) return null

  if (sanitized.startsWith('//')) {
    sanitized = `https:${sanitized}`
  }

  if (!/^https?:\/\//i.test(sanitized)) {
    return null
  }

  const candidates: string[] = [sanitized]
  const trailingChars = '),.;'

  for (const candidate of candidates) {
    if (isValidHttpUrl(candidate)) {
      return candidate
    }

    let trimmed = candidate
    while (trimmed.length > 0 && trailingChars.includes(trimmed.charAt(trimmed.length - 1))) {
      trimmed = trimmed.slice(0, -1)
      if (isValidHttpUrl(trimmed)) {
        return trimmed
      }
    }
  }

  return null
}

function hasImageExtension(url: string): boolean {
  const fragmentIndex = url.indexOf('#')
  const withoutFragment = fragmentIndex === -1 ? url : url.slice(0, fragmentIndex)
  const queryIndex = withoutFragment.indexOf('?')
  const withoutQuery = queryIndex === -1 ? withoutFragment : withoutFragment.slice(0, queryIndex)
  const imagePattern = /\.(?:png|jpe?g|gif|webp|bmp|svg)(?:![^/]*)?$/i
  return imagePattern.test(withoutQuery)
}

const inlineImageUrls = computed(() => {
  const pattern = /(https?:\/\/[^\s)]+)/gi
  const attachmentUrls = new Set(
    (props.files || [])
      .filter((file) => file.type === 'image' && file.url)
      .map((file) => file.url as string),
  )
  const urls = new Set<string>()

  const source = props.content || ''
  let match: RegExpExecArray | null
  while ((match = pattern.exec(source)) !== null) {
    const rawUrl = match[1]
    if (!rawUrl) continue
    const normalized = normalizeImageUrl(rawUrl)
    if (!normalized) continue
    if (!hasImageExtension(normalized)) continue
    if (!attachmentUrls.has(normalized)) {
      urls.add(normalized)
    }
  }

  return Array.from(urls)
})

const contentRef = ref<HTMLElement | null>(null)

function updateAnchorTargets() {
  nextTick(() => {
    if (!contentRef.value) return
    const anchors = contentRef.value.querySelectorAll<HTMLAnchorElement>('a[href]')
    anchors.forEach((anchor) => {
      anchor.setAttribute('target', '_blank')
      anchor.setAttribute('rel', 'noopener noreferrer')
    })
  })
}

function typeContent() {
  if (!props.streaming) {
    displayContent.value = props.content
    lastContentLength = props.content.length
    return
  }

  const currentLength = props.content.length

  if (currentLength === lastContentLength) {
    return
  }

  if (currentLength > lastContentLength) {
    let index = lastContentLength
    lastContentLength = currentLength

    clearInterval(typingInterval.value)
    if (typingAnimationFrame.value) {
      cancelAnimationFrame(typingAnimationFrame.value)
    }

    let lastUpdateTime = Date.now()
    const charsPerMs = 0.05

    function animateTyping() {
      const now = Date.now()
      const timeDelta = now - lastUpdateTime
      const charsToAdd = Math.max(1, Math.floor(timeDelta * charsPerMs))

      index = Math.min(index + charsToAdd, currentLength)
      displayContent.value = props.content.slice(0, index)
      lastUpdateTime = now

      if (index < currentLength) {
        typingAnimationFrame.value = requestAnimationFrame(animateTyping)
      }
    }

    typingAnimationFrame.value = requestAnimationFrame(animateTyping)
  } else if (currentLength === 0) {
    displayContent.value = ''
    lastContentLength = 0
    clearInterval(typingInterval.value)
    if (typingAnimationFrame.value) {
      cancelAnimationFrame(typingAnimationFrame.value)
    }
  }
}

watch(() => props.content, typeContent, { immediate: true })
watch(renderedContent, updateAnchorTargets)

onMounted(() => {
  updateAnchorTargets()
})

onUnmounted(() => {
  clearInterval(typingInterval.value)
  if (typingAnimationFrame.value) {
    cancelAnimationFrame(typingAnimationFrame.value)
  }
})
</script>

<template>
  <div :class="cn('flex min-w-0 flex-col gap-2', props.class)">
    <div v-if="files && files.length > 0" class="flex min-w-0 flex-wrap gap-2">
      <template v-for="file in files" :key="file.id">
        <AiImagePreview
          v-if="file.type === 'image' && file.url"
          :src="file.url"
          :alt="file.name"
          thumbnail
          max-height="150px"
          class="w-full sm:w-auto sm:max-w-[200px]"
        />
        <AiFilePreview v-else :file="file" class="w-full sm:w-auto" />
      </template>
    </div>
    <div
      v-if="renderedContent"
      ref="contentRef"
      class="prose prose-sm min-w-0 max-w-none dark:prose-invert prose-p:my-3 prose-pre:my-3 prose-headings:mt-4 prose-headings:mb-2 prose-h1:text-lg prose-h2:text-base prose-h3:text-sm prose-li:my-1 prose-ol:my-3 prose-ul:my-3 prose-blockquote:my-3 prose-blockquote:pl-3 prose-img:my-3 prose-strong:font-semibold prose-code:text-amber-600 dark:prose-code:text-amber-400"
      v-html="renderedContent"
    />
    <div v-if="inlineImageUrls.length > 0" class="flex min-w-0 flex-wrap gap-2">
      <AiImagePreview
        v-for="url in inlineImageUrls"
        :key="url"
        :src="url"
        :alt="`外部图像 ${url}`"
        thumbnail
        max-height="150px"
        class="w-full sm:w-auto sm:max-w-[200px]"
      />
    </div>
  </div>
</template>

<style>
/* Custom prose styles. */
.prose {
  color: inherit;
}

.prose :where(code):not(:where([class~='not-prose'] *)) {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 0.125rem 0.25rem;
  border-radius: 0.25rem;
  font-size: 0.875em;
}

.dark .prose :where(code):not(:where([class~='not-prose'] *)) {
  background-color: rgba(255, 255, 255, 0.1);
}

.prose :where(pre):not(:where([class~='not-prose'] *)) {
  background-color: rgb(24, 24, 27);
  color: rgb(250, 250, 250);
  border-radius: 0.5rem;
  padding: 1rem;
  overflow-x: auto;
  max-width: 100%;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  line-height: 1.5;
}

/* Code blocks inside prose. */
.prose :where(pre code):not(:where([class~='not-prose'] *)) {
  background-color: transparent;
  padding: 0;
  border-radius: 0;
  font-size: inherit;
  color: inherit;
}

.prose :where(table):not(:where([class~='not-prose'] *)) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
  margin-top: 1rem;
  margin-bottom: 1rem;
}

.prose :where(thead):not(:where([class~='not-prose'] *)) {
  border-bottom: 1px solid rgb(228, 228, 231);
}

.dark .prose :where(thead):not(:where([class~='not-prose'] *)) {
  border-bottom-color: rgb(63, 63, 70);
}

.prose :where(th):not(:where([class~='not-prose'] *)) {
  padding: 0.5rem 0.75rem;
  text-align: left;
  font-weight: 600;
  font-size: 0.875rem;
  color: rgb(24, 24, 27);
}

.dark .prose :where(th):not(:where([class~='not-prose'] *)) {
  color: rgb(250, 250, 250);
}

.prose :where(td):not(:where([class~='not-prose'] *)) {
  padding: 0.5rem 0.75rem;
  border-top: 1px solid rgb(228, 228, 231);
  font-size: 0.875rem;
}

.dark .prose :where(td):not(:where([class~='not-prose'] *)) {
  border-top-color: rgb(63, 63, 70);
}

.prose :where(tbody tr):not(:where([class~='not-prose'] *)):hover {
  background-color: rgb(250, 250, 250);
}

.dark .prose :where(tbody tr):not(:where([class~='not-prose'] *)):hover {
  background-color: rgb(39, 39, 42);
}

.prose :where(a):not(:where([class~='not-prose'] *)) {
  color: #1f2937;
  text-decoration: underline;
  font-weight: 500;
}

.prose :where(a):not(:where([class~='not-prose'] *)):hover {
  color: #111827;
}

.dark .prose :where(a):not(:where([class~='not-prose'] *)) {
  color: #e5e7eb;
}

.dark .prose :where(a):not(:where([class~='not-prose'] *)):hover {
  color: #f5f5f5;
}

/* Increase spacing for lists. */
.prose :where(ol > li):not(:where([class~='not-prose'] *)),
.prose :where(ul > li):not(:where([class~='not-prose'] *)) {
  margin-top: 0.375rem;
  margin-bottom: 0.375rem;
}

/* Improve blockquote styling. */
.prose :where(blockquote):not(:where([class~='not-prose'] *)) {
  border-left: 3px solid rgb(209, 213, 219);
  padding-left: 1rem;
  font-style: italic;
  color: rgb(87, 87, 87);
}

.dark .prose :where(blockquote):not(:where([class~='not-prose'] *)) {
  border-left-color: rgb(63, 63, 70);
  color: rgb(212, 212, 212);
}

/* Image styling. */
.prose :where(img):not(:where([class~='not-prose'] *)) {
  border-radius: 0.5rem;
  max-width: 100%;
  height: auto;
}
</style>
