/**
 * AI chat type definitions.
 */

export interface BaseMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  timestamp: number
  status?: 'pending' | 'streaming' | 'done' | 'error'
}

/**
 * Processing state for step indicators.
 */
export interface ProcessingState {
  step: 'file_processing' | 'thinking'
  status: 'in_progress' | 'completed' | 'error'
  startTime: number
  endTime?: number
  errorMessage?: string
}

export interface UserMessage extends BaseMessage {
  role: 'user'
  content: string
  files?: FileAttachment[]
}

export interface AssistantMessage extends BaseMessage {
  role: 'assistant'
  content: string
  parts: MessagePart[]
  processingStates?: ProcessingState[]
  metadata?: {
    model_id?: string
    total_time_ms?: number
    iterations?: number
  }
}

export type Message = UserMessage | AssistantMessage

export type MessagePart = ThinkingPart | TextPart | ToolCallPart | ErrorPart

export interface ThinkingPart {
  type: 'thinking'
  message: string
  timestamp: number
}

export interface TextPart {
  type: 'text'
  content: string
}

export interface ToolCallPart {
  type: 'tool_call'
  id: string
  name: string
  input: Record<string, any>
  output?: Record<string, any>
  status: 'calling' | 'executing' | 'success' | 'error'
  success?: boolean
  timestamp: number
}

export interface ErrorPart {
  type: 'error'
  code: string
  message: string
  timestamp: number
}

export interface FileAttachment {
  id: number
  name: string
  type: 'image' | 'pdf' | 'docx' | 'pptx'
  mimeType: string
  size: number
  url?: string // Used to display image previews.
}
