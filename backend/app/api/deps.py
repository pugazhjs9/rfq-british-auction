from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.clock import Clock, DbClock
from app.db import get_session
from app.errors import Unauthorized
from app.models import User
from app.realtime import Publisher, publisher

_db_clock = DbClock()


def get_clock() -> Clock:
    return _db_clock


def get_publisher() -> Publisher:
    return publisher


def get_viewer(
    x_user_id: int | None = Header(default=None), session: Session = Depends(get_session)
) -> User | None:
    """Authentication is mocked: the client says who it is acting as.

    A real deployment would read the user from a verified token instead.
    Reads work without a user, but then show no supplier names.
    """
    if x_user_id is None:
        return None
    user = session.get(User, x_user_id)
    if user is None:
        raise Unauthorized(f"No user with id {x_user_id}")
    return user


def get_current_user(user: User | None = Depends(get_viewer)) -> User:
    if user is None:
        raise Unauthorized("Choose a user to act as (send the X-User-Id header)")
    return user
