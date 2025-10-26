/**
 * Authentication state management store.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'
import type { UserInfo, UserLogin, UserRegister } from '@/types/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => user.value !== null)

  /**
   * Register a new user and log them in.
   */
  async function register(data: UserRegister): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await authApi.register(data)
      await login({ username: data.username, password: data.password })
    } catch (err: any) {
      error.value = err.message || '注册失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Authenticate the current user.
   */
  async function login(data: UserLogin): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await authApi.login(data)
      user.value = await authApi.getMe()
    } catch (err: any) {
      error.value = err.message || '登录失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Sign out.
   */
  function logout(): void {
    authApi.logout()
    user.value = null
    error.value = null
  }

  /**
   * Attempt to restore the session using stored tokens.
   */
  async function initialize(): Promise<void> {
    try {
      user.value = await authApi.getMe()
    } catch {
      authApi.logout()
      user.value = null
    }
  }

  /**
   * Clear any pending auth error.
   */
  function clearError(): void {
    error.value = null
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    register,
    login,
    logout,
    initialize,
    clearError,
  }
})
