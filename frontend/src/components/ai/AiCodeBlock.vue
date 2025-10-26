<script setup lang="ts">
import { ref } from 'vue'
import { cn } from '@/utils/cn'
import { Check, Copy } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import { codeToHtml } from 'shiki'

interface Props {
  code: string
  language?: string
  showLineNumbers?: boolean
  filename?: string
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  language: 'text',
  showLineNumbers: false,
})

const isCopied = ref(false)
const highlightedCode = ref('')

async function highlightCode() {
  try {
    highlightedCode.value = await codeToHtml(props.code, {
      lang: props.language,
      theme: 'github-dark',
    })
  } catch {
    highlightedCode.value = `<pre><code>${props.code}</code></pre>`
  }
}

highlightCode()

async function copyCode() {
  try {
    await navigator.clipboard.writeText(props.code)
    isCopied.value = true
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy code:', error)
  }
}
</script>

<template>
  <div
    :class="
      cn(
        'not-prose group relative my-3 overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-950 shadow-lg dark:border-zinc-800 sm:my-4',
        props.class,
      )
    "
  >
    <div
      v-if="filename"
      class="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-3 py-2 sm:px-4 sm:py-2.5"
    >
      <span class="truncate text-xs text-zinc-400">{{ filename }}</span>
    </div>
    <div class="relative">
      <div class="overflow-x-auto p-3 sm:p-4" v-html="highlightedCode" />
      <Button
        variant="ghost"
        size="icon"
        class="absolute top-2 right-2 opacity-0 transition-opacity group-hover:opacity-100"
        @click="copyCode"
      >
        <Check v-if="isCopied" :size="14" class="text-green-500" />
        <Copy v-else :size="14" />
      </Button>
    </div>
  </div>
</template>

<style>
/* Override the default shiki styles. */
.shiki {
  background-color: transparent !important;
  margin: 0;
  padding: 0;
}

.shiki code {
  font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
  font-size: 0.875rem;
  line-height: 1.5;
}
</style>
