"""修复小说状态：如果已有幕节点但 current_stage 仍为 macro_planning，则修正为 act_planning"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.persistence.database.connection import get_database

def fix_novel_stage(novel_id: str):
    """修复指定小说的状态"""
    db = get_database()

    # 查询小说信息
    novel_sql = "SELECT id, title, current_stage, autopilot_status FROM novels WHERE id = ?"
    novel = db.fetch_one(novel_sql, (novel_id,))

    if not novel:
        print(f"❌ 未找到小说: {novel_id}")
        return False

    print(f"小说: {novel.get('title')}")
    print(f"当前状态: {novel.get('current_stage')}")
    print(f"自动驾驶状态: {novel.get('autopilot_status')}")
    print()

    # 检查是否有幕节点
    nodes_sql = "SELECT COUNT(*) as count FROM story_nodes WHERE novel_id = ? AND node_type = 'act'"
    result = db.fetch_one(nodes_sql, (novel_id,))
    act_count = result.get('count', 0)

    print(f"幕节点数量: {act_count}")

    if act_count > 0 and novel.get('current_stage') == 'macro_planning':
        print()
        print("[WARNING] Detected issue: Has act nodes but stage is still macro_planning")
        print("Fixing...")

        # 更新状态为 act_planning（使用事务）
        with db.transaction() as conn:
            conn.execute(
                "UPDATE novels SET current_stage = 'act_planning' WHERE id = ?",
                (novel_id,)
            )

        print("[SUCCESS] Fixed: current_stage updated to act_planning")
        return True
    elif act_count > 0:
        print()
        print("[OK] Status is normal: Has act nodes and stage is not macro_planning")
        return True
    else:
        print()
        print("[INFO] No act nodes, macro_planning stage is normal")
        return True

if __name__ == "__main__":
    if len(sys.argv) > 1:
        novel_id = sys.argv[1]
    else:
        # 默认修复 test-novel-voice-27fda3d0
        novel_id = "test-novel-voice-27fda3d0"

    print(f"正在检查小说: {novel_id}")
    print("=" * 60)
    print()

    fix_novel_stage(novel_id)
