from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session


class Clock(Protocol):
    def now(self, session: Session) -> datetime: ...


class DbClock:
    """Reads Postgres `clock_timestamp()`, giving every API replica and worker one shared clock.

    `now()` would be wrong here: Postgres freezes it at the start of the
    transaction, so a request that waited on a row lock would see a stale time.
    """

    def now(self, session: Session) -> datetime:
        return session.scalar(select(func.clock_timestamp()))


class FrozenClock:
    """A clock you move by hand. Used by tests and by the seed script to replay history."""

    def __init__(self, at: datetime):
        self.at = at

    def now(self, session: Session | None = None) -> datetime:
        return self.at

    def set(self, at: datetime) -> None:
        self.at = at

    def advance(self, **delta: float) -> None:
        self.at += timedelta(**delta)
