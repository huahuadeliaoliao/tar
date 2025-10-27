<script setup lang="ts">
import { computed, ref } from 'vue'
import { cn } from '@/utils/cn'
import { Copy, Check } from 'lucide-vue-next'
import Avatar from '@/components/ui/Avatar.vue'
import AiIcon from '@/components/ui/AiIcon.vue'
import Button from '@/components/ui/Button.vue'
import type { Message } from '@/types/chat'

const props = withDefaults(
  defineProps<{
    message: Message
    variant?: 'contained' | 'flat'
    avatarSrc?: string
    avatarFallback?: string
    showCopyButton?: boolean
  }>(),
  {
    variant: 'flat',
    showCopyButton: true,
  },
)

const isUser = computed(() => props.message.role === 'user')
const isCopied = ref(false)

async function copyMessage() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    isCopied.value = true
    setTimeout(() => {
      isCopied.value = false
    }, 2000)
  } catch (error) {
    console.error('Failed to copy message:', error)
  }
}

const messageClasses = computed(() => {
  return cn(
    'group flex w-full min-w-0 items-start gap-3 py-3',
    isUser.value ? 'is-user justify-end' : 'is-assistant justify-start',
  )
})

const contentClasses = computed(() => {
  const base = 'relative flex min-w-0 flex-col gap-3 overflow-hidden rounded-2xl text-sm'

  if (props.variant === 'contained') {
    return cn(
      base,
      'px-4 py-3.5',
      isUser.value
        ? 'max-w-[70%] bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-md'
        : 'max-w-full bg-zinc-100/80 text-zinc-900 backdrop-blur-sm dark:bg-zinc-800/50 dark:text-zinc-100',
    )
  } else {
    return cn(
      base,
      'px-4 py-3.5',
      isUser.value
        ? 'max-w-[70%] bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-md'
        : 'max-w-full bg-white/80 text-zinc-900 shadow-sm backdrop-blur-sm dark:bg-zinc-900/50 dark:text-zinc-100',
    )
  }
})

const aiAvatarClasses =
  'bg-white text-black ring-1 ring-zinc-200 dark:bg-zinc-100 dark:text-zinc-900'
const userAvatarClasses = 'from-blue-500 to-blue-600 text-white'
</script>

<template>
  <div :class="messageClasses">
    <Avatar v-if="!isUser" :src="avatarSrc" :class="aiAvatarClasses">
      <AiIcon :size="18" />
    </Avatar>
    <div :class="contentClasses">
      <slot />
      <Button
        v-if="!isUser && props.showCopyButton && message.content"
        variant="ghost"
        size="icon"
        class="absolute top-2 right-2 h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
        @click="copyMessage"
      >
        <Check v-if="isCopied" :size="14" class="text-green-600" />
        <Copy v-else :size="14" />
      </Button>
    </div>
    <Avatar
      v-if="isUser"
      :src="avatarSrc"
      :fallback="avatarFallback || 'ME'"
      :class="userAvatarClasses"
    />
  </div>
</template>
