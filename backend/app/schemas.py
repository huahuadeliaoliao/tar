"""Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ==================== Users ====================


class UserRegister(BaseModel):
    """Request body for user registration."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    registration_token: str


class UserLogin(BaseModel):
    """Request body for user login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response containing access and optional refresh tokens."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Serialized user information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    created_at: datetime


# ==================== Sessions ====================


class SessionCreate(BaseModel):
    """Payload for creating a new session."""

    title: Optional[str] = None
    model_id: str = Field(..., description="Model identifier used for the session.")


class SessionUpdate(BaseModel):
    """Payload for updating mutable session fields."""

    title: Optional[str] = Field(None, description="Session title.")
    model_id: Optional[str] = Field(None, description="Model identifier used for the session.")


class SessionResponse(BaseModel):
    """Session metadata returned to clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: Optional[str]
    model_id: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    """Chat message representation with optional tool data."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: Optional[str]
    tool_call_id: Optional[str]
    tool_name: Optional[str]
    tool_input: Optional[str]
    tool_output: Optional[str]
    sequence: int
    model_id: Optional[str]  # Model that produced the assistant response.
    created_at: datetime


class SessionDetailResponse(BaseModel):
    """Session metadata along with its ordered messages."""

    session: SessionResponse
    messages: List[MessageResponse]


# ==================== Files ====================


class FileUploadResponse(BaseModel):
    """Response describing an uploaded file."""

    file_id: int
    filename: str
    file_type: str
    processing_status: str
    image_count: Optional[int] = None


class FileStatusResponse(BaseModel):
    """Processing status for a stored file."""

    file_id: int
    processing_status: str
    image_count: Optional[int] = None
    error_message: Optional[str] = None


class FileImageInfo(BaseModel):
    """Metadata for a single image derived from a document."""

    page: int
    image_id: int
    width: int
    height: int
    image_data_base64: Optional[str] = None  # Base64-encoded image payload.


class FileImagesResponse(BaseModel):
    """Response containing all image derivatives for a file."""

    file_id: int
    images: List[FileImageInfo]


class FileListItem(BaseModel):
    """Summary of a file used in listing responses."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    file_size: int
    processing_status: str
    created_at: datetime


class FileListResponse(BaseModel):
    """Collection of files owned by a user."""

    files: List[FileListItem]


# ==================== Chat ====================


class ChatRequest(BaseModel):
    """Request payload for streaming chat interactions."""

    session_id: int
    message: str = Field(..., min_length=1)
    model_id: Optional[str] = Field(None, description="Optional override for the session model.")
    files: Optional[List[int]] = Field(default_factory=list)


# ==================== Models ====================


class ModelInfo(BaseModel):
    """Metadata describing an available model."""

    id: str
    name: str
    supports_vision: bool


class ModelsResponse(BaseModel):
    """Response containing all configured models."""

    models: List[ModelInfo]


# ==================== SSE events ====================


class SSEEvent(BaseModel):
    """Base schema for Server-Sent Event payloads."""

    type: str
    timestamp: int


class StatusEvent(SSEEvent):
    """Status update event."""

    status: str
    message: str


class ThinkingEvent(SSEEvent):
    """Event emitted while the agent is thinking."""

    message: str


class ToolCallEvent(SSEEvent):
    """Event describing a tool call request."""

    tool_call_id: str
    tool_name: str
    tool_input: Dict[str, Any]


class ToolExecutingEvent(SSEEvent):
    """Event indicating a tool is currently executing."""

    tool_call_id: str
    tool_name: str
    message: str


class ToolResultEvent(SSEEvent):
    """Event capturing the result of a tool invocation."""

    tool_call_id: str
    tool_name: str
    tool_output: Dict[str, Any]
    success: bool


class ContentStartEvent(SSEEvent):
    """Event fired before the assistant begins streaming content."""

    message: str


class ContentDeltaEvent(SSEEvent):
    """Event containing a content delta chunk."""

    delta: str


class ContentDoneEvent(SSEEvent):
    """Event emitted when all content has been generated."""

    full_content: str


class IterationInfoEvent(SSEEvent):
    """Event conveying iteration statistics."""

    current_iteration: int
    max_iterations: int
    message: str


class RetryEvent(SSEEvent):
    """Event emitted when the agent retries a tool call."""

    reason: str
    retry_count: int
    max_retries: int
    message: str


class ErrorEvent(SSEEvent):
    """Event describing an error encountered during execution."""

    error_code: str
    error_message: str
    details: Optional[Dict[str, Any]] = None


class DoneEvent(SSEEvent):
    """Event signaling that the run loop has finished."""

    message_id: int
    session_id: int
    total_iterations: int
    total_time_ms: int
