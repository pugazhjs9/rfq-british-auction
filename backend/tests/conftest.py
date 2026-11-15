"""Fixtures for tests that need Postgres (docker compose up -d db).

Each session gets a fresh `auction_test` database built by running the real
Alembic migrations, so the migrations are tested too.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_clock, get_publisher
from app.clock import FrozenClock
from app.db import get_session, make_engine
from app.main import app
from app.models import User, UserRole

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://auction:auction@localhost:5433/auction_test"
)
BACKEND_DIR = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def engine():
    url = make_url(TEST_DATABASE_URL)
    admin = make_engine(
        url.set(database="postgres").render_as_string(hide_password=False),
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")

    engine = make_engine(TEST_DATABASE_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine) -> Iterator[sessionmaker]:
    yield sessionmaker(engine, expire_on_commit=False)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE auction_events, bids, rfqs, users RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE rfq_reference_seq RESTART"))


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


class RecordingPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, rfq_id, events, current_close_at):
        self.messages.append((rfq_id, events, current_close_at))


@pytest.fixture
def publisher() -> RecordingPublisher:
    return RecordingPublisher()


@pytest.fixture
def users(session_factory) -> dict[str, User]:
    people = {
        "buyer": User(name="Ananya Rao", company="Indigo Retail", role=UserRole.BUYER),
        "kestrel": User(name="Arjun Mehta", company="Kestrel", role=UserRole.SUPPLIER),
        "saffron": User(name="Priya Nair", company="Saffron", role=UserRole.SUPPLIER),
        "monsoon": User(name="Rohan Das", company="Monsoon", role=UserRole.SUPPLIER),
        "northstar": User(name="Meera Iyer", company="Northstar", role=UserRole.SUPPLIER),
    }
    with session_factory() as session:
        session.add_all(people.values())
        session.commit()
    return people


@pytest.fixture
def client(session_factory, clock, publisher) -> Iterator[TestClient]:
    def session_override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_publisher] = lambda: publisher
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
