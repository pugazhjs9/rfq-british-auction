from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def make_engine(url: str, **kwargs):
    # Every connection talks UTC so timestamps come back in one zone.
    return create_engine(
        url, pool_pre_ping=True, connect_args={"options": "-c timezone=utc"}, **kwargs
    )


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
