from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.schemas.user import UserAdminUpdate, UserCreate, UserResponse
from app.services.audit import log_audit

router = APIRouter(
    prefix="/users",
    tags=["Users (Admin Only)"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.get("", response_model=list[UserResponse], summary="List all system users (ADMIN only)")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    stmt = select(User).offset(skip).limit(limit)
    return db.scalars(stmt).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="Create a new user with role (ADMIN only)")
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {payload.email} already exists",
        )

    new_user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(new_user)
    db.flush()

    # Write audit log
    log_audit(
        db=db,
        user=current_user,
        action="USER_CREATED",
        entity_type="User",
        entity_id=new_user.id,
        old_values=None,
        new_values={
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role.value,
            "is_active": new_user.is_active,
        },
    )

    db.commit()
    db.refresh(new_user)
    return new_user


@router.get("/{user_id}", response_model=UserResponse, summary="Get user by ID (ADMIN only)")
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserResponse, summary="Update role or activate/deactivate user (ADMIN only)")
def update_user(
    user_id: int,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    old_values = {
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
    }

    update_data = payload.model_dump(exclude_unset=True)
    if "full_name" in update_data and update_data["full_name"] is not None:
        user.full_name = update_data["full_name"]
    if "role" in update_data and update_data["role"] is not None:
        user.role = update_data["role"]
    if "is_active" in update_data and update_data["is_active"] is not None:
        user.is_active = update_data["is_active"]

    new_values = {
        "full_name": user.full_name,
        "role": user.role.value,
        "is_active": user.is_active,
    }

    # Determine specific action
    action = "USER_UPDATED"
    if old_values["role"] != new_values["role"]:
        action = "USER_ROLE_CHANGED"
    elif old_values["is_active"] != new_values["is_active"]:
        action = "USER_ACTIVATED" if new_values["is_active"] else "USER_DEACTIVATED"

    log_audit(
        db=db,
        user=current_user,
        action=action,
        entity_type="User",
        entity_id=user.id,
        old_values=old_values,
        new_values=new_values,
    )

    db.commit()
    db.refresh(user)
    return user
