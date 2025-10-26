/**
 * API service layer that wraps every backend call.
 */

import { apiClient } from './client'
import type {
  UserRegister,
  UserLogin,
  TokenResponse,
  UserInfo,
  SessionCreate,
  SessionUpdate,
  Session,
  SessionDetail,
  ChatRequest,
  SSEEvent,
  FileUploadResponse,
  FileStatusResponse,
  FileImagesResponse,
  FileListResponse,
  ModelsResponse,
} from '@/types/api'

// ==================== Auth API ====================

export const authApi = {
  async register(data: UserRegister): Promise<{ message: string }> {
    return apiClient.post('/auth/register', data)
  },

  async login(data: UserLogin): Promise<TokenResponse> {
    const response = await apiClient.post<TokenResponse>('/auth/login', data)
    apiClient.setTokens(response)
    return response
  },

  async getMe(): Promise<UserInfo> {
    return apiClient.get('/auth/me')
  },

  logout() {
    apiClient.clearTokens()
  },
}

// ==================== Session API ====================

export const sessionsApi = {
  async create(data: SessionCreate): Promise<Session> {
    return apiClient.post('/sessions', data)
  },

  async list(): Promise<Session[]> {
    return apiClient.get('/sessions')
  },

  async get(sessionId: number): Promise<SessionDetail> {
    return apiClient.get(`/sessions/${sessionId}`)
  },

  async update(sessionId: number, data: SessionUpdate): Promise<Session> {
    return apiClient.patch(`/sessions/${sessionId}`, data)
  },

  async delete(sessionId: number): Promise<{ message: string }> {
    return apiClient.delete(`/sessions/${sessionId}`)
  },
}

// ==================== Chat API ====================

export const chatApi = {
  /**
   * Create an SSE stream to consume chat events.
   */
  async *streamChat(request: ChatRequest): AsyncGenerator<SSEEvent, void, unknown> {
    const token = apiClient.getAccessToken()
    if (!token) {
      throw new Error('未登录')
    }

    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('Response body is not readable')
    }

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process SSE messages.
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || '' // Keep the final incomplete chunk.

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6) // Remove the 'data: ' prefix.
            if (data.trim()) {
              try {
                const event: SSEEvent = JSON.parse(data)
                yield event
              } catch (error) {
                console.error('Failed to parse SSE event:', error, data)
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  },
}

// ==================== File API ====================

export const filesApi = {
  async upload(file: File, images?: File[]): Promise<FileUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    // Attach pre-rendered images for PDFs.
    if (images && images.length > 0) {
      images.forEach((img) => {
        formData.append('images', img)
      })
    }

    return apiClient.postFormData('/files/upload', formData)
  },

  async getStatus(fileId: number): Promise<FileStatusResponse> {
    return apiClient.get(`/files/${fileId}/status`)
  },

  async getImages(fileId: number): Promise<FileImagesResponse> {
    return apiClient.get(`/files/${fileId}/images`)
  },

  async list(): Promise<FileListResponse> {
    return apiClient.get('/files')
  },

  async delete(fileId: number): Promise<{ message: string }> {
    return apiClient.delete(`/files/${fileId}`)
  },

  getImageUrl(fileId: number, pageNumber: number): string {
    return `/api/files/${fileId}/images/${pageNumber}`
  },

  getDownloadUrl(fileId: number): string {
    return `/api/files/${fileId}`
  },
}

// ==================== Model API ====================

export const modelsApi = {
  async list(): Promise<ModelsResponse> {
    return apiClient.get('/models')
  },
}
