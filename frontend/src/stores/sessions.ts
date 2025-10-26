/**
 * Session state management store.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sessionsApi, modelsApi } from '@/api'
import type { Session, SessionCreate, SessionUpdate, ModelInfo } from '@/types/api'

export const useSessionsStore = defineStore('sessions', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<number | null>(null)
  const models = ref<ModelInfo[]>([])
  const selectedModelId = ref<string>('')
  const loading = ref(false)
  const error = ref<string | null>(null)

  const currentSession = computed(() => {
    if (!currentSessionId.value) return null
    return sessions.value.find((s) => s.id === currentSessionId.value) || null
  })

  const sortedSessions = computed(() => {
    return [...sessions.value].sort((a, b) => {
      return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
    })
  })

  /**
   * Load all sessions.
   */
  async function loadSessions(): Promise<void> {
    loading.value = true
    error.value = null

    try {
      sessions.value = await sessionsApi.list()
    } catch (err: any) {
      error.value = err.message || '加载会话失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a session.
   */
  async function createSession(data: SessionCreate): Promise<Session> {
    loading.value = true
    error.value = null

    try {
      const session = await sessionsApi.create(data)
      sessions.value.unshift(session)
      currentSessionId.value = session.id
      return session
    } catch (err: any) {
      error.value = err.message || '创建会话失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Update a session.
   */
  async function updateSession(sessionId: number, data: SessionUpdate): Promise<Session> {
    loading.value = true
    error.value = null

    try {
      const updatedSession = await sessionsApi.update(sessionId, data)

      const index = sessions.value.findIndex((s) => s.id === sessionId)
      if (index !== -1) {
        sessions.value[index] = updatedSession
      }

      return updatedSession
    } catch (err: any) {
      error.value = err.message || '更新会话失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Delete a session.
   */
  async function deleteSession(sessionId: number): Promise<void> {
    loading.value = true
    error.value = null

    try {
      await sessionsApi.delete(sessionId)
      sessions.value = sessions.value.filter((s) => s.id !== sessionId)

      if (currentSessionId.value === sessionId) {
        currentSessionId.value = null
      }
    } catch (err: any) {
      error.value = err.message || '删除会话失败'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Set the active session.
   */
  function setCurrentSession(sessionId: number | null): void {
    currentSessionId.value = sessionId
  }

  /**
   * Update the session timestamp for ordering.
   */
  function touchSession(sessionId: number): void {
    const session = sessions.value.find((s) => s.id === sessionId)
    if (session) {
      session.updated_at = new Date().toISOString()
    }
  }

  /**
   * Load the available model list.
   */
  async function loadModels(): Promise<void> {
    try {
      const response = await modelsApi.list()
      models.value = response.models
      if (models.value.length > 0) {
        if (!selectedModelId.value || !models.value.find((m) => m.id === selectedModelId.value)) {
          const firstModel = models.value[0]
          if (firstModel) {
            selectedModelId.value = firstModel.id
          }
        }
      }
    } catch (err: any) {
      console.error('Failed to load models:', err)
      models.value = []
    }
  }

  /**
   * Set the chosen model.
   */
  function setSelectedModel(modelId: string): void {
    selectedModelId.value = modelId
  }

  /**
   * Clear the current error.
   */
  function clearError(): void {
    error.value = null
  }

  /**
   * Reset the store (used on logout).
   */
  function reset(): void {
    sessions.value = []
    currentSessionId.value = null
    models.value = []
    selectedModelId.value = ''
    loading.value = false
    error.value = null
  }

  return {
    sessions,
    currentSessionId,
    currentSession,
    sortedSessions,
    models,
    selectedModelId,
    loading,
    error,
    loadSessions,
    createSession,
    updateSession,
    deleteSession,
    setCurrentSession,
    touchSession,
    loadModels,
    setSelectedModel,
    clearError,
    reset,
  }
})
