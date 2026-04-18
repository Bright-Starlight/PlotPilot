"""Fixtures for API integration tests."""

import pytest
from fastapi.testclient import TestClient
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.sqlite_entity_base_repository import (
    SqliteEntityBaseRepository
)
from infrastructure.persistence.database.sqlite_narrative_event_repository import (
    SqliteNarrativeEventRepository
)

@pytest.fixture
def db(tmp_path):
    """File-backed database fixture for cross-thread FastAPI tests."""
    db_path = tmp_path / "test-api.sqlite3"
    db = DatabaseConnection(str(db_path))
    yield db
    db.close()


@pytest.fixture
def client(db, monkeypatch):
    """FastAPI test client with mocked database."""
    # Mock get_database to return our test database
    def mock_get_database():
        return db

    monkeypatch.setattr(
        "infrastructure.persistence.database.connection.get_database",
        mock_get_database,
    )
    # dependencies 内 `from connection import get_database` 会绑定旧引用，需同步 patch
    monkeypatch.setattr(
        "interfaces.api.dependencies.get_database",
        mock_get_database,
    )
    monkeypatch.setattr(
        "interfaces.api.dependencies.get_story_node_repository",
        lambda: StoryNodeRepository(str(db.db_path)),
    )

    # Import app after monkeypatching
    from interfaces.main import app
    return TestClient(app)


@pytest.fixture
def test_novel_id(db):
    """Create a test novel and return its ID."""
    novel_id = "test-novel-1"
    db.execute(
        "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
        (novel_id, "Test Novel", "test-novel", 10)
    )
    db.get_connection().commit()
    return novel_id


@pytest.fixture
def test_entity_id(db, test_novel_id):
    """Create a test entity and return its ID."""
    entity_id = "test-entity-1"
    core_attributes = {
        "name": "John Doe",
        "age": 30,
        "occupation": "Detective"
    }

    db.execute(
        "INSERT INTO entity_bases (id, novel_id, entity_type, core_attributes) VALUES (?, ?, ?, ?)",
        (entity_id, test_novel_id, "character", str(core_attributes))
    )
    db.get_connection().commit()
    return entity_id
