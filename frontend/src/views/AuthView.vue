<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'
import Card from '@/components/ui/Card.vue'
import AiIcon from '@/components/ui/AiIcon.vue'
import { LogIn, UserPlus, Loader2 } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const registrationToken = ref('')

const errors = ref<{
  username?: string
  password?: string
  confirmPassword?: string
  registrationToken?: string
  general?: string
}>({})

const isLogin = computed(() => mode.value === 'login')
const loading = computed(() => authStore.loading)

function clearErrors() {
  errors.value = {}
  authStore.clearError()
}

function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  clearErrors()
  password.value = ''
  confirmPassword.value = ''
  registrationToken.value = ''
}

function validate(): boolean {
  clearErrors()

  if (!username.value) {
    errors.value.username = '请输入用户名'
    return false
  }

  if (username.value.length < 3 || username.value.length > 50) {
    errors.value.username = '用户名长度应在 3-50 之间'
    return false
  }

  if (!password.value) {
    errors.value.password = '请输入密码'
    return false
  }

  if (password.value.length < 6) {
    errors.value.password = '密码长度至少为 6 位'
    return false
  }

  if (!isLogin.value) {
    if (!confirmPassword.value) {
      errors.value.confirmPassword = '请确认密码'
      return false
    }

    if (password.value !== confirmPassword.value) {
      errors.value.confirmPassword = '两次输入的密码不一致'
      return false
    }

    if (!registrationToken.value) {
      errors.value.registrationToken = '请输入注册令牌'
      return false
    }
  }

  return true
}

async function handleSubmit() {
  if (!validate()) return

  try {
    if (isLogin.value) {
      await authStore.login({
        username: username.value,
        password: password.value,
      })
    } else {
      await authStore.register({
        username: username.value,
        password: password.value,
        registration_token: registrationToken.value,
      })
    }

    router.push('/')
  } catch (error: any) {
    errors.value.general = error.message || (isLogin.value ? '登录失败' : '注册失败')
  }
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    handleSubmit()
  }
}
</script>

<template>
  <div
    class="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-zinc-50 to-zinc-100 p-4 dark:from-zinc-950 dark:to-zinc-900"
  >
    <div class="mb-8 flex flex-col items-center gap-4">
      <div
        class="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-zinc-200 to-zinc-400 shadow-lg"
      >
        <AiIcon :size="32" class="text-white" />
      </div>
      <h1 class="text-2xl font-bold text-zinc-900 dark:text-zinc-100">tar 智能助手</h1>
    </div>
    <Card class="w-full max-w-md p-6 sm:p-8">
      <h2 class="mb-6 text-center text-xl font-semibold text-zinc-900 dark:text-zinc-100">
        {{ isLogin ? '登录' : '注册' }}
      </h2>
      <div
        v-if="errors.general"
        class="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-900/20 dark:text-red-200"
      >
        {{ errors.general }}
      </div>
      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div>
          <label
            for="username"
            class="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            用户名
          </label>
          <Input
            id="username"
            name="username"
            autocomplete="username"
            v-model="username"
            placeholder="请输入用户名"
            :error="errors.username"
            :disabled="loading"
            @keydown="handleKeydown"
          />
        </div>
        <div>
          <label
            for="password"
            class="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            密码
          </label>
          <Input
            id="password"
            name="password"
            :autocomplete="isLogin ? 'current-password' : 'new-password'"
            v-model="password"
            type="password"
            placeholder="请输入密码"
            :error="errors.password"
            :disabled="loading"
            @keydown="handleKeydown"
          />
        </div>
        <div v-if="!isLogin">
          <label
            for="confirmPassword"
            class="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            确认密码
          </label>
          <Input
            id="confirmPassword"
            name="confirmPassword"
            autocomplete="new-password"
            v-model="confirmPassword"
            type="password"
            placeholder="请再次输入密码"
            :error="errors.confirmPassword"
            :disabled="loading"
            @keydown="handleKeydown"
          />
        </div>
        <div v-if="!isLogin">
          <label
            for="registrationToken"
            class="mb-1.5 block text-sm font-medium text-zinc-700 dark:text-zinc-300"
          >
            注册令牌
          </label>
          <Input
            id="registrationToken"
            name="registrationToken"
            autocomplete="off"
            v-model="registrationToken"
            placeholder="请输入注册令牌"
            :error="errors.registrationToken"
            :disabled="loading"
            @keydown="handleKeydown"
          />
          <p class="mt-1.5 text-xs text-zinc-500 dark:text-zinc-400">请联系管理员获取注册令牌</p>
        </div>
        <Button type="submit" class="w-full" :disabled="loading">
          <Loader2 v-if="loading" :size="16" class="mr-2 animate-spin" />
          <LogIn v-else-if="isLogin" :size="16" class="mr-2" />
          <UserPlus v-else :size="16" class="mr-2" />
          {{ loading ? '处理中...' : isLogin ? '登录' : '注册' }}
        </Button>
      </form>
      <div class="mt-6 text-center">
        <button
          type="button"
          class="text-sm text-zinc-600 hover:text-zinc-900 hover:underline dark:text-zinc-300 dark:hover:text-white"
          :disabled="loading"
          @click="switchMode"
        >
          {{ isLogin ? '还没有账号？立即注册' : '已有账号？立即登录' }}
        </button>
      </div>
    </Card>
    <p class="mt-8 text-center text-xs text-zinc-500 dark:text-zinc-400">Powered by ActReply</p>
  </div>
</template>
