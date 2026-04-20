"""插入3本测试小说到数据库（用于测试精密规划结构参数）"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, '.')

from domain.novel.value_objects.novel_id import NovelId
from domain.novel.entities.novel import (
    Novel, NovelStage, AutopilotStatus, PlanningConfig
)
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository


def make_novel(title, author, plan_mode, parts, volumes_per_part, acts_per_volume, target_chapters):
    db_path = str(Path(__file__).resolve().parents[1] / "data" / "aitext.db")
    db = DatabaseConnection(db_path)
    repo = SqliteNovelRepository(db)

    config = PlanningConfig(
        plan_mode=plan_mode,
        parts=parts,
        volumes_per_part=volumes_per_part,
        acts_per_volume=acts_per_volume,
    )

    total_acts = parts * volumes_per_part * acts_per_volume
    novel_id = NovelId(value=f"novel-{uuid.uuid4().hex[:8]}")

    novel = Novel(
        id=novel_id,
        title=title,
        author=author,
        target_chapters=target_chapters,
        premise="测试用小说",
        stage=NovelStage.MACRO_PLANNING,
        autopilot_status=AutopilotStatus.STOPPED,
        auto_approve_mode=False,
        current_stage=NovelStage.MACRO_PLANNING,
        planning_config=config,
        target_words_per_chapter=3500,
        genre="测试",
    )

    repo.save(novel)
    print("OK: {} [{}] {} chapters, {} acts ({}x{}x{})".format(
        novel_id.value, plan_mode, target_chapters, total_acts,
        parts, volumes_per_part, acts_per_volume))
    return novel_id.value


def main():
    novels = [
        # (title, author, plan_mode, parts, volumes, acts, target_chapters)
        # 总幕数=36, 章数=54, 54>36 ✓
        ("测试小说A：修仙大陆", "作者A", "precise", 3, 3, 4, 54),
        # 总幕数=12, 章数=30, 30>12 ✓
        ("测试小说B：都市异能", "作者B", "precise", 2, 2, 3, 30),
        # 总幕数=8, 章数=20, 20>8 ✓
        ("测试小说C：星际战争", "作者C", "quick", 2, 2, 2, 20),
    ]

    print("Inserting 3 test novels (chapters > acts):")
    for title, author, mode, p, v, a, chapters in novels:
        make_novel(title, author, mode, p, v, a, chapters)
    print("\nDone.")


if __name__ == "__main__":
    main()
