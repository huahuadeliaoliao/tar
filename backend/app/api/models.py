"""Model metadata endpoints."""

from fastapi import APIRouter, Depends

from app.config import config
from app.dependencies import get_current_user
from app.schemas import ModelInfo, ModelsResponse

router = APIRouter(prefix="/api/models", tags=["Models"])


@router.get("", response_model=ModelsResponse)
def list_models(user=Depends(get_current_user)):
    """Return the configured list of available models.

    Args:
        user: Authenticated user. The value is unused but required for auth.

    Returns:
        ModelsResponse: Wrapper containing model metadata entries.
    """
    models = [ModelInfo(**model) for model in config.AVAILABLE_MODELS]
    return ModelsResponse(models=models)
