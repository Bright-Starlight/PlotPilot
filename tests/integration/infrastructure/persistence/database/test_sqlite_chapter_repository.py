"""SQLite Chapter Repository 集成测试。"""
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.tension_dimensions import TensionDimensions
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_repository import (
    SqliteChapterRepository,
)


def test_update_tension_dimensions_if_default_is_idempotent(tmp_path):
    db = DatabaseConnection(str(tmp_path / "test.db"))
    try:
        repo = SqliteChapterRepository(db)
        db.execute(
            "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
            ("novel-1", "Test Novel", "test-novel", 10),
        )
        chapter = Chapter(
            id="ch-1",
            novel_id=NovelId("novel-1"),
            number=7,
            title="第7章",
            content="这是需要补回填的章节正文。",
        )
        repo.save(chapter)

        dims = TensionDimensions.from_raw_scores(80, 82, 79)
        assert repo.update_tension_dimensions_if_default("novel-1", 7, dims) is True

        saved = repo.get_by_novel_and_number(NovelId("novel-1"), 7)
        assert saved is not None
        assert saved.tension_score == dims.composite_score
        assert saved.plot_tension == dims.plot_tension
        assert saved.emotional_tension == dims.emotional_tension
        assert saved.pacing_tension == dims.pacing_tension

        second_dims = TensionDimensions.from_raw_scores(60, 60, 60)
        assert repo.update_tension_dimensions_if_default("novel-1", 7, second_dims) is False

        unchanged = repo.get_by_novel_and_number(NovelId("novel-1"), 7)
        assert unchanged is not None
        assert unchanged.tension_score == dims.composite_score
        assert unchanged.plot_tension == dims.plot_tension
        assert unchanged.emotional_tension == dims.emotional_tension
        assert unchanged.pacing_tension == dims.pacing_tension
    finally:
        db.close()
