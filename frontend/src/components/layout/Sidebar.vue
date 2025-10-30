<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { cn } from '@/utils/cn'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import Button from '@/components/ui/Button.vue'
import Badge from '@/components/ui/Badge.vue'
import { Plus, MessageSquare, Trash2, LogOut, X, Menu, Loader2 } from 'lucide-vue-next'

interface Props {
  modelValue: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const router = useRouter()
const authStore = useAuthStore()
const sessionsStore = useSessionsStore()

const deletingSessionId = ref<number | null>(null)

const isOpen = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

function closeSidebar() {
  isOpen.value = false
}

async function handleNewChat() {
  try {
    const defaultModel = sessionsStore.models[0]?.id || 'gemini-2.5-flash-thinking'

    const session = await sessionsStore.createSession({
      title: '新对话',
      model_id: defaultModel,
    })

    router.push(`/chat/${session.id}`)
    closeSidebar()
  } catch (error) {
    console.error('Failed to create session:', error)
  }
}

function selectSession(sessionId: number) {
  sessionsStore.setCurrentSession(sessionId)
  router.push(`/chat/${sessionId}`)
  closeSidebar()
}

async function deleteSession(sessionId: number, event: Event) {
  event.stopPropagation()

  if (!confirm('确定要删除这个对话吗？')) return

  deletingSessionId.value = sessionId

  try {
    await sessionsStore.deleteSession(sessionId)

    if (sessionsStore.currentSessionId === sessionId) {
      router.push('/')
    }
  } catch (error) {
    console.error('Failed to delete session:', error)
  } finally {
    deletingSessionId.value = null
  }
}

function handleLogout() {
  if (confirm('确定要退出登录吗?')) {
    authStore.logout()
    sessionsStore.reset()
    router.push('/auth')
  }
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`

  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
    @click="closeSidebar"
  />
  <aside
    :class="[
      'fixed left-0 top-0 z-50 flex h-full w-64 flex-col border-r border-zinc-200/50 bg-white/80 backdrop-blur-md transition-transform duration-300 dark:border-zinc-800/50 dark:bg-zinc-950/80',
      isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
    ]"
  >
    <div
      class="flex items-center justify-between border-b border-zinc-200/50 px-4 py-3 dark:border-zinc-800/50"
    >
      <h1 class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">对话列表</h1>
      <Button variant="ghost" size="icon" class="h-8 w-8 lg:hidden" @click="closeSidebar">
        <X :size="18" />
      </Button>
    </div>
    <div class="p-3">
      <Button
        class="w-full justify-center"
        @click="handleNewChat"
        :disabled="sessionsStore.loading"
      >
        <Plus :size="16" class="mr-2" />
        新建对话
      </Button>
    </div>
    <div class="flex-1 overflow-y-auto px-2 pb-2">
      <div
        v-if="sessionsStore.loading && sessionsStore.sessions.length === 0"
        class="flex items-center justify-center py-8"
      >
        <Loader2 :size="24" class="animate-spin text-zinc-400" />
      </div>

      <div v-else-if="sessionsStore.sessions.length === 0" class="px-4 py-8 text-center">
        <MessageSquare :size="32" class="mx-auto mb-2 text-zinc-300 dark:text-zinc-700" />
        <p class="text-sm text-zinc-500 dark:text-zinc-400">还没有对话</p>
        <p class="mt-1 text-xs text-zinc-400 dark:text-zinc-500">点击上方按钮开始新对话</p>
      </div>

      <div v-else class="space-y-1">
        <button
          v-for="session in sessionsStore.sortedSessions"
          :key="session.id"
          :class="[
            'group relative w-full rounded-xl px-3 py-2.5 text-left transition-all',
            sessionsStore.currentSessionId === session.id
              ? 'bg-zinc-200/80 ring-2 ring-zinc-400/30 dark:bg-zinc-800/70'
              : 'hover:bg-zinc-100/80 dark:hover:bg-zinc-800/50',
          ]"
          @click="selectSession(session.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <p
                :class="[
                  'truncate text-sm font-medium',
                  sessionsStore.currentSessionId === session.id
                    ? 'text-zinc-900 dark:text-zinc-50'
                    : 'text-zinc-900 dark:text-zinc-100',
                ]"
              >
                {{ session.title || '新对话' }}
              </p>
              <div class="mt-1 flex items-center gap-2">
                <Badge
                  :class="
                    cn(
                      'text-xs',
                      sessionsStore.currentSessionId === session.id
                        ? 'bg-zinc-900 text-white dark:bg-zinc-200 dark:text-zinc-900'
                        : 'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400',
                    )
                  "
                >
                  {{ session.model_id.split('-')[0] }}
                </Badge>
                <span class="text-xs text-zinc-500 dark:text-zinc-400">
                  {{ formatDate(session.updated_at) }}
                </span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              class="h-7 w-7 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
              :disabled="deletingSessionId === session.id"
              @click="(e: Event) => deleteSession(session.id, e)"
            >
              <Loader2 v-if="deletingSessionId === session.id" :size="14" class="animate-spin" />
              <Trash2 v-else :size="14" />
            </Button>
          </div>
        </button>
      </div>
    </div>
    <div class="border-t border-zinc-200/50 p-3 dark:border-zinc-800/50">
      <div
        class="flex items-center justify-between rounded-xl bg-zinc-100/80 px-3 py-2.5 dark:bg-zinc-800/50"
      >
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {{ authStore.user?.username }}
          </p>
          <p class="text-xs text-zinc-500 dark:text-zinc-400">在线</p>
        </div>

        <Button variant="ghost" size="icon" class="h-8 w-8 shrink-0" @click="handleLogout">
          <LogOut :size="16" />
        </Button>
      </div>
    </div>
  </aside>
  <Button
    variant="outline"
    size="icon"
    class="fixed left-4 top-4 z-30 lg:hidden"
    @click="isOpen = !isOpen"
  >
    <Menu :size="18" />
  </Button>
</template>

<style scoped>
/* Custom scrollbar */
aside::-webkit-scrollbar {
  width: 6px;
}

aside::-webkit-scrollbar-track {
  background: transparent;
}

aside::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.1);
  border-radius: 10px;
}

aside::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.2);
}

:global(.dark) aside::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
}

:global(.dark) aside::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
