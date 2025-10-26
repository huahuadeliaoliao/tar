"""Authentication endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, create_refresh_token, get_password_hash, verify_password
from app.config import config
from app.database import get_db
from app.dependencies import get_current_user, verify_refresh_token
from app.models import User
from app.schemas import TokenResponse, UserLogin, UserRegister, UserResponse

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user after validating the shared token.

    Args:
        user_data: Submitted registration payload containing username, password,
            and the shared registration token.
        db: Database session injected by FastAPI.

    Returns:
        dict: Confirmation message upon successful registration.

    Raises:
        HTTPException: Raised when the registration token is invalid or the
        username already exists.
    """
    # Verify registration token.
    if user_data.registration_token != config.REGISTRATION_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid registration token")

    # Ensure the username is available.
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    # Persist the user.
    hashed_password = get_password_hash(user_data.password)
    new_user = User(username=user_data.username, hashed_password=hashed_password)

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User created successfully"}


@router.post("/login", response_model=TokenResponse)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate a user and issue access/refresh tokens.

    Args:
        user_data: Submitted credentials.
        db: Database session injected by FastAPI.

    Returns:
        TokenResponse: Newly minted access and refresh tokens.

    Raises:
        HTTPException: Raised when the username does not exist or the password
        is invalid.
    """
    # Lookup the user.
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    # Validate password.
    if not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    # Issue tokens (sub must be a string).
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(user: User = Depends(verify_refresh_token)):
    """Issue a new access token based on a valid refresh token.

    Args:
        user: The authenticated user resolved from the refresh token.

    Returns:
        TokenResponse: A response containing the new access token.
    """
    token_data = {"sub": str(user.id), "username": user.username}
    access_token = create_access_token(token_data)

    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    """Return the authenticated user.

    Args:
        user: The user resolved from the access token.

    Returns:
        User: The authenticated user record.
    """
    return user
