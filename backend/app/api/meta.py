from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_clock
from app.clock import Clock
from app.db import get_session
from app.models import User
from app.schemas import ServerTimeOut, UserOut

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/time", response_model=ServerTimeOut)
def server_time(session: Session = Depends(get_session), clock: Clock = Depends(get_clock)):
    """Lets the browser correct for its own clock drift when showing countdowns."""
    return ServerTimeOut(now=clock.now(session))


@router.get("/users", response_model=list[UserOut])
def list_users(session: Session = Depends(get_session)):
    return session.scalars(select(User).order_by(User.role, User.id)).all()
