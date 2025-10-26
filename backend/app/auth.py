"""JWT authentication helpers."""

from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import config

# Password hashing context.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check whether a plaintext password matches a stored hash.

    Args:
        plain_password: The password provided by the user.
        hashed_password: The persisted bcrypt hash.

    Returns:
        bool: True when the plaintext password matches the hash; otherwise
        False.
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash for a plaintext password.

    Args:
        password: The password to hash.

    Returns:
        str: The generated bcrypt hash.
    """
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed access token.

    Args:
        data: Payload to encode inside the JWT.
        expires_delta: Optional override for the expiration window.

    Returns:
        str: The encoded JWT string identifying an access token.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create a signed refresh token.

    Args:
        data: Payload to encode inside the JWT.

    Returns:
        str: The encoded JWT string identifying a refresh token.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT.

    Args:
        token: Encoded access or refresh token.

    Returns:
        Optional[dict]: The decoded payload when verification succeeds, or
        None otherwise.
    """
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_token_type(payload: dict, expected_type: str) -> bool:
    """Check whether a decoded payload matches the expected token type.

    Args:
        payload: The decoded JWT payload.
        expected_type: Either `"access"` or `"refresh"`.

    Returns:
        bool: True when the payload type matches the expectation.
    """
    return payload.get("type") == expected_type
