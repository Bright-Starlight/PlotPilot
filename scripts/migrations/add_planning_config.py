"""数据库迁移：为 novels 表添加 planning_config 字段

执行方式：
    python scripts/migrations/add_planning_config.py
"""
import sqlite3
import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from application.paths import get_db_path


def migrate_add_planning_config():
    """为 novels 表添加 planning_config 字段并设置默认值"""
    db_path = get_db_path()

    print(f"Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. 检查字段是否已存在
        cursor.execute("PRAGMA table_info(novels)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'planning_config' in columns:
            print("[OK] planning_config field already exists, skipping")
        else:
            # 2. 添加 planning_config 字段
            print("Adding planning_config field...")
            cursor.execute("""
                ALTER TABLE novels ADD COLUMN planning_config TEXT
            """)
            print("[OK] planning_config field added successfully")

        # 3. 为现有小说设置默认配置
        cursor.execute("""
            SELECT id, planning_config FROM novels
        """)
        novels = cursor.fetchall()

        default_config = {
            "chapters_per_act": 5,
            "acts_per_volume": 3,
            "volumes_per_part": 2
        }
        default_config_json = json.dumps(default_config)

        updated_count = 0
        for novel_id, existing_config in novels:
            if not existing_config:
                cursor.execute("""
                    UPDATE novels
                    SET planning_config = ?
                    WHERE id = ?
                """, (default_config_json, novel_id))
                updated_count += 1

        conn.commit()

        print(f"[OK] Added default planning_config to {updated_count} novels")
        print(f"  Default config: {default_config}")
        print(f"\nTotal: {len(novels)} novels")
        print("[OK] Migration completed successfully")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_add_planning_config()
