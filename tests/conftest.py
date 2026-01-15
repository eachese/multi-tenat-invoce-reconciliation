"""Shared pytest fixtures for Flow RMS tests."""
from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import get_db_session
from app.db.base import Base
from app.db.models import Tenant
from app.main import create_app


@pytest.fixture()
def engine() -> Generator:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    SessionLocal = sessionmaker(bind=engine, class_=Session, autoflush=False, autocommit=False)
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()


@pytest.fixture()
def tenant(session: Session) -> Tenant:
    tenant = Tenant(name="Test Tenant")
    session.add(tenant)
    session.commit()
    session.refresh(tenant)
    return tenant


@pytest.fixture()
def client(session: Session) -> Generator[TestClient, None, None]:
    application = create_app()

    def override_get_db_session() -> Generator[Session, None, None]:
        try:
            yield session
        finally:
            session.rollback()

    application.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(application) as test_client:
        yield test_client

    application.dependency_overrides.clear()
