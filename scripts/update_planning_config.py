"""更新小说的 planning_config 配置

用法：
    python scripts/update_planning_config.py <novel_id> --chapters-per-act 2
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.persistence.database.connection import get_database


def update_planning_config(novel_id: str, chapters_per_act: int = None,
                          acts_per_volume: int = None, volumes_per_part: int = None):
    """更新小说的规划配置"""
    db = get_database()

    # 查询当前配置
    novel_sql = "SELECT id, title, planning_config FROM novels WHERE id = ?"
    novel = db.fetch_one(novel_sql, (novel_id,))

    if not novel:
        print(f"[ERROR] 未找到小说: {novel_id}")
        return False

    print(f"小说: {novel.get('title')}")
    print(f"当前配置: {novel.get('planning_config')}")
    print()

    # 解析现有配置
    current_config = json.loads(novel.get('planning_config') or '{}')

    # 更新配置
    if chapters_per_act is not None:
        current_config['chapters_per_act'] = chapters_per_act
    if acts_per_volume is not None:
        current_config['acts_per_volume'] = acts_per_volume
    if volumes_per_part is not None:
        current_config['volumes_per_part'] = volumes_per_part

    new_config_json = json.dumps(current_config)

    print(f"新配置: {new_config_json}")
    print()

    # 更新数据库
    with db.transaction() as conn:
        conn.execute(
            "UPDATE novels SET planning_config = ? WHERE id = ?",
            (new_config_json, novel_id)
        )

    print("[SUCCESS] 配置更新成功")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='更新小说的规划配置')
    parser.add_argument('novel_id', help='小说 ID')
    parser.add_argument('--chapters-per-act', type=int, help='每幕章节数')
    parser.add_argument('--acts-per-volume', type=int, help='每卷幕数')
    parser.add_argument('--volumes-per-part', type=int, help='每部卷数')

    args = parser.parse_args()

    if not any([args.chapters_per_act, args.acts_per_volume, args.volumes_per_part]):
        print("[ERROR] 至少需要指定一个配置项")
        parser.print_help()
        sys.exit(1)

    print(f"正在更新小说配置: {args.novel_id}")
    print("=" * 60)
    print()

    update_planning_config(
        args.novel_id,
        chapters_per_act=args.chapters_per_act,
        acts_per_volume=args.acts_per_volume,
        volumes_per_part=args.volumes_per_part
    )
