<script setup lang="ts">
import { ref, computed } from 'vue'
import { cn } from '@/utils/cn'
import { Send, Paperclip } from 'lucide-vue-next'
import Button from '@/components/ui/Button.vue'
import AiFilePreview from './AiFilePreview.vue'
import type { FileAttachment } from '@/types/chat'

interface Props {
  placeholder?: string
  disabled?: boolean
  class?: string
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: '输入消息...',
  disabled: false,
})

const emit = defineEmits<{
  submit: [content: string, files: (FileAttachment & { _file?: File })[]]
}>()

const inputValue = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()
const attachedFiles = ref<FileAttachment[]>([])

const uniqueId = `prompt-input-${Math.random().toString(36).substr(2, 9)}`
const textareaId = `${uniqueId}-textarea`
const fileInputId = `${uniqueId}-file-input`

const canSubmit = computed(() => {
  return (inputValue.value.trim().length > 0 || attachedFiles.value.length > 0) && !props.disabled
})

function handleSubmit() {
  if (!canSubmit.value) return

  const filesToSend = [...attachedFiles.value]

  const blobUrlsToRevoke = filesToSend.filter((f) => f.url?.startsWith('blob:')).map((f) => f.url!)

  emit('submit', inputValue.value.trim(), filesToSend)

  inputValue.value = ''

  setTimeout(() => {
    blobUrlsToRevoke.forEach((url) => {
      try {
        URL.revokeObjectURL(url)
      } catch {}
    })
  }, 1000)

  attachedFiles.value = []

  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}

function adjustHeight() {
  if (!textareaRef.value) return

  textareaRef.value.style.height = 'auto'

  const maxHeight = window.innerHeight * 0.5
  const newHeight = Math.min(textareaRef.value.scrollHeight, maxHeight)

  textareaRef.value.style.height = `${newHeight}px`
}

function openFilePicker() {
  fileInputRef.value?.click()
}

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  const files = target.files
  if (!files || files.length === 0) return

  const allowedTypes = {
    'image/jpeg': 'image',
    'image/jpg': 'image',
    'image/png': 'image',
    'image/gif': 'image',
    'image/webp': 'image',
    // PDF
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/msword': 'docx',
    'application/vnd.ms-word': 'docx',
    'application/x-msword': 'docx',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
    'application/vnd.ms-powerpoint': 'pptx',
    'application/mspowerpoint': 'pptx',
  } as const

  for (const file of Array.from(files)) {
    let fileType = allowedTypes[file.type as keyof typeof allowedTypes]

    if (!fileType) {
      const ext = file.name.toLowerCase().split('.').pop()
      if (ext === 'docx' || ext === 'doc') {
        fileType = 'docx'
      } else if (ext === 'pptx' || ext === 'ppt') {
        fileType = 'pptx'
      } else if (ext === 'pdf') {
        fileType = 'pdf'
      } else if (['jpg', 'jpeg', 'png', 'gif', 'webp'].includes(ext || '')) {
        fileType = 'image'
      }
    }

    if (!fileType) {
      alert(`不支持的文件类型: ${file.type || file.name}`)
      continue
    }

    if (file.size > 50 * 1024 * 1024) {
      alert(`文件 ${file.name} 超过 50MB 限制`)
      continue
    }

    let url = undefined
    if (fileType === 'image') {
      url = URL.createObjectURL(file)
    }

    const fileAttachment: FileAttachment & { _file?: File } = {
      id: Date.now() + Math.random(),
      name: file.name,
      type: fileType,
      mimeType: file.type,
      size: file.size,
      url,
      _file: file,
    }

    attachedFiles.value.push(fileAttachment)
  }

  target.value = ''
}

function removeFile(index: number) {
  const file = attachedFiles.value[index]
  if (!file) return

  if (file.url) {
    setTimeout(() => {
      URL.revokeObjectURL(file.url!)
    }, 100)
  }
  attachedFiles.value.splice(index, 1)
}
</script>

<template>
  <div
    :class="
      cn(
        'border-t border-zinc-200 bg-white/80 p-3 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-950/80 sm:p-4',
        props.class,
      )
    "
  >
    <div class="mx-auto max-w-4xl">
      <slot name="header" />
      <div v-if="attachedFiles.length > 0" class="mb-3 flex flex-wrap gap-2">
        <AiFilePreview
          v-for="(file, index) in attachedFiles"
          :key="file.id"
          :file="file"
          removable
          class="w-full sm:w-auto"
          @remove="removeFile(index)"
        />
      </div>
      <div class="flex items-end gap-2 sm:gap-3">
        <div class="flex shrink-0 items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            class="h-10 w-10 rounded-xl"
            :disabled="disabled"
            @click="openFilePicker"
          >
            <Paperclip :size="18" />
          </Button>
        </div>
        <div class="relative flex-1">
          <textarea
            :id="textareaId"
            ref="textareaRef"
            v-model="inputValue"
            name="message"
            autocomplete="off"
            :placeholder="placeholder"
            :disabled="disabled"
            class="w-full resize-none rounded-2xl border border-zinc-300 bg-white px-4 py-3 text-sm shadow-sm outline-none transition-all placeholder:text-zinc-400 focus:border-blue-500 focus:shadow-md focus:ring-4 focus:ring-blue-500/10 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:focus:border-blue-400 sm:px-5 sm:py-3.5"
            rows="1"
            @input="adjustHeight"
            @keydown="handleKeydown"
          />
        </div>
        <Button
          :disabled="!canSubmit"
          size="icon"
          class="shrink-0 rounded-xl"
          @click="handleSubmit"
        >
          <Send :size="16" />
        </Button>
      </div>
      <input
        :id="fileInputId"
        ref="fileInputRef"
        type="file"
        name="attachments"
        accept="image/jpeg,image/png,image/gif,image/webp,.pdf,.doc,.docx,.ppt,.pptx"
        multiple
        class="hidden"
        @change="handleFileSelect"
      />
      <p class="mt-2 hidden text-center text-xs text-zinc-500 sm:block">
        按
        <kbd class="rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono shadow-sm dark:bg-zinc-800"
          >Enter</kbd
        >
        发送，<kbd class="rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono shadow-sm dark:bg-zinc-800"
          >Shift</kbd
        >
        +
        <kbd class="rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono shadow-sm dark:bg-zinc-800"
          >Enter</kbd
        >
        换行
      </p>
    </div>
  </div>
</template>

<style scoped>
/* Acrylic-inspired scrollbar styling. */
textarea::-webkit-scrollbar {
  width: 6px;
}

textarea::-webkit-scrollbar-track {
  background: transparent;
}

textarea::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 10px;
  backdrop-filter: blur(10px);
}

textarea::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.25);
}

/* Dark theme adjustment. */
:global(.dark) textarea::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
}

:global(.dark) textarea::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

/* Firefox */
textarea {
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.15) transparent;
}

:global(.dark) textarea {
  scrollbar-color: rgba(255, 255, 255, 0.2) transparent;
}
</style>
