"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import auth, chat, files, models, sessions
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan hooks.

    Args:
        app: FastAPI application instance.

    Yields:
        None: Control is yielded back to FastAPI to run the app.
    """
    print("🚀 Starting tar agent backend...")
    init_db()
    print("✅ Service started successfully!")
    yield
    print("👋 Shutting down service...")


app = FastAPI(
    title="tar agent backend",
    description="Intelligent agent backend built with FastAPI, SQLite, and OpenAI",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS placeholder (enable if a deployment target needs cross-origin support).

# Register routers.
app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(files.router)
app.include_router(models.router)


@app.get("/")
def read_root():
    """Return service metadata.

    Returns:
        dict: Basic service information for smoke testing.
    """
    return {
        "message": "tar agent backend",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Return a health probe response.

    Returns:
        dict: Status indicator for health checks.
    """
    return {"status": "healthy"}
