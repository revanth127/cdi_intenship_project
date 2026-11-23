from typing import Generic, TypeVar
from sqlalchemy.orm import Session
from app.core.db import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseService(Generic[ModelType]):
    """
    Base service class to keep FastAPI routers thin.
    All business logic must reside within service classes.
    """
    def __init__(self, db: Session):
        self.db = db
