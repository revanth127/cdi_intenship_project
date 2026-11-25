from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)
except ImportError:
    import bcrypt

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

    def get_password_hash(password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

try:
    from jose import JWTError, jwt
except ImportError:
    import jwt  # type: ignore

    class JWTError(Exception):  # type: ignore
        pass

from app.core.config import settings
from app.models.user import UserRole


def create_access_token(
    subject: Union[str, int],
    role: Union[UserRole, str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed JWT access token containing subject (user ID) and role claim.
    Default expiry: settings.ACCESS_TOKEN_EXPIRE_MINUTES (e.g. 24 hours / 1440 mins).
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    role_val = role.value if isinstance(role, UserRole) else str(role)

    to_encode = {
        "sub": str(subject),
        "role": role_val,
        "type": "access",
        "iat": now,
        "exp": expire,
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def create_refresh_token(
    subject: Union[str, int],
    role: Union[UserRole, str],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Generate a signed JWT refresh token with a longer lifespan (default 7 days).
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=7)

    role_val = role.value if isinstance(role, UserRole) else str(role)

    to_encode = {
        "sub": str(subject),
        "role": role_val,
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access or refresh token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except Exception as e:
        raise ValueError("Invalid or expired token") from e
