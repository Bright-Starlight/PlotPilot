# 规划系统改进方案（第5部分）- 宏观规划跳过已有结构

## 问题描述

### 问题现象
小说 `test-novel-voice-27fda3d0` 已经手动生成了结构规划（4个幕节点），但在全托管模式下仍然触发了宏观规划：

```
16:13:05 [INFO] application.engine.services.autopilot_daemon - [test-novel-voice-27fda3d0] 📋 开始宏观规划
```

### 问题根源

1. **状态不一致**：用户手动生成了结构规划（创建了4个幕节点），但小说的 `current_stage` 仍然是 `macro_planning`
2. **缺少检查**：`_handle_macro_planning` 方法没有检查是否已经有幕节点，直接执行宏观规划
3. **重复规划**：导致已有的手动规划可能被覆盖

### 数据库状态

```sql
SELECT id, current_stage, autopilot_status FROM novels WHERE id = 'test-novel-voice-27fda3d0';
-- current_stage: macro_planning
-- autopilot_status: running

SELECT COUNT(*) FROM story_nodes WHERE novel_id = 'test-novel-voice-27fda3d0' AND node_type = 'act';
-- 4 个幕节点
```

## 解决方案

### 1. 修改 `_handle_macro_planning` 方法

在 `application/engine/services/autopilot_daemon.py` 的 `_handle_macro_planning` 方法开头增加检查：

```python
async def _handle_macro_planning(self, novel: Novel):
    """处理宏观规划（规划部/卷/幕）- 使用极速模式让 AI 自主推断结构"""
    if not self._is_still_running(novel):
        return

    # 检查是否已有幕节点（手动规划或之前已完成宏观规划）
    novel_id = novel.novel_id.value
    all_nodes = await self.story_node_repo.get_by_novel(novel_id)
    act_nodes = [n for n in all_nodes if n.node_type.value == "act"]

    if act_nodes:
        logger.info(
            f"[{novel.novel_id}] 已有 {len(act_nodes)} 个幕节点（手动规划或已完成宏观规划），"
            f"跳过宏观规划，直接进入幕级规划"
        )
        # 全自动模式：直接进入幕级规划
        if getattr(novel, 'auto_approve_mode', False):
            novel.current_stage = NovelStage.ACT_PLANNING
            self._flush_novel(novel)
            logger.info(f"[{novel.novel_id}] 🚀 全自动模式：跳过宏观规划，直接进入幕级规划")
        else:
            # 非全自动模式：进入审阅等待（让用户确认已有的结构）
            novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
            self._flush_novel(novel)
            logger.info(f"[{novel.novel_id}] 已有结构规划，进入审阅等待")
        return

    # 继续原有的宏观规划逻辑...
```

### 2. 修复脚本

创建 `scripts/fix_novel_stage.py` 用于修复已有小说的状态：

```python
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
        print(f"[ERROR] Novel not found: {novel_id}")
        return False

    print(f"Novel: {novel.get('title')}")
    print(f"Current Stage: {novel.get('current_stage')}")
    print(f"Autopilot Status: {novel.get('autopilot_status')}")
    print()

    # 检查是否有幕节点
    nodes_sql = "SELECT COUNT(*) as count FROM story_nodes WHERE novel_id = ? AND node_type = 'act'"
    result = db.fetch_one(nodes_sql, (novel_id,))
    act_count = result.get('count', 0)

    print(f"Act Nodes: {act_count}")

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

    print(f"Checking novel: {novel_id}")
    print("=" * 60)
    print()

    fix_novel_stage(novel_id)
```

### 3. 执行修复

```bash
# 修复指定小说
python scripts/fix_novel_stage.py test-novel-voice-27fda3d0

# 输出：
# [WARNING] Detected issue: Has act nodes but stage is still macro_planning
# Fixing...
# [SUCCESS] Fixed: current_stage updated to act_planning
```

## 修复效果

### 修复前
- `current_stage`: `macro_planning`
- 全托管模式启动后触发宏观规划
- 可能覆盖已有的手动规划

### 修复后
- `current_stage`: `act_planning`
- 全托管模式启动后跳过宏观规划
- 直接进入幕级规划，检查每个幕下的章节数量
- 如果章节数量充足，直接进入写作阶段

## 相关代码位置

| 文件 | 行号 | 说明 |
|------|------|------|
| `application/engine/services/autopilot_daemon.py` | 407-432 | `_handle_macro_planning` 方法增加已有幕节点检查 |
| `application/engine/services/autopilot_daemon.py` | 681-868 | `_handle_act_planning` 方法检查已有章节数量 |
| `scripts/fix_novel_stage.py` | 1-64 | 修复脚本 |

## 测试验证

### 验证步骤

1. **创建测试小说**：手动生成结构规划（创建幕节点）
2. **设置状态**：将 `current_stage` 设置为 `macro_planning`
3. **启动全托管**：启动自动驾驶
4. **检查日志**：确认跳过宏观规划，直接进入幕级规划

### 预期结果

```
[test-novel-voice-27fda3d0] 已有 4 个幕节点（手动规划或已完成宏观规划），跳过宏观规划，直接进入幕级规划
[test-novel-voice-27fda3d0] 🚀 全自动模式：跳过宏观规划，直接进入幕级规划
[test-novel-voice-27fda3d0] 📝 开始幕级规划 (第 1 幕)
[test-novel-voice-27fda3d0] 幕 1 章节数量检查: 已有 0 章, 期望 5 章
[test-novel-voice-27fda3d0] 幕 1 无规划，开始自动规划
```

## 防止未来再次出现

### 1. 手动规划完成后自动更新状态

在 `continuous_planning_service.py` 的 `confirm_macro_plan` 方法中，确认宏观规划后自动更新小说状态：

```python
async def confirm_macro_plan(self, novel_id: str, structure: list) -> Dict:
    # ... 创建节点逻辑 ...
    
    # 更新小说状态为 act_planning
    novel = self.novel_repository.get_by_id(NovelId(novel_id))
    if novel and novel.current_stage == NovelStage.MACRO_PLANNING:
        novel.current_stage = NovelStage.ACT_PLANNING
        self.novel_repository.save(novel)
        logger.info(f"[{novel_id}] 宏观规划确认完成，状态更新为 act_planning")
```

### 2. 前端提示

在前端手动规划完成后，提示用户：
- "结构规划已完成，可以启动全托管模式进行章节规划和写作"
- 自动将小说状态从 `macro_planning` 更新为 `act_planning`

### 3. 状态一致性检查

在自动驾驶启动时，增加状态一致性检查：

```python
async def start_autopilot(self, novel_id: str):
    novel = self.novel_repository.get_by_id(NovelId(novel_id))
    
    # 状态一致性检查
    all_nodes = await self.story_node_repo.get_by_novel(novel_id)
    act_nodes = [n for n in all_nodes if n.node_type.value == "act"]
    
    if act_nodes and novel.current_stage == NovelStage.MACRO_PLANNING:
        logger.warning(
            f"[{novel_id}] 状态不一致：已有 {len(act_nodes)} 个幕节点但状态为 macro_planning，"
            f"自动修正为 act_planning"
        )
        novel.current_stage = NovelStage.ACT_PLANNING
        self.novel_repository.save(novel)
```

## 总结

这次修复解决了手动规划与全托管模式的状态不一致问题：

1. **根本原因**：`_handle_macro_planning` 没有检查已有幕节点
2. **修复方案**：增加幕节点检查，如果已有则跳过宏观规划
3. **数据修复**：提供脚本修复已有小说的状态
4. **预防措施**：在多个环节增加状态一致性检查

修复后，全托管模式会正确识别手动规划的结构，不会重复执行宏观规划。
