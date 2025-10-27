/**
 * Backend API type definitions.
 */

// ==================== Authentication ====================

export interface UserRegister {
  username: string
  password: string
  registration_token: string
}

export interface UserLogin {
  username: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token?: string
  token_type: string
}

export interface UserInfo {
  id: number
  username: string
  created_at: string
}

// ==================== Sessions ====================

export interface SessionCreate {
  title?: string
  model_id: string
}

export interface SessionUpdate {
  title?: string
  model_id?: string
}

export interface Session {
  id: number
  title: string | null
  model_id: string
  created_at: string
  updated_at: string
}

export interface ApiMessage {
  id: number
  role: string
  content: string | null
  tool_call_id: string | null
  tool_name: string | null
  tool_input: string | null
  tool_output: string | null
  sequence: number
  model_id: string | null
  created_at: string
}

export interface SessionDetail {
  session: Session
  messages: ApiMessage[]
}

// ==================== Chat ====================

export interface ChatRequest {
  session_id: number
  message: string
  model_id?: string
  files?: number[]
}

// SSE event types.
export interface BaseSSEEvent {
  type: string
  timestamp: number
}

export interface StatusEvent extends BaseSSEEvent {
  type: 'status'
  status:
    | 'processing'
    | 'thinking'
    | 'tool_calling'
    | 'generating'
    | 'completed'
    | 'awaiting_more_actions'
  message: string
}

export interface ThinkingEvent extends BaseSSEEvent {
  type: 'thinking'
  message: string
}

export interface ToolCallEvent extends BaseSSEEvent {
  type: 'tool_call'
  tool_call_id: string
  tool_name: string
  tool_input: Record<string, any>
}

export interface ToolExecutingEvent extends BaseSSEEvent {
  type: 'tool_executing'
  tool_call_id: string
  tool_name: string
  message: string
}

export interface ToolResultEvent extends BaseSSEEvent {
  type: 'tool_result'
  tool_call_id: string
  tool_name: string
  tool_output: Record<string, any>
  success: boolean
}

export interface ContentStartEvent extends BaseSSEEvent {
  type: 'content_start'
  message: string
  guarded?: boolean
}

export interface ContentDeltaEvent extends BaseSSEEvent {
  type: 'content_delta'
  delta: string
  guarded?: boolean
}

export interface ContentDoneEvent extends BaseSSEEvent {
  type: 'content_done'
  full_content: string
  guarded?: boolean
}

export interface IterationInfoEvent extends BaseSSEEvent {
  type: 'iteration_info'
  current_iteration: number
  max_iterations: number
  message: string
}

export interface RetryEvent extends BaseSSEEvent {
  type: 'retry'
  reason: string
  retry_count: number
  max_retries: number
  message: string
}

export interface ErrorEvent extends BaseSSEEvent {
  type: 'error'
  error_code: string
  error_message: string
  details?: Record<string, any>
}

export interface DoneEvent extends BaseSSEEvent {
  type: 'done'
  message_id: number
  session_id: number
  total_iterations: number
  total_time_ms: number
}

export type SSEEvent =
  | StatusEvent
  | ThinkingEvent
  | ToolCallEvent
  | ToolExecutingEvent
  | ToolResultEvent
  | ContentStartEvent
  | ContentDeltaEvent
  | ContentDoneEvent
  | IterationInfoEvent
  | RetryEvent
  | ErrorEvent
  | DoneEvent

// ==================== Files ====================

export interface FileUploadResponse {
  file_id: number
  filename: string
  file_type: string
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  image_count?: number
}

export interface FileStatusResponse {
  file_id: number
  processing_status: 'pending' | 'processing' | 'completed' | 'failed'
  image_count?: number
  error_message?: string
}

export interface FileImageInfo {
  page: number
  image_id: number
  width: number
  height: number
  image_data_base64?: string
}

export interface FileImagesResponse {
  file_id: number
  images: FileImageInfo[]
}

export interface FileListItem {
  id: number
  filename: string
  file_type: string
  file_size: number
  processing_status: string
  created_at: string
}

export interface FileListResponse {
  files: FileListItem[]
}

// ==================== Models ====================

export interface ModelInfo {
  id: string
  name: string
  supports_vision: boolean
}

export interface ModelsResponse {
  models: ModelInfo[]
}
