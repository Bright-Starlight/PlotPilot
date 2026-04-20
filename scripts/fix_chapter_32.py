"""修复第32章验证问题的脚本

问题：
1. timeline_end 设置为"地下市场突遭袭击"，但大纲和内容实际停留在"废墟石室"
2. 大纲最后一句被截断

解决方案：
1. 修正 timeline_end 为"废墟石室"
2. 补全大纲内容
3. 重新生成状态锁
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infrastructure.persistence.database.connection import get_database
import json

def fix_chapter_32():
    db = get_database()
    novel_id = 'novel-1776499481673'
    chapter_number = 32

    print("=== 修复第32章验证问题 ===\n")

    # 1. 查看当前状态
    print("1. 当前状态：")
    story_node_sql = '''
        SELECT id, title, timeline_end, outline
        FROM story_nodes
        WHERE novel_id = ? AND node_type = 'chapter' AND number = ?
    '''
    story_node = db.fetch_one(story_node_sql, (novel_id, chapter_number))

    if not story_node:
        print(f"错误：未找到第{chapter_number}章的规划")
        return

    print(f"   章节ID: {story_node.get('id')}")
    print(f"   标题: {story_node.get('title')}")
    print(f"   当前 timeline_end: {story_node.get('timeline_end')}")
    print(f"   大纲长度: {len(story_node.get('outline', ''))} 字符")
    print(f"   大纲最后50字: ...{story_node.get('outline', '')[-50:]}")
    print()

    # 2. 修正 timeline_end
    print("2. 修正 timeline_end：")
    new_timeline_end = "废墟石室"

    update_sql = '''
        UPDATE story_nodes
        SET timeline_end = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    '''

    try:
        db.execute(update_sql, (new_timeline_end, story_node.get('id')))
        db.get_connection().commit()
        print(f"   [OK] timeline_end 已更新为: {new_timeline_end}")
    except Exception as e:
        print(f"   [ERROR] 更新失败: {e}")
        return

    print()

    # 3. 补全大纲
    print("3. 补全大纲：")
    current_outline = story_node.get('outline', '')

    # 检查大纲是否被截断
    if current_outline.endswith('发现黑市'):
        # 补全大纲
        completed_outline = current_outline + "中有人在追踪皇族血脉的线索。"

        update_outline_sql = '''
            UPDATE story_nodes
            SET outline = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        '''

        try:
            db.execute(update_outline_sql, (completed_outline, story_node.get('id')))
            db.get_connection().commit()
            print(f"   [OK] 大纲已补全")
            print(f"   新增内容: 中有人在追踪皇族血脉的线索。")
        except Exception as e:
            print(f"   [ERROR] 补全失败: {e}")
            return
    else:
        print(f"   - 大纲未被截断，无需补全")

    print()

    # 4. 更新状态锁
    print("4. 更新状态锁：")
    chapter_id = f'chapter-{novel_id}-chapter-{chapter_number}'

    # 查询当前状态锁
    state_lock_sql = '''
        SELECT state_lock_id, ending_lock_json
        FROM state_locks
        WHERE chapter_id = ?
        ORDER BY latest_version DESC LIMIT 1
    '''
    state_lock = db.fetch_one(state_lock_sql, (chapter_id,))

    if state_lock:
        ending_lock = json.loads(state_lock.get('ending_lock_json', '{}'))

        # 更新 ending_lock
        if 'entries' in ending_lock and len(ending_lock['entries']) > 0:
            old_value = ending_lock['entries'][0].get('value')
            ending_lock['entries'][0]['value'] = new_timeline_end

            update_lock_sql = '''
                UPDATE state_locks
                SET ending_lock_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE state_lock_id = ?
            '''

            try:
                db.execute(update_lock_sql, (json.dumps(ending_lock, ensure_ascii=False), state_lock.get('state_lock_id')))
                db.get_connection().commit()
                print(f"   [OK] 状态锁已更新")
                print(f"   旧值: {old_value}")
                print(f"   新值: {new_timeline_end}")
            except Exception as e:
                print(f"   [ERROR] 更新失败: {e}")
                return
        else:
            print(f"   - 状态锁格式异常，跳过更新")
    else:
        print(f"   - 未找到状态锁")

    print()

    # 5. 验证修复结果
    print("5. 验证修复结果：")

    # 重新查询
    story_node = db.fetch_one(story_node_sql, (novel_id, chapter_number))
    state_lock = db.fetch_one(state_lock_sql, (chapter_id,))

    print(f"   story_nodes.timeline_end: {story_node.get('timeline_end')}")

    if state_lock:
        ending_lock = json.loads(state_lock.get('ending_lock_json', '{}'))
        if 'entries' in ending_lock and len(ending_lock['entries']) > 0:
            print(f"   state_locks.ending_lock: {ending_lock['entries'][0].get('value')}")

    print(f"   大纲长度: {len(story_node.get('outline', ''))} 字符")
    print(f"   大纲最后50字: ...{story_node.get('outline', '')[-50:]}")

    print()
    print("=== 修复完成 ===")
    print()
    print("建议后续操作：")
    print("1. 重新运行第32章的验证")
    print("2. 检查验证报告中的问题是否已解决")
    print("3. 如果问题仍存在，可能需要重新生成章节内容")

    db.close()

if __name__ == '__main__':
    fix_chapter_32()
