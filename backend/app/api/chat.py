"""Chat streaming endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Session as SessionModel
from app.models import User
from app.schemas import ChatRequest
from app.services.agent import run_agent_loop

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/stream")
async def chat_stream(request: ChatRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stream chat responses over Server-Sent Events with optional tool calls.

    Args:
        request: Incoming chat payload containing message content, session ID,
            and optional tools/files.
        user: The authenticated user who owns the session.
        db: Database session injected by FastAPI.

    Returns:
        StreamingResponse: SSE stream emitting events produced by the agent.

    Raises:
        HTTPException: Raised when the session does not belong to the user or
        cannot be found.
    """
    # Ensure the session belongs to the user.
    session = (
        db.query(SessionModel).filter(SessionModel.id == request.session_id, SessionModel.user_id == user.id).first()
    )

    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    # Prefer the requested model, otherwise fall back to the session default.
    model_id = request.model_id if request.model_id else session.model_id

    # Run the agent loop and emit events.
    async def event_generator():
        try:
            async for event in run_agent_loop(
                session_id=request.session_id,
                user_message=request.message,
                model_id=model_id,
                files=request.files,
                db=db,
            ):
                yield event
        except Exception as e:
            # Emit an error event.
            import json

            from app.utils.helpers import get_timestamp

            error_event = f"data: {json.dumps({'type': 'error', 'error_code': 'INTERNAL_ERROR', 'error_message': str(e), 'timestamp': get_timestamp()}, ensure_ascii=False)}\n\n"
            yield error_event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering.
        },
    )
