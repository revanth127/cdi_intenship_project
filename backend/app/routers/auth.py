from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    verify_password,
)
from app.models.user import User
from app.schemas.token import RefreshTokenRequest, Token
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token, summary="OAuth2 password login returning JWT access and refresh tokens")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Validates user credentials (username is user email).
    Rejects inactive users and returns a generic 401 on authentication failure.
    Compatible with OpenAPI Swagger UI Authorize dialog.
    """
    user = db.scalar(select(User).where(User.email == form_data.username.strip().lower()))

    # Verify password against hash
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated. Contact an administrator.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(subject=user.id, role=user.role)
    refresh_token = create_refresh_token(subject=user.id, role=user.role)

    return Token(
        access_token=access_token,
        token_type="bearer",
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse, summary="Get current authenticated user profile")
def read_current_user(current_user: User = Depends(get_current_user)):
    """Returns the authenticated user's details and active role."""
    return current_user


@router.post("/refresh", response_model=Token, summary="Exchange valid refresh token for a new access token")
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    """
    Validates refresh token claim and issues a fresh access token.
    Tradeoff: Stateless tokens require no DB lookup for token state, but cannot be
    server-revoked before expiry without a blacklist table.
    """
    try:
        token_data = decode_access_token(payload.refresh_token)
        if token_data.get("type") != "refresh":
            raise ValueError("Token is not a refresh token")
        user_id = int(token_data["sub"])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    new_access_token = create_access_token(subject=user.id, role=user.role)
    return Token(
        access_token=new_access_token,
        token_type="bearer",
        refresh_token=payload.refresh_token,
        user=UserResponse.model_validate(user),
    )
