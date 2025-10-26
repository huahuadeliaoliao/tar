/**
 * HTTP client wrapper that centralizes auth and error handling.
 */

import { jwtDecode } from 'jwt-decode'
import type { TokenResponse } from '@/types/api'

interface JWTPayload {
  exp: number
  sub: string
  username: string
  type: 'access' | 'refresh'
}

class ApiClient {
  private baseURL = '/api'
  private accessToken: string | null = null
  private refreshToken: string | null = null
  private refreshTimer: number | null = null
  private isRefreshing = false

  constructor() {
    // Restore persisted tokens.
    this.accessToken = localStorage.getItem('access_token')
    this.refreshToken = localStorage.getItem('refresh_token')

    // Start the auto-refresh timer.
    this.startAutoRefresh()
  }

  setTokens(tokens: TokenResponse) {
    this.accessToken = tokens.access_token
    if (tokens.refresh_token) {
      this.refreshToken = tokens.refresh_token
    }

    // Persist tokens for subsequent sessions.
    localStorage.setItem('access_token', tokens.access_token)
    if (tokens.refresh_token) {
      localStorage.setItem('refresh_token', tokens.refresh_token)
    }

    // Restart the refresh timer.
    this.startAutoRefresh()
  }

  clearTokens() {
    this.accessToken = null
    this.refreshToken = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')

    // Stop any pending refresh timers.
    this.stopAutoRefresh()
  }

  getAccessToken() {
    return this.accessToken
  }

  getRefreshToken() {
    return this.refreshToken
  }

  async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    }

    // Attach the bearer token when needed.
    if (this.accessToken && !url.includes('/auth/login') && !url.includes('/auth/register')) {
      headers['Authorization'] = `Bearer ${this.accessToken}`
    }

    try {
      const response = await fetch(`${this.baseURL}${url}`, {
        ...options,
        headers,
      })

      // Attempt to refresh expired tokens on 401 responses.
      if (response.status === 401 && this.refreshToken && !url.includes('/auth/refresh')) {
        const refreshed = await this.refreshAccessToken()
        if (refreshed) {
          // Retry the original request.
          if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`
          }
          const retryResponse = await fetch(`${this.baseURL}${url}`, {
            ...options,
            headers,
          })

          if (!retryResponse.ok) {
            throw new Error(`HTTP error! status: ${retryResponse.status}`)
          }

          return retryResponse.json()
        } else {
          // Refresh failed; clear tokens and bail.
          this.clearTokens()
          throw new Error('认证已过期，请重新登录')
        }
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
      }

      return response.json()
    } catch (error) {
      console.error('API request failed:', error)
      throw error
    }
  }

  async get<T>(url: string): Promise<T> {
    return this.request<T>(url, { method: 'GET' })
  }

  async post<T>(url: string, data?: any): Promise<T> {
    return this.request<T>(url, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async patch<T>(url: string, data?: any): Promise<T> {
    return this.request<T>(url, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  async delete<T>(url: string): Promise<T> {
    return this.request<T>(url, { method: 'DELETE' })
  }

  async postFormData<T>(url: string, formData: FormData): Promise<T> {
    const headers: HeadersInit = {}

    // Attach the bearer token when needed.
    if (this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`
    }

    const response = await fetch(`${this.baseURL}${url}`, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || `HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (!this.refreshToken || this.isRefreshing) return false

    this.isRefreshing = true

    try {
      const response = await fetch(`${this.baseURL}/auth/refresh`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${this.refreshToken}`,
          'Content-Type': 'application/json',
        },
      })

      if (!response.ok) {
        this.isRefreshing = false
        return false
      }

      const data: TokenResponse = await response.json()
      this.accessToken = data.access_token
      localStorage.setItem('access_token', data.access_token)

      // Restart the refresh timer.
      this.startAutoRefresh()

      this.isRefreshing = false
      return true
    } catch (error) {
      console.error('Failed to refresh token:', error)
      this.isRefreshing = false
      return false
    }
  }

  /**
   * Decode the token to determine its expiration time.
   */
  private getTokenExpiry(token: string): number | null {
    try {
      const decoded = jwtDecode<JWTPayload>(token)
      return decoded.exp
    } catch (error) {
      console.error('Failed to decode token:', error)
      return null
    }
  }

  /**
   * Check whether a token expires within the provided buffer (default 5 minutes).
   */
  private isTokenExpiringSoon(token: string, bufferMinutes = 5): boolean {
    const expiry = this.getTokenExpiry(token)
    if (!expiry) return true

    const now = Math.floor(Date.now() / 1000)
    const bufferSeconds = bufferMinutes * 60
    return expiry - now < bufferSeconds
  }

  /**
   * Start the auto-refresh timer.
   */
  private startAutoRefresh() {
    // Clear any existing timer first.
    this.stopAutoRefresh()

    if (!this.accessToken || !this.refreshToken) return

    const expiry = this.getTokenExpiry(this.accessToken)
    if (!expiry) return

    const now = Math.floor(Date.now() / 1000)
    const timeUntilExpiry = expiry - now

    // Refresh five minutes before expiry (or immediately if overdue).
    const refreshIn = Math.max(0, timeUntilExpiry - 5 * 60)

    console.log(`Token will be refreshed in ${Math.floor(refreshIn / 60)} minutes`)

    this.refreshTimer = window.setTimeout(async () => {
      console.log('Auto-refreshing access token...')
      const success = await this.refreshAccessToken()
      if (!success) {
        console.error('Auto-refresh failed, clearing tokens')
        this.clearTokens()
      }
    }, refreshIn * 1000)
  }

  /**
   * Stop the auto-refresh timer.
   */
  private stopAutoRefresh() {
    if (this.refreshTimer !== null) {
      clearTimeout(this.refreshTimer)
      this.refreshTimer = null
    }
  }
}

export const apiClient = new ApiClient()
