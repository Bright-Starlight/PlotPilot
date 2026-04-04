"""Cast API integration tests"""
import pytest
from fastapi.testclient import TestClient
import shutil
from pathlib import Path
from infrastructure.persistence.storage.file_storage import FileStorage
from infrastructure.persistence.repositories.file_novel_repository import FileNovelRepository
from infrastructure.persistence.repositories.file_chapter_repository import FileChapterRepository
from application.services.novel_service import NovelService
from application.services.cast_service import CastService
from interfaces.api.dependencies import get_novel_service, get_cast_service
from interfaces.main import app


# Global variables to hold test services
_test_novel_service = None
_test_cast_service = None


def get_test_novel_service():
    """Get test novel service"""
    return _test_novel_service


def get_test_cast_service():
    """Get test cast service"""
    return _test_cast_service


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """Setup test environment"""
    global _test_novel_service, _test_cast_service

    test_data = tmp_path / "data"
    test_data.mkdir()

    # Create test storage and repositories
    storage = FileStorage(test_data)
    novel_repo = FileNovelRepository(storage)
    chapter_repo = FileChapterRepository(storage)
    # Create services
    _test_novel_service = NovelService(novel_repo, chapter_repo)
    _test_cast_service = CastService(test_data)

    # Override dependencies
    app.dependency_overrides[get_novel_service] = get_test_novel_service
    app.dependency_overrides[get_cast_service] = get_test_cast_service

    yield

    # Cleanup
    app.dependency_overrides.clear()
    _test_novel_service = None
    _test_cast_service = None
    if test_data.exists():
        shutil.rmtree(test_data)


client = TestClient(app)


@pytest.fixture
def test_novel():
    """Create test novel"""
    response = client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-cast",
        "title": "测试小说",
        "author": "测试作者",
        "target_chapters": 10
    })
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def test_cast_graph(test_novel):
    """Create test cast graph"""
    response = client.put("/api/v1/novels/test-novel-cast/cast", json={
        "version": 2,
        "characters": [
            {
                "id": "char1",
                "name": "张三",
                "aliases": ["小张"],
                "role": "主角",
                "traits": "勇敢",
                "note": "主角备注",
                "story_events": [
                    {
                        "id": "ev1",
                        "summary": "出场",
                        "chapter_id": 1,
                        "importance": "key"
                    }
                ]
            },
            {
                "id": "char2",
                "name": "李四",
                "aliases": [],
                "role": "配角",
                "traits": "聪明",
                "note": "",
                "story_events": []
            }
        ],
        "relationships": [
            {
                "id": "rel1",
                "source_id": "char1",
                "target_id": "char2",
                "label": "朋友",
                "note": "好朋友",
                "directed": False,
                "story_events": []
            }
        ]
    })
    assert response.status_code == 200
    return response.json()


class TestGetCastGraph:
    """Test get cast graph endpoint"""

    def test_get_cast_graph_success(self, test_cast_graph):
        """Test successfully getting cast graph"""
        response = client.get("/api/v1/novels/test-novel-cast/cast")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 2
        assert len(data["characters"]) == 2
        assert len(data["relationships"]) == 1
        assert data["characters"][0]["name"] == "张三"
        assert data["characters"][0]["aliases"] == ["小张"]
        assert len(data["characters"][0]["story_events"]) == 1

    def test_get_cast_graph_empty_when_not_created(self, test_novel):
        """尚无 cast 文件时返回 200 与空图"""
        response = client.get("/api/v1/novels/test-novel-cast/cast")
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 2
        assert data["characters"] == []
        assert data["relationships"] == []


class TestUpdateCastGraph:
    """Test update cast graph endpoint"""

    def test_update_cast_graph_create_new(self, test_novel):
        """Test creating new cast graph"""
        response = client.put("/api/v1/novels/test-novel-cast/cast", json={
            "version": 2,
            "characters": [
                {
                    "id": "hero",
                    "name": "英雄",
                    "aliases": [],
                    "role": "主角",
                    "traits": "",
                    "note": "",
                    "story_events": []
                }
            ],
            "relationships": []
        })
        assert response.status_code == 200
        data = response.json()
        assert data["version"] == 2
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "英雄"

    def test_update_cast_graph_modify_existing(self, test_cast_graph):
        """Test modifying existing cast graph"""
        response = client.put("/api/v1/novels/test-novel-cast/cast", json={
            "version": 2,
            "characters": [
                {
                    "id": "char1",
                    "name": "张三（修改）",
                    "aliases": ["小张", "张老三"],
                    "role": "主角",
                    "traits": "勇敢且聪明",
                    "note": "修改后的备注",
                    "story_events": []
                }
            ],
            "relationships": []
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "张三（修改）"
        assert len(data["characters"][0]["aliases"]) == 2

    def test_update_cast_graph_with_relationships(self, test_novel):
        """Test updating cast graph with relationships"""
        response = client.put("/api/v1/novels/test-novel-cast/cast", json={
            "version": 2,
            "characters": [
                {"id": "a", "name": "A", "aliases": [], "role": "", "traits": "", "note": "", "story_events": []},
                {"id": "b", "name": "B", "aliases": [], "role": "", "traits": "", "note": "", "story_events": []}
            ],
            "relationships": [
                {
                    "id": "r1",
                    "source_id": "a",
                    "target_id": "b",
                    "label": "师徒",
                    "note": "师父徒弟",
                    "directed": True,
                    "story_events": [
                        {
                            "id": "ev_rel1",
                            "summary": "拜师",
                            "chapter_id": 2,
                            "importance": "key"
                        }
                    ]
                }
            ]
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["relationships"]) == 1
        assert data["relationships"][0]["label"] == "师徒"
        assert data["relationships"][0]["directed"] is True
        assert len(data["relationships"][0]["story_events"]) == 1

    def test_update_cast_graph_invalid_data(self, test_novel):
        """Test updating with invalid data"""
        response = client.put("/api/v1/novels/test-novel-cast/cast", json={
            "version": 2,
            "characters": [
                {"id": "char1"}  # Missing required fields
            ],
            "relationships": []
        })
        assert response.status_code == 422  # Validation error


class TestSearchCast:
    """Test search cast endpoint"""

    def test_search_cast_by_name(self, test_cast_graph):
        """Test searching by character name"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/search?q=张三")
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "张三"

    def test_search_cast_by_alias(self, test_cast_graph):
        """Test searching by character alias"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/search?q=小张")
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "张三"

    def test_search_cast_by_role(self, test_cast_graph):
        """Test searching by role"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/search?q=主角")
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["characters"][0]["role"] == "主角"

    def test_search_cast_by_relationship(self, test_cast_graph):
        """Test searching by relationship label"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/search?q=朋友")
        assert response.status_code == 200
        data = response.json()
        assert len(data["relationships"]) == 1
        assert data["relationships"][0]["label"] == "朋友"

    def test_search_cast_no_results(self, test_cast_graph):
        """Test search with no results"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/search?q=不存在的角色")
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 0
        assert len(data["relationships"]) == 0

    def test_search_cast_not_found(self, test_novel):
        """Test searching non-existent cast graph"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/search?q=test")
        assert response.status_code == 404


class TestGetCastCoverage:
    """Test get cast coverage endpoint"""

    def test_get_cast_coverage_basic(self, test_cast_graph, tmp_path):
        """Test getting cast coverage"""
        # Create some chapter files for testing
        novel_path = tmp_path / "data" / "novels" / "test-novel-cast"
        novel_path.mkdir(parents=True, exist_ok=True)

        chapter1 = novel_path / "chapter_1.md"
        chapter1.write_text("张三出场了，他很勇敢。", encoding='utf-8')

        chapter2 = novel_path / "chapter_2.md"
        chapter2.write_text("李四也来了。", encoding='utf-8')

        response = client.get("/api/v1/novels/test-novel-cast/cast/coverage")
        assert response.status_code == 200
        data = response.json()
        assert data["chapter_files_scanned"] == 2
        assert len(data["characters"]) == 2

        # Check character mentions
        char1 = next(c for c in data["characters"] if c["name"] == "张三")
        assert char1["mentioned"] is True
        assert 1 in char1["chapter_ids"]

        char2 = next(c for c in data["characters"] if c["name"] == "李四")
        assert char2["mentioned"] is True
        assert 2 in char2["chapter_ids"]

    def test_get_cast_coverage_not_found(self, test_novel):
        """Test getting coverage for non-existent cast graph"""
        response = client.get("/api/v1/novels/test-novel-cast/cast/coverage")
        assert response.status_code == 404
