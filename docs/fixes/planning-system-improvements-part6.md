# 规划系统改进方案（第6部分）- 手动规划时设置幕章节数

## 问题描述

### 问题现象
小说 `test-novel-voice-27fda3d0` 在手动规划时，前端界面显示"平均每幕将包含约 2 章"，但实际创建的幕节点 `suggested_chapter_count` 为 `None`，导致 autopilot 使用小说的全局配置（默认 5 章）而不是用户期望的 2 章。

```
16:21:29 [INFO] application.engine.services.autopilot_daemon - [test-novel-voice-27fda3d0] 📝 开始幕级规划 (第 1 幕)
16:21:29 [INFO] application.engine.services.autopilot_daemon - [test-novel-voice-27fda3d0] 幕 1 章节数量检查: 已有 0 章, 期望 5 章
```

用户期望：期望 2 章（根据前端界面的计算）

### 问题根源

1. **前端 Bug**：`MacroPlanModal.vue` 在调用 `confirmMacro` API 时，没有为幕节点添加 `suggested_chapter_count` 字段
2. **后端兜底逻辑**：`autopilot_daemon.py` 的 `_get_expected_chapter_count` 方法使用优先级：
   - 优先级1：幕节点的 `suggested_chapter_count`
   - 优先级2：小说的 `planning_config.chapters_per_act`
   - 优先级3：默认值 5
3. **默认配置问题**：小说的默认配置是 5 章/幕（由迁移脚本设置）

### 数据库状态

```sql
-- 小说配置
SELECT id, title, planning_config FROM novels WHERE id = 'test-novel-voice-27fda3d0';
-- planning_config: {"chapters_per_act": 5, "acts_per_volume": 3, "volumes_per_part": 2}

-- 幕节点
SELECT id, number, title, suggested_chapter_count FROM story_nodes 
WHERE novel_id = 'test-novel-voice-27fda3d0' AND node_type = 'act';
-- 所有幕的 suggested_chapter_count: None
```

## 解决方案

### 1. 修改前端代码

在 `frontend/src/components/workbench/MacroPlanModal.vue` 中：

#### 1.1 添加 `addSuggestedChapterCount` 函数

```typescript
const addSuggestedChapterCount = (parts: MacroPartNode[]): MacroPartNode[] => {
  // 计算每幕建议章节数
  const suggestedCount = chaptersPerAct.value

  // 深拷贝并为每个幕添加 suggested_chapter_count
  return parts.map(part => {
    const newPart = { ...part }
    if (Array.isArray(newPart.volumes)) {
      newPart.volumes = newPart.volumes.map(volume => {
        const newVolume = { ...volume }
        if (Array.isArray(newVolume.acts)) {
          newVolume.acts = newVolume.acts.map(act => ({
            ...act,
            suggested_chapter_count: suggestedCount
          }))
        }
        return newVolume
      })
    }
    return newPart
  })
}
```

#### 1.2 修改 `doConfirm` 方法

```typescript
const doConfirm = async () => {
  confirming.value = true
  try {
    // 为每个幕节点添加 suggested_chapter_count
    const structureWithChapterCount = addSuggestedChapterCount(editableStructure.value)

    const res = await planningApi.confirmMacro(props.novelId, { 
      structure: structureWithChapterCount as Record<string, unknown>[] 
    }) as any
    
    // ... 其余代码不变
  }
}
```

### 2. 修复已有数据

#### 2.1 更新小说的全局配置

创建 `scripts/update_planning_config.py`：

```python
"""更新小说的 planning_config 配置"""
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

    # 更新数据库
    with db.transaction() as conn:
        conn.execute(
            "UPDATE novels SET planning_config = ? WHERE id = ?",
            (new_config_json, novel_id)
        )

    print("[SUCCESS] 配置更新成功")
    return True
```

使用方法：
```bash
python scripts/update_planning_config.py test-novel-voice-27fda3d0 --chapters-per-act 2
```

#### 2.2 修复幕节点的 suggested_chapter_count

创建 `scripts/fix_act_chapter_count.py`：

```python
"""修复幕节点的 suggested_chapter_count"""
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

    # 确定每幕章节数
    if chapters_per_act is None:
        config = json.loads(novel.get('planning_config') or '{}')
        chapters_per_act = config.get('chapters_per_act', 5)

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

    # 更新所有幕节点
    with db.transaction() as conn:
        for act in acts:
            conn.execute(
                "UPDATE story_nodes SET suggested_chapter_count = ? WHERE id = ?",
                (chapters_per_act, act.get('id'))
            )

    print(f"[SUCCESS] 已更新 {len(acts)} 个幕节点的 suggested_chapter_count")
    return True
```

使用方法：
```bash
# 使用小说的全局配置
python scripts/fix_act_chapter_count.py test-novel-voice-27fda3d0

# 或指定章节数
python scripts/fix_act_chapter_count.py test-novel-voice-27fda3d0 --chapters-per-act 2
```

## 修复效果

### 修复前
- 前端界面显示"平均每幕将包含约 2 章"
- 但幕节点的 `suggested_chapter_count` 为 `None`
- Autopilot 使用小说全局配置（5 章）或默认值（5 章）
- 日志显示："期望 5 章"

### 修复后
- 前端在确认宏观规划时，为每个幕添加 `suggested_chapter_count` 字段
- 幕节点的 `suggested_chapter_count` 正确设置为用户期望的值
- Autopilot 使用幕节点的配置
- 日志显示："期望 2 章"

## 相关代码位置

| 文件 | 行号 | 说明 |
|------|------|------|
| `frontend/src/components/workbench/MacroPlanModal.vue` | 287-307 | 新增 `addSuggestedChapterCount` 函数 |
| `frontend/src/components/workbench/MacroPlanModal.vue` | 419-425 | 修改 `doConfirm` 方法，调用 `addSuggestedChapterCount` |
| `application/engine/services/autopilot_daemon.py` | 533-544 | `_get_expected_chapter_count` 方法（优先级逻辑） |
| `scripts/update_planning_config.py` | 1-73 | 更新小说全局配置的脚本 |
| `scripts/fix_act_chapter_count.py` | 1-78 | 修复幕节点章节数的脚本 |

## 测试验证

### 验证步骤

1. **前端测试**：
   - 创建新小说
   - 启动结构规划（精密定制模式）
   - 设置目标章节数 10，结构分布 1 部 × 1 卷 × 4 幕
   - 确认生成（应该显示"平均每幕将包含约 2 章"）
   - 确认写入结构树

2. **数据库验证**：
   ```sql
   SELECT id, number, title, suggested_chapter_count 
   FROM story_nodes 
   WHERE novel_id = '<novel_id>' AND node_type = 'act';
   ```
   预期：所有幕的 `suggested_chapter_count` 应该是 2

3. **Autopilot 验证**：
   - 启动全托管模式
   - 检查日志，应该显示："期望 2 章"

### 预期结果

```
[test-novel-voice-27fda3d0] 📝 开始幕级规划 (第 1 幕)
[test-novel-voice-27fda3d0] 幕 1 章节数量检查: 已有 0 章, 期望 2 章
[test-novel-voice-27fda3d0] 幕 1 无规划，开始自动规划
```

## 防止未来再次出现

### 1. 前端验证

在前端添加单元测试，验证 `addSuggestedChapterCount` 函数：

```typescript
describe('addSuggestedChapterCount', () => {
  it('should add suggested_chapter_count to all acts', () => {
    const input = [
      {
        title: '第一部',
        volumes: [
          {
            title: '第一卷',
            acts: [
              { title: '第一幕' },
              { title: '第二幕' }
            ]
          }
        ]
      }
    ]
    
    const result = addSuggestedChapterCount(input, 2)
    
    expect(result[0].volumes[0].acts[0].suggested_chapter_count).toBe(2)
    expect(result[0].volumes[0].acts[1].suggested_chapter_count).toBe(2)
  })
})
```

### 2. 后端验证

在后端 `confirm_macro_plan_safe` 方法中添加警告日志：

```python
async def confirm_macro_plan_safe(self, novel_id: str, structure: List[Dict]) -> Dict:
    # ... 现有代码 ...
    
    # 检查幕节点是否有 suggested_chapter_count
    for part in structure:
        for volume in part.get('volumes', []):
            for act in volume.get('acts', []):
                if 'suggested_chapter_count' not in act or act['suggested_chapter_count'] is None:
                    logger.warning(
                        f"[{novel_id}] 幕节点 '{act.get('title')}' 缺少 suggested_chapter_count，"
                        f"将使用小说全局配置"
                    )
```

### 3. API 文档更新

在 `continuous_planning_routes.py` 的 API 文档中明确说明：

```python
@router.post("/novels/{novel_id}/macro/confirm")
async def confirm_macro_plan(
    novel_id: str,
    request: MacroPlanConfirmRequest,
    service: ContinuousPlanningService = Depends(get_continuous_planning_service)
):
    """确认宏观规划（安全版本，带智能合并）

    用户编辑后，保存所有部-卷-幕节点（不创建章节）
    
    **重要**：每个幕节点应包含 `suggested_chapter_count` 字段，
    指定该幕的建议章节数。如果未提供，将使用小说的全局配置。
    
    请求示例：
    ```json
    {
      "structure": [
        {
          "title": "第一部",
          "volumes": [
            {
              "title": "第一卷",
              "acts": [
                {
                  "title": "第一幕",
                  "description": "开端",
                  "suggested_chapter_count": 2
                }
              ]
            }
          ]
        }
      ]
    }
    ```
    """
```

## 总结

这次修复解决了手动规划时幕章节数不一致的问题：

1. **根本原因**：前端在确认宏观规划时，没有传递 `suggested_chapter_count` 字段
2. **修复方案**：
   - 前端：添加 `addSuggestedChapterCount` 函数，在确认前为每个幕添加章节数
   - 后端：保持现有的优先级逻辑（幕配置 > 小说全局配置 > 默认值）
3. **数据修复**：提供脚本修复已有小说的配置和幕节点
4. **预防措施**：添加测试、日志警告和 API 文档

修复后，手动规划时前端界面显示的"平均每幕将包含约 X 章"会正确传递给后端，autopilot 会使用这个值进行幕级规划。
