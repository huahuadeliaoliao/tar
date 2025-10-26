"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """User table."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships.
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    files = relationship("File", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """Chat session table."""

    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    model_id = Column(String(100), nullable=False)  # Model used for this session.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships.
    user = relationship("User", back_populates="sessions")
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Message table storing the full conversation history."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user/assistant/tool.
    content = Column(Text, nullable=True)  # JSON payload for text/image/file references.
    tool_call_id = Column(String(100), nullable=True)  # Present when the assistant invoked a tool.
    tool_name = Column(String(100), nullable=True)
    tool_input = Column(Text, nullable=True)  # JSON
    tool_output = Column(Text, nullable=True)  # JSON
    sequence = Column(Integer, nullable=False)  # Message order.
    model_id = Column(String(100), nullable=True)  # Model used to produce an assistant response.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships.
    session = relationship("Session", back_populates="messages")


class File(Base):
    """Uploaded files along with metadata and binary content."""

    __tablename__ = "files"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)  # image/pdf/docx/ppt.
    mime_type = Column(String(100), nullable=False)
    file_data = Column(LargeBinary, nullable=False)  # Raw binary payload.
    file_size = Column(Integer, nullable=False)
    processing_status = Column(String(20), default="pending", nullable=False)  # pending/processing/completed/failed.
    error_message = Column(Text, nullable=True)  # Optional processing error message.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships.
    user = relationship("User", back_populates="files")
    images = relationship("FileImage", back_populates="file", cascade="all, delete-orphan")


class FileImage(Base):
    """Derivative images produced from uploaded files."""

    __tablename__ = "file_images"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)  # One-based page index.
    image_data = Column(LargeBinary, nullable=False)  # Compressed WebP image.
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    file_size = Column(Integer, nullable=False)  # Image size in bytes.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships.
    file = relationship("File", back_populates="images")
