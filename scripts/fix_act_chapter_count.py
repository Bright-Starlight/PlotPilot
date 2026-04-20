"""修复幕节点的 suggested_chapter_count

当手动规划时前端没有传递 suggested_chapter_count，导致幕节点的该字段为 None。
此脚本根据小说的 planning_config 为所有幕节点设置 suggested_chapter_count。

用法：
    python scripts/fix_act_chapter_count.py <novel_id>
    python scripts/fix_act_chapter_count.py <novel_id> --chapters-per-act 2
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.persistence.database.connection import get_database


def fix_act_chapter_count(novel_id: str, chapters_per_act: int = None):
    """修复幕节点的 suggested_chapter_count"""
    db = get_database()

    # 查询小说配置
    novel_sql = "SELECT id, title, planning_config FROM novels WHERE id = ?"
    novel = db.fetch_one(novel_sql, (novel_id,))

    if not novel:
        print(f"[ERROR] 未找到小说: {novel_id}")
        return False

    print(f"小说: {novel.get('title')}")
    print(f"当前配置: {novel.get('planning_config')}")
    print()

    # 确定每幕章节数
    if chapters_per_act is None:
        config = json.loads(novel.get('planning_config') or '{}')
        chapters_per_act = config.get('chapters_per_act', 5)

    print(f"将为所有幕设置 suggested_chapter_count = {chapters_per_act}")
    print()

    # 查询所有幕节点
    acts_sql = """
        SELECT id, number, title, suggested_chapter_count
        FROM story_nodes
        WHERE novel_id = ? AND node_type = 'act'
        ORDER BY number
    """
    acts = db.fetch_all(acts_sql, (novel_id,))

    if not acts:
        print("[INFO] 没有找到幕节点")
        return True

    print(f"找到 {len(acts)} 个幕节点:")
    for act in acts:
        current = act.get('suggested_chapter_count')
        print(f"  幕 {act.get('number')}: {act.get('title')}")
        print(f"    当前: {current} -> 更新为: {chapters_per_act}")

    print()

    # 更新所有幕节点
    with db.transaction() as conn:
        for act in acts:
            conn.execute(
                "UPDATE story_nodes SET suggested_chapter_count = ? WHERE id = ?",
                (chapters_per_act, act.get('id'))
            )

    print(f"[SUCCESS] 已更新 {len(acts)} 个幕节点的 suggested_chapter_count")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='修复幕节点的 suggested_chapter_count')
    parser.add_argument('novel_id', help='小说 ID')
    parser.add_argument('--chapters-per-act', type=int, help='每幕章节数（不指定则使用小说配置）')

    args = parser.parse_args()

    print(f"正在修复小说: {args.novel_id}")
    print("=" * 60)
    print()

    fix_act_chapter_count(args.novel_id, args.chapters_per_act)
