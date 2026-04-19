"""SQLite ChapterGenerationMetricsRepository 集成测试。"""
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_generation_metrics_repository import (
    SqliteChapterGenerationMetricsRepository,
)


def test_upsert_persists_beat_quality_json(tmp_path):
    db = DatabaseConnection(str(tmp_path / "test.db"))
    try:
        db.execute(
            "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
            ("novel-1", "Test Novel", "test-novel", 10),
        )
        db.execute(
            """
            INSERT INTO chapters (id, novel_id, number, title, content, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("chapter-1", "novel-1", 1, "第一章", "正文", "draft"),
        )
        db.get_connection().commit()

        repo = SqliteChapterGenerationMetricsRepository(db)
        repo.upsert(
            "novel-1",
            1,
            {
                "generated_via": "autopilot",
                "target": 3000,
                "actual": 2800,
                "tolerance": 0.15,
                "delta": -200,
                "status": "too_short",
                "within_tolerance": False,
                "action": "needs_expansion",
                "expansion_attempts": 2,
                "trim_applied": False,
                "fallback_used": True,
                "beat_quality": [
                    {"beat_index": 0, "passed": True, "char_count": 180},
                    {"beat_index": 1, "passed": False, "char_count": 20},
                ],
            },
        )

        saved = repo.get("novel-1", 1)

        assert saved is not None
        assert saved["status"] == "too_short"
        assert saved["beat_quality"] == [
            {"beat_index": 0, "passed": True, "char_count": 180},
            {"beat_index": 1, "passed": False, "char_count": 20},
        ]
    finally:
        db.close()
