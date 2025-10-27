<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionsStore } from '@/stores/sessions'
import { useFileUpload } from '@/composables/useFileUpload'
import { sessionsApi, chatApi, filesApi } from '@/api'
import Sidebar from '@/components/layout/Sidebar.vue'
import ModelSelector from '@/components/ui/ModelSelector.vue'
import {
  AiConversation,
  AiMessage,
  AiResponse,
  AiThinking,
  AiToolCall,
  AiError,
  AiPromptInput,
  AiProcessingStep,
} from '@/components/ai'
import type {
  Message,
  AssistantMessage,
  ToolCallPart,
  FileAttachment,
  MessagePart,
} from '@/types/chat'
import type { SSEEvent } from '@/types/api'
import { Loader2, Settings, Check, X, Edit2, Copy, ChevronDown } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const sessionsStore = useSessionsStore()
const { uploading, uploadFiles } = useFileUpload()

const messages = ref<Message[]>([])
const loading = ref(false)
const sidebarOpen = ref(false)
const conversationRef = ref<InstanceType<typeof AiConversation>>()
const pendingFiles = ref<(FileAttachment & { _file?: File })[]>([])

const editingTitle = ref(false)
const editedTitle = ref('')
const editingModel = ref(false)
const editedModelId = ref('')
const updating = ref(false)

const sessionId = computed(() => {
  const id = route.params.id
  return id ? Number(id) : null
})

async function loadSessionMessages() {
  if (!sessionId.value) {
    messages.value = []
    return
  }

  loading.value = true

  try {
    const detail = await sessionsApi.get(sessionId.value)

    messages.value = convertApiMessages(detail.messages)
  } catch (error) {
    console.error('Failed to load messages:', error)
    router.push('/')
  } finally {
    loading.value = false
  }
}

function parseAssistantContent(raw: string | null | undefined) {
  let finalText = ''
  const progressSegments: string[] = []

  if (typeof raw === 'string' && raw.length > 0) {
    try {
      const parsed = JSON.parse(raw)

      if (parsed && typeof parsed === 'object' && parsed.type === 'assistant_final') {
        if (typeof parsed.final === 'string') {
          finalText = parsed.final
        }

        if (Array.isArray(parsed.progress)) {
          for (const segment of parsed.progress) {
            if (typeof segment === 'string' && segment.trim().length > 0) {
              progressSegments.push(segment)
            }
          }
        }
      } else {
        finalText = raw
      }
    } catch (error) {
      console.warn('Failed to parse assistant content payload:', error)
      finalText = raw
    }
  }

  if (!finalText && typeof raw === 'string') {
    finalText = raw
  }

  const progressLog = progressSegments.join('\n\n').trim()

  return { finalText: finalText || '', progressLog, progressSegments }
}

function convertApiMessages(apiMessages: any[]): Message[] {
  const converted: Message[] = []
  let currentAssistant: AssistantMessage | null = null

  for (const msg of apiMessages) {
    if (msg.role === 'user') {
      try {
        const content = typeof msg.content === 'string' ? JSON.parse(msg.content) : msg.content
        const textParts = content.filter((c: any) => c.type === 'text')
        const text = textParts.map((t: any) => t.text).join('\n')

        const files: FileAttachment[] = []

        const fileMetadata: { [filename: string]: { pages: number[]; indices: number[] } } = {}
        let contentIndex = 0

        for (const part of content) {
          if (part.type === 'text') {
            const metaMatches = part.text.matchAll(/\[文件: (.+?), 第(\d+)页\]/g)
            for (const match of metaMatches) {
              const filename = match[1]
              const page = parseInt(match[2])

              if (!fileMetadata[filename]) {
                fileMetadata[filename] = { pages: [], indices: [] }
              }
              fileMetadata[filename].pages.push(page)
              fileMetadata[filename].indices.push(contentIndex)
            }
          }
          contentIndex++
        }

        const imageParts = content.filter((c: any) => c.type === 'image_url')
        const imageUrls = imageParts.map((img: any) => img.image_url?.url || '')

        if (Object.keys(fileMetadata).length > 0) {
          let imageIndex = 0

          for (const [filename, meta] of Object.entries(fileMetadata)) {
            const ext = filename.toLowerCase().split('.').pop() || ''
            let fileType: 'pdf' | 'docx' | 'pptx' | 'image' = 'image'

            if (ext === 'pdf') {
              fileType = 'pdf'
            } else if (ext === 'docx' || ext === 'doc') {
              fileType = 'docx'
            } else if (ext === 'pptx' || ext === 'ppt') {
              fileType = 'pptx'
            }

            if (fileType !== 'image') {
              files.push({
                id: Date.now() + Math.random(),
                name: filename,
                type: fileType,
                mimeType: `application/${fileType}`,
                size: 0,
              })
            }

            for (let i = 0; i < meta.pages.length; i++) {
              if (imageIndex < imageUrls.length) {
                const imageUrl = imageUrls[imageIndex]
                if (imageUrl.startsWith('data:image/')) {
                  const mimeMatch = imageUrl.match(/^data:(image\/\w+);base64,/)
                  const mimeType = mimeMatch ? mimeMatch[1] : 'image/webp'

                  files.push({
                    id: Date.now() + Math.random() + imageIndex,
                    name: `${filename.replace(/\.\w+$/, '')}-page-${meta.pages[i]}.webp`,
                    type: 'image',
                    mimeType,
                    size: 0,
                    url: imageUrl,
                  })
                }
                imageIndex++
              }
            }
          }
        } else {
          for (let i = 0; i < imageUrls.length; i++) {
            const imageUrl = imageUrls[i]
            if (imageUrl.startsWith('data:image/')) {
              const mimeMatch = imageUrl.match(/^data:(image\/\w+);base64,/)
              const mimeType = mimeMatch ? mimeMatch[1] : 'image/webp'

              files.push({
                id: Date.now() + Math.random() + i,
                name: `image-${i + 1}.webp`,
                type: 'image',
                mimeType,
                size: 0,
                url: imageUrl,
              })
            }
          }
        }

        converted.push({
          id: String(msg.id),
          role: 'user',
          content: text.replace(/\[文件: .+?, 第\d+页\]\n?/g, '').trim(),
          files: files.length > 0 ? files : undefined,
          timestamp: new Date(msg.created_at).getTime(),
        })
      } catch (error) {
        console.error('Failed to parse user message:', error)
      }
    } else if (msg.role === 'assistant') {
      if (msg.tool_call_id) {
        if (!currentAssistant) {
          currentAssistant = {
            id: String(msg.id),
            role: 'assistant',
            content: '',
            parts: [],
            progressLog: '',
            progressSegments: [],
            isProgressCollapsed: false,
            timestamp: new Date(msg.created_at).getTime(),
            status: 'done',
          }
        }

        const toolCall: ToolCallPart = {
          type: 'tool_call',
          id: msg.tool_call_id,
          name: msg.tool_name || '',
          input: msg.tool_input ? JSON.parse(msg.tool_input) : {},
          status: 'success',
          timestamp: new Date(msg.created_at).getTime(),
        }

        const toolResult = apiMessages.find(
          (m) => m.role === 'tool' && m.tool_call_id === msg.tool_call_id,
        )
        if (toolResult && toolResult.tool_output) {
          try {
            toolCall.output = JSON.parse(toolResult.tool_output)
            toolCall.success = !toolCall.output?.error
            if (!toolCall.success) {
              toolCall.status = 'error'
            }
          } catch (error) {
            console.error('Failed to parse tool output:', error)
          }
        }

        currentAssistant.parts.push(toolCall)
      } else {
        const { finalText, progressLog, progressSegments } = parseAssistantContent(msg.content)

        if (currentAssistant) {
          currentAssistant.content = finalText
          currentAssistant.progressLog = progressLog
          currentAssistant.progressSegments = progressSegments
          currentAssistant.isProgressCollapsed = progressLog.length > 0
          currentAssistant.metadata = {
            model_id: msg.model_id,
          }
          converted.push(currentAssistant)
          currentAssistant = null
        } else {
          converted.push({
            id: String(msg.id),
            role: 'assistant',
            content: finalText,
            parts: [],
            progressLog,
            progressSegments,
            isProgressCollapsed: progressLog.length > 0,
            timestamp: new Date(msg.created_at).getTime(),
            status: 'done',
            metadata: {
              model_id: msg.model_id,
            },
          })
        }
      }
    }
  }

  if (currentAssistant) {
    converted.push(currentAssistant)
  }

  return converted
}

const copiedMessageId = ref<string | null>(null)

function getMessageParts(message: AssistantMessage, type: MessagePart['type']) {
  return message.parts.filter((part) => part.type === type)
}

function hasExecutionLog(message: AssistantMessage) {
  return (
    getMessageParts(message, 'thinking').length > 0 ||
    getMessageParts(message, 'tool_call').length > 0 ||
    getMessageParts(message, 'error').length > 0 ||
    !!message.progressLog?.trim()
  )
}

function getProgressPreview(message: AssistantMessage) {
  if (!message.progressLog) return ''
  const trimmed = message.progressLog.trim()
  if (trimmed.length <= 120) {
    return trimmed
  }
  return `${trimmed.slice(0, 117)}...`
}

function toggleExecutionLog(message: AssistantMessage) {
  message.isProgressCollapsed = !message.isProgressCollapsed
}

async function copyFinalAnswer(message: AssistantMessage) {
  try {
    await navigator.clipboard.writeText(message.content)
    copiedMessageId.value = message.id
    setTimeout(() => {
      if (copiedMessageId.value === message.id) {
        copiedMessageId.value = null
      }
    }, 2000)
  } catch (error) {
    console.error('Failed to copy assistant response:', error)
  }
}

async function waitForFileProcessing(fileId: number, maxRetries: number = 120) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const status = await filesApi.getStatus(fileId)

      if (status.processing_status === 'completed') {
        return true
      }

      if (status.processing_status === 'failed') {
        console.error('File processing failed:', status.error_message)
        return false
      }

      await new Promise((resolve) => setTimeout(resolve, 500))
    } catch (error) {
      console.error('Failed to check file status:', error)
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
  }

  console.error('File processing timeout')
  return false
}

async function handleSubmit(content: string, files: (FileAttachment & { _file?: File })[]) {
  if (!sessionId.value) {
    try {
      const session = await sessionsStore.createSession({
        title: content.slice(0, 50),
        model_id: sessionsStore.selectedModelId,
      })

      pendingFiles.value = files

      router.push(`/chat/${session.id}`)
      return
    } catch (error) {
      console.error('Failed to create session:', error)
      return
    }
  }

  const messageContent = content.trim() || (files.length > 0 ? '[上传了文件]' : '')

  let uploadedFiles: FileAttachment[] = []
  if (files.length > 0) {
    uploadedFiles = files.map((f) => ({
      id: f.id,
      name: f.name,
      type: f.type,
      mimeType: f.mimeType,
      size: f.size,
      url: f.url,
    }))
  }

  const userMessage: Message = {
    id: `user-${Date.now()}`,
    role: 'user',
    content: messageContent,
    files: uploadedFiles.length > 0 ? uploadedFiles : undefined,
    timestamp: Date.now(),
  }
  const userMessageIndex = messages.value.push(userMessage) - 1

  const assistantMessage: AssistantMessage = {
    id: `assistant-${Date.now()}`,
    role: 'assistant',
    content: '',
    parts: [],
    progressLog: '',
    progressSegments: [],
    isProgressCollapsed: false,
    timestamp: Date.now(),
    status: 'streaming',
    processingStates:
      files.length > 0
        ? [
            {
              step: 'file_processing',
              status: 'in_progress',
              startTime: Date.now(),
            },
          ]
        : [],
  }
  const messageIndex = messages.value.push(assistantMessage) - 1

  await nextTick()
  scrollToBottom()

  let fileIds: number[] = []
  if (files.length > 0) {
    try {
      fileIds = await uploadFiles(files)

      for (const fileId of fileIds) {
        const success = await waitForFileProcessing(fileId)
        if (!success) {
          throw new Error(`文件处理失败: ID ${fileId}`)
        }
      }

      try {
        const userMsg = messages.value[userMessageIndex] as Message
        if (userMsg.role === 'user' && userMsg.files) {
          const updatedFiles: FileAttachment[] = []

          for (const fileId of fileIds) {
            try {
              const imagesResponse = await filesApi.getImages(fileId)

              if (imagesResponse.images && imagesResponse.images.length > 0) {
                const originalFile = uploadedFiles.find((f) => (f.id as any) === fileId)

                if (originalFile?.type === 'image' && imagesResponse.images.length === 1) {
                  const firstImage = imagesResponse.images[0]
                  if (!firstImage) {
                    continue
                  }
                  updatedFiles.push({
                    id: fileId,
                    name: originalFile.name,
                    type: originalFile.type,
                    mimeType: originalFile.mimeType,
                    size: originalFile.size,
                    url: firstImage.image_data_base64
                      ? `data:image/webp;base64,${firstImage.image_data_base64}`
                      : undefined,
                  })
                } else {
                  for (const img of imagesResponse.images) {
                    updatedFiles.push({
                      id: img.image_id ?? fileId * 1000 + img.page,
                      name: originalFile?.name || `page-${img.page}`,
                      type: originalFile?.type || 'image',
                      mimeType: originalFile?.mimeType || 'image/webp',
                      size: 0,
                      url: img.image_data_base64
                        ? `data:image/webp;base64,${img.image_data_base64}`
                        : undefined,
                    })
                  }
                }
              }
            } catch (error) {
              console.error(`Failed to fetch images for file ${fileId}:`, error)
              const originalFile = uploadedFiles.find((f) => (f.id as any) === fileId)
              if (originalFile) {
                updatedFiles.push(originalFile)
              }
            }
          }

          if (updatedFiles.length > 0) {
            userMsg.files = updatedFiles
            await nextTick()
          }
        }
      } catch (error) {
        console.error('Failed to process file images:', error)
      }
    } catch (error) {
      console.error('File upload or processing failed:', error)
      const msg = messages.value[messageIndex] as AssistantMessage
      const fileState = msg.processingStates?.find((s) => s.step === 'file_processing')
      if (fileState) {
        fileState.status = 'error'
        fileState.errorMessage = '文件处理失败'
        fileState.endTime = Date.now()
      }
      return
    }
  }

  try {
    let sseConnected = false

    for await (const event of chatApi.streamChat({
      session_id: sessionId.value,
      message: messageContent,
      files: fileIds.length > 0 ? fileIds : undefined,
    })) {
      if (!sseConnected) {
        sseConnected = true
        const msg = messages.value[messageIndex] as AssistantMessage

        if (
          msg.processingStates &&
          msg.processingStates.some((s) => s.step === 'file_processing')
        ) {
          const fileState = msg.processingStates.find((s) => s.step === 'file_processing')!
          fileState.status = 'completed'
          fileState.endTime = Date.now()
        }

        msg.processingStates = msg.processingStates || []
        msg.processingStates.push({
          step: 'thinking',
          status: 'in_progress',
          startTime: Date.now(),
        })
      }

      if (event.type === 'thinking') {
        continue
      }

      const result = handleSSEEvent(event, messages.value[messageIndex] as AssistantMessage)

      if (result === 'content_delta') {
        scrollToBottom()
      } else {
        await nextTick()
        scrollToBottom()
      }
    }

    const msg = messages.value[messageIndex] as AssistantMessage
    msg.status = 'done'

    const thinkingState = msg.processingStates?.find((s) => s.step === 'thinking')
    if (thinkingState) {
      thinkingState.status = 'completed'
      thinkingState.endTime = Date.now()
    }

    sessionsStore.touchSession(sessionId.value)
  } catch (error: any) {
    console.error('Chat error:', error)
    const msg = messages.value[messageIndex] as AssistantMessage
    msg.status = 'error'
    msg.parts.push({
      type: 'error',
      code: 'STREAM_ERROR',
      message: error.message || '发送消息失败',
      timestamp: Date.now(),
    })

    const thinkingState = msg.processingStates?.find((s) => s.step === 'thinking')
    if (thinkingState && thinkingState.status === 'in_progress') {
      thinkingState.status = 'error'
      thinkingState.endTime = Date.now()
      thinkingState.errorMessage = error.message || '思考出错'
    }
  }
}

function handleSSEEvent(event: SSEEvent, message: AssistantMessage): string | void {
  switch (event.type) {
    case 'status':
      if (event.status === 'awaiting_more_actions') {
        message.status = 'streaming'
      }
      break

    case 'content_start': {
      const guarded = (event as any).guarded ?? false
      if (guarded) {
        message.isProgressCollapsed = false
      } else if (hasExecutionLog(message)) {
        message.isProgressCollapsed = true
      }
      break
    }

    case 'thinking':
      message.parts.push({
        type: 'thinking',
        message: event.message,
        timestamp: event.timestamp,
      })
      break

    case 'tool_call':
      message.parts.push({
        type: 'tool_call',
        id: event.tool_call_id,
        name: event.tool_name,
        input: event.tool_input,
        status: 'calling',
        timestamp: event.timestamp,
      })
      break

    case 'tool_executing':
      const executingTool = message.parts.find(
        (p) => p.type === 'tool_call' && p.id === event.tool_call_id,
      ) as ToolCallPart | undefined
      if (executingTool) {
        executingTool.status = 'executing'
      }
      break

    case 'tool_result':
      const resultTool = message.parts.find(
        (p) => p.type === 'tool_call' && p.id === event.tool_call_id,
      ) as ToolCallPart | undefined
      if (resultTool) {
        resultTool.output = event.tool_output
        resultTool.success = event.success
        resultTool.status = event.success ? 'success' : 'error'
      }
      break

    case 'content_delta':
      if ((event as any).guarded) {
        message.progressLog = (message.progressLog || '') + ((event as any).delta || '')
      } else {
        message.content += (event as any).delta || ''
      }
      return 'content_delta'

    case 'content_done':
      break

    case 'done':
      message.metadata = {
        ...message.metadata,
        total_time_ms: event.total_time_ms,
        iterations: event.total_iterations,
      }
      if (message.progressLog) {
        message.progressSegments = message.progressLog
          .split(/\n\n+/)
          .map((segment) => segment.trim())
          .filter(Boolean)
        message.isProgressCollapsed = true
      }
      break

    case 'error':
      message.parts.push({
        type: 'error',
        code: event.error_code,
        message: event.error_message,
        timestamp: event.timestamp,
      })
      break
  }
}

function scrollToBottom() {
  if (!conversationRef.value) {
    return
  }

  const isNearBottom = (conversationRef.value as any).isUserNearBottom?.()

  if (isNearBottom) {
    ;(conversationRef.value as any).scrollToBottom?.()
  }
}

function startEditTitle() {
  if (!sessionsStore.currentSession) return
  editedTitle.value = sessionsStore.currentSession.title || ''
  editingTitle.value = true
  nextTick(() => {
    const input = document.querySelector('.title-input') as HTMLInputElement
    input?.focus()
    input?.select()
  })
}

function startEditModel() {
  if (!sessionsStore.currentSession) return
  editedModelId.value = sessionsStore.currentSession.model_id
  editingModel.value = true
}

async function saveTitle() {
  if (!sessionId.value || !editedTitle.value.trim()) {
    editingTitle.value = false
    return
  }

  updating.value = true
  try {
    await sessionsStore.updateSession(sessionId.value, { title: editedTitle.value.trim() })
    editingTitle.value = false
  } catch (error) {
    console.error('Failed to update title:', error)
  } finally {
    updating.value = false
  }
}

async function saveModel() {
  if (!sessionId.value || !editedModelId.value) {
    editingModel.value = false
    return
  }

  updating.value = true
  try {
    await sessionsStore.updateSession(sessionId.value, { model_id: editedModelId.value })
    editingModel.value = false
  } catch (error) {
    console.error('Failed to update model:', error)
  } finally {
    updating.value = false
  }
}

function cancelEditTitle() {
  editingTitle.value = false
  editedTitle.value = ''
}

function cancelEditModel() {
  editingModel.value = false
  editedModelId.value = ''
}

watch(
  () => route.params.id,
  async () => {
    await loadSessionMessages()
    sessionsStore.setCurrentSession(sessionId.value)

    if (pendingFiles.value.length > 0 && sessionId.value) {
      pendingFiles.value = []
    }
  },
  { immediate: true },
)

onMounted(() => {
  if (sessionsStore.models.length === 0) {
    sessionsStore.loadModels()
  }
})
</script>

<template>
  <div
    class="flex h-screen overflow-x-hidden bg-gradient-to-br from-zinc-50 to-zinc-100 dark:from-zinc-950 dark:to-zinc-900"
  >
    <Sidebar v-model="sidebarOpen" />
    <div class="flex flex-1 flex-col overflow-x-hidden lg:ml-64">
      <header
        v-if="sessionId"
        class="border-b border-zinc-200/50 bg-white/80 px-4 py-3 backdrop-blur-md dark:border-zinc-800/50 dark:bg-zinc-950/80"
      >
        <div class="mx-auto max-w-4xl">
          <div class="mb-2 flex items-center gap-2">
            <template v-if="editingTitle">
              <input
                v-model="editedTitle"
                type="text"
                id="edit-title-input"
                name="title"
                autocomplete="off"
                class="title-input flex-1 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm font-medium text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                placeholder="输入会话标题..."
                @keyup.enter="saveTitle"
                @keyup.escape="cancelEditTitle"
              />
              <button
                @click="saveTitle"
                :disabled="updating || !editedTitle.trim()"
                class="rounded-md p-1.5 text-green-600 hover:bg-green-50 disabled:opacity-50 dark:hover:bg-green-950"
              >
                <Check :size="18" />
              </button>
              <button
                @click="cancelEditTitle"
                :disabled="updating"
                class="rounded-md p-1.5 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              >
                <X :size="18" />
              </button>
            </template>
            <template v-else>
              <h1 class="flex-1 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                {{ sessionsStore.currentSession?.title || '未命名对话' }}
              </h1>
              <button
                @click="startEditTitle"
                class="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
                title="编辑标题"
              >
                <Edit2 :size="16" />
              </button>
            </template>
          </div>
          <div class="flex items-center gap-2">
            <span class="shrink-0 text-xs font-medium text-zinc-600 dark:text-zinc-400">模型:</span>
            <template v-if="editingModel">
              <ModelSelector
                id="model-selector"
                name="model"
                autocomplete="off"
                v-model="editedModelId"
                :models="sessionsStore.models"
                :disabled="updating"
                class="flex-1"
              />
              <button
                @click="saveModel"
                :disabled="updating || !editedModelId"
                class="rounded-md p-1.5 text-green-600 hover:bg-green-50 disabled:opacity-50 dark:hover:bg-green-950"
              >
                <Check :size="18" />
              </button>
              <button
                @click="cancelEditModel"
                :disabled="updating"
                class="rounded-md p-1.5 text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              >
                <X :size="18" />
              </button>
            </template>
            <template v-else>
              <span class="flex-1 text-sm text-zinc-700 dark:text-zinc-300">
                {{
                  sessionsStore.models.find((m) => m.id === sessionsStore.currentSession?.model_id)
                    ?.name || sessionsStore.currentSession?.model_id
                }}
              </span>
              <button
                @click="startEditModel"
                class="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-700 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-300"
                title="更换模型"
              >
                <Settings :size="16" />
              </button>
            </template>
          </div>
        </div>
      </header>
      <div class="flex flex-1 flex-col overflow-hidden">
        <div v-if="loading" class="flex flex-1 items-center justify-center">
          <Loader2 :size="32" class="animate-spin text-zinc-400" />
        </div>
        <div
          v-else-if="!sessionId || messages.length === 0"
          class="flex flex-1 items-center justify-center p-4"
        >
          <div class="text-center">
            <h2 class="text-2xl font-bold text-zinc-900 dark:text-zinc-100 sm:text-3xl">
              你好！我是 tar 智能助手
            </h2>
            <p class="mt-2 text-sm text-zinc-500 sm:text-base">
              我可以帮你回答问题、分析文件、执行任务
            </p>
            <p class="mt-1 text-xs text-zinc-400 sm:text-sm">支持图片、PDF、Word、PPT 文件上传</p>
          </div>
        </div>
        <AiConversation v-else ref="conversationRef">
          <AiMessage
            v-for="message in messages"
            :key="message.id"
            :message="message"
            :show-copy-button="message.role === 'user'"
          >
            <template v-if="message.role === 'user'">
              <AiResponse :content="message.content" :files="message.files" />
            </template>
            <template v-else>
              <AiProcessingStep
                v-for="state in (message as AssistantMessage).processingStates"
                :key="`${state.step}-${state.status}`"
                :state="state"
                class="mb-3"
              />
              <div class="flex flex-col gap-4">
                <div
                  v-if="hasExecutionLog(message as AssistantMessage)"
                  class="relative rounded-2xl border border-zinc-200/70 bg-white p-4 shadow-sm transition-all dark:border-zinc-800/70 dark:bg-zinc-900/50"
                  :class="
                    (message as AssistantMessage).isProgressCollapsed
                      ? 'max-h-36 overflow-hidden'
                      : ''
                  "
                >
                  <div class="flex items-center justify-between gap-2">
                    <p class="text-sm font-medium text-zinc-700 dark:text-zinc-200">执行日志</p>
                    <button
                      type="button"
                      class="flex items-center gap-1 rounded-full border border-zinc-300/70 bg-white/80 px-3 py-1 text-xs font-medium text-zinc-600 shadow-sm transition hover:border-zinc-400 hover:text-zinc-900 dark:border-zinc-700/70 dark:bg-zinc-900/70 dark:text-zinc-300 dark:hover:border-zinc-500 dark:hover:text-zinc-100"
                      @click="toggleExecutionLog(message as AssistantMessage)"
                    >
                      <span>{{
                        (message as AssistantMessage).isProgressCollapsed ? '展开' : '收起'
                      }}</span>
                      <ChevronDown
                        :size="14"
                        class="transition-transform"
                        :class="{
                          '-rotate-180': !(message as AssistantMessage).isProgressCollapsed,
                        }"
                      />
                    </button>
                  </div>
                  <div class="relative mt-3">
                    <div
                      class="execution-log-content space-y-3 pr-1 text-sm leading-relaxed text-zinc-700 dark:text-zinc-200"
                      :class="{
                        'max-h-32 overflow-hidden': (message as AssistantMessage)
                          .isProgressCollapsed,
                      }"
                    >
                      <AiThinking
                        v-for="(part, i) in getMessageParts(
                          message as AssistantMessage,
                          'thinking',
                        )"
                        :key="`thinking-${i}`"
                        :message="(part as any).message"
                      />
                      <AiToolCall
                        v-for="(part, i) in getMessageParts(
                          message as AssistantMessage,
                          'tool_call',
                        )"
                        :key="`tool-${i}`"
                        :tool-call="part as any"
                      />
                      <AiError
                        v-for="(part, i) in getMessageParts(message as AssistantMessage, 'error')"
                        :key="`error-${i}`"
                        :error-code="(part as any).code"
                        :error-message="(part as any).message"
                      />
                      <div
                        v-if="(message as AssistantMessage).progressLog"
                        class="rounded-xl border border-zinc-200/70 bg-zinc-100/70 p-3 font-mono text-xs text-zinc-700 shadow-inner dark:border-zinc-800/60 dark:bg-zinc-800/40 dark:text-zinc-200"
                      >
                        <pre class="max-h-96 overflow-y-auto whitespace-pre-wrap">{{
                          (message as AssistantMessage).progressLog
                        }}</pre>
                      </div>
                    </div>
                    <div
                      v-if="
                        (message as AssistantMessage).isProgressCollapsed &&
                        (message as AssistantMessage).progressLog
                      "
                      class="pointer-events-none absolute inset-x-0 bottom-0 translate-y-1/2 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-zinc-500 shadow-md dark:bg-zinc-900/90 dark:text-zinc-300"
                    >
                      {{ getProgressPreview(message as AssistantMessage) }}
                    </div>
                  </div>
                </div>

                <div
                  class="relative group/answer rounded-2xl border border-zinc-200/70 bg-white p-4 shadow-sm dark:border-zinc-800/70 dark:bg-zinc-900/50"
                >
                  <button
                    v-if="message.content"
                    type="button"
                    class="absolute top-4 right-4 flex items-center justify-center rounded-full border border-zinc-200/70 bg-white/80 p-2 text-zinc-500 opacity-0 transition group-hover/answer:opacity-100 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-700/70 dark:bg-zinc-900/70 dark:text-zinc-300 dark:hover:border-zinc-500 dark:hover:text-zinc-100"
                    @click="copyFinalAnswer(message as AssistantMessage)"
                  >
                    <Check
                      v-if="copiedMessageId === message.id"
                      :size="16"
                      class="text-emerald-500"
                    />
                    <Copy v-else :size="16" />
                  </button>
                  <AiResponse
                    v-if="message.content"
                    :content="message.content"
                    :streaming="message.status === 'streaming'"
                  />
                </div>
              </div>
            </template>
          </AiMessage>
        </AiConversation>
      </div>
      <AiPromptInput
        :placeholder="sessionId ? '输入消息...' : '输入消息开始新对话...'"
        :disabled="
          loading ||
          uploading ||
          (messages.length > 0 && messages[messages.length - 1]?.status === 'streaming')
        "
        @submit="handleSubmit"
      />
    </div>
  </div>
</template>
