import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai.llm_service import LLMService
from app.api.dependencies.llm import set_llm_service_override
from app.db.base import Base
from app.db.database import get_db
from app.db.database import enable_sqlite_foreign_keys
from app.db import models  # noqa: F401 — populate Base.metadata
from app.main import app


class FakeLLMService(LLMService):
    """Deterministic stand-in for Ollama so tests never require a real LLM server."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        if "intent" in system.lower():
            return '{"intent": "FREEFORM", "target": null}'
        return "[test narration]"


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session: Session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def fake_llm():
    return FakeLLMService()


@pytest.fixture()
def client(db_session, fake_llm):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    set_llm_service_override(fake_llm)

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    set_llm_service_override(None)
