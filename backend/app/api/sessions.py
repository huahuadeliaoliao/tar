"""Session management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Message, User
from app.models import Session as SessionModel
from app.schemas import MessageResponse, SessionCreate, SessionDetailResponse, SessionResponse, SessionUpdate

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(session_data: SessionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a new session for the authenticated user.

    Args:
        session_data: Title and default model for the new session.
        user: Authenticated user resolved from the access token.
        db: Database session injected by FastAPI.

    Returns:
        SessionResponse: The persisted session object.
    """
    new_session = SessionModel(user_id=user.id, title=session_data.title, model_id=session_data.model_id)

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return new_session


@router.get("", response_model=List[SessionResponse])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return all sessions owned by the user.

    Args:
        user: Authenticated user whose sessions should be listed.
        db: Database session injected by FastAPI.

    Returns:
        List[SessionResponse]: Sessions sorted by last update time.
    """
    sessions = (
        db.query(SessionModel).filter(SessionModel.user_id == user.id).order_by(SessionModel.updated_at.desc()).all()
    )

    return sessions


@router.get("/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return a session plus its messages.

    Args:
        session_id: Identifier of the requested session.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        SessionDetailResponse: The session metadata and ordered message list.

    Raises:
        HTTPException: When the session does not exist or is not owned by the
        user.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id, SessionModel.user_id == user.id).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    messages = db.query(Message).filter(Message.session_id == session_id).order_by(Message.sequence).all()

    message_responses = [MessageResponse.model_validate(msg) for msg in messages]

    return SessionDetailResponse(session=session, messages=message_responses)


@router.patch("/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: int, session_data: SessionUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Update mutable session fields such as title or model.

    Args:
        session_id: Identifier of the session to update.
        session_data: Payload containing optional updates.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        SessionResponse: The updated session.

    Raises:
        HTTPException: When the session does not exist or is not owned by the
        user.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id, SessionModel.user_id == user.id).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session_data.title is not None:
        session.title = session_data.title

    if session_data.model_id is not None:
        session.model_id = session_data.model_id

    db.commit()
    db.refresh(session)

    return session


@router.delete("/{session_id}", response_model=dict)
def delete_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete a session and cascade delete its messages.

    Args:
        session_id: Identifier of the session to delete.
        user: Authenticated user, used to verify ownership.
        db: Database session injected by FastAPI.

    Returns:
        dict: Confirmation message.

    Raises:
        HTTPException: When the session does not exist or is not owned by the
        user.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id, SessionModel.user_id == user.id).first()

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    db.delete(session)
    db.commit()

    return {"message": "Session deleted"}
