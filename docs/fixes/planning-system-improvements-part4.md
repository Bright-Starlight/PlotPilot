# 规划系统改进方案（第4部分）

## 集成到现有流程

### 集成到自动驾驶守护进程

```python
# application/engine/services/autopilot_daemon.py

async def _handle_chapter_writing(self, novel: Novel) -> None:
    """章节写作阶段（集成动态节拍调整）"""
    # ... 前面的代码 ...
    
    target_word_count = max(1, int(
        getattr(novel, "target_words_per_chapter", AppConfig.DEFAULT_WORDS_PER_CHAPTER) 
        or AppConfig.DEFAULT_WORDS_PER_CHAPTER
    ))
    
    # 动态计算节拍数量
    from application.blueprint.services.beat_calculator import BeatCalculator
    beat_count = BeatCalculator.calculate_beat_count(target_word_count)
    
    # 验证节拍数量
    is_valid, reason = BeatCalculator.validate_beat_count(target_word_count, beat_count)
    if not is_valid:
        logger.warning(
            f"[{novel.novel_id}] 节拍数量不合理: {reason}, "
            f"使用推荐值: {beat_count}"
        )
    
    logger.info(
        f"[{novel.novel_id}] 章节目标字数: {target_word_count}, "
        f"动态计算节拍数: {beat_count}"
    )
    
    # 生成节拍表时传入节拍数量
    beat_sheet = await self.beat_sheet_service.generate_beat_sheet(
        chapter_id=next_chapter_node.id,
        outline=outline,
        target_beat_count=beat_count,  # 新增参数
        state_lock_version=effective_state_lock_version
    )
    
    # ... 后续代码 ...
```

### 修改 BeatSheetService

```python
# application/blueprint/services/beat_sheet_service.py

async def generate_beat_sheet(
    self,
    chapter_id: str,
    outline: str,
    *,
    plan_version: int | None = None,
    state_lock_version: int | None = None,
    target_beat_count: int | None = None,  # 新增参数
) -> BeatSheet:
    """为章节生成节拍表
    
    Args:
        chapter_id: 章节 ID
        outline: 章节大纲
        plan_version: 规划版本
        state_lock_version: 状态锁版本
        target_beat_count: 目标节拍数量（可选，不传则自动计算）
    """
    logger.info(
        f"Generating beat sheet for chapter {chapter_id} "
        f"with state_lock_version={state_lock_version}"
    )
    
    if state_lock_version is None or state_lock_version <= 0:
        raise ValueError("state_lock_version is required before beat sheet generation")
    
    effective_state_lock_version = state_lock_version
    
    # 0. 获取章节信息和小说配置
    from domain.novel.value_objects.chapter_id import ChapterId
    chapter = self.chapter_repo.get_by_id(ChapterId(chapter_id))
    if not chapter:
        raise ValueError(f"Chapter {chapter_id} not found")
    
    # 获取小说的目标章节字数配置
    from domain.novel.repositories.novel_repository import NovelRepository
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
    
    novel_repo = SqliteNovelRepository(get_database())
    novel = novel_repo.get_by_id(chapter.novel_id)
    target_words_per_chapter = novel.target_words_per_chapter if novel else 3500
    
    # 动态计算节拍数量
    from application.blueprint.services.beat_calculator import BeatCalculator
    if target_beat_count is None:
        target_beat_count = BeatCalculator.calculate_beat_count(target_words_per_chapter)
    
    # 计算每个节拍的目标字数
    words_per_beat = BeatCalculator.calculate_words_per_beat(
        target_words_per_chapter, 
        target_beat_count
    )
    
    logger.info(
        f"Target words per chapter: {target_words_per_chapter}, "
        f"Beat count: {target_beat_count}, "
        f"Words per beat: {words_per_beat}"
    )
    
    # 1. 混合检索：获取相关上下文
    context = await self._retrieve_relevant_context(chapter_id, outline)
    
    # 2. 构建提示词（传入动态节拍数和字数分配）
    prompt = self._build_beat_sheet_prompt(
        outline, 
        context, 
        target_words_per_chapter,
        target_beat_count=target_beat_count,  # 新增
        words_per_beat=words_per_beat  # 新增
    )
    
    # 3. 调用 LLM 生成节拍表
    config = GenerationConfig(max_tokens=2048, temperature=0.7)
    response = await self.llm_service.generate(prompt, config)
    
    # 4. 解析响应
    scenes = self._parse_llm_response(response)
    
    # 5. 创建节拍表实体
    beat_sheet = BeatSheet(
        id=str(uuid.uuid4()),
        chapter_id=chapter_id,
        scenes=scenes,
        plan_version=int(plan_version or 0),
        state_lock_version=effective_state_lock_version,
    )
    
    # 6. 保存到仓储
    await self.beat_sheet_repo.save(beat_sheet)
    
    logger.info(f"Beat sheet generated with {len(scenes)} scenes")
    return beat_sheet
```

### 修改节拍表提示词构建

```python
def _build_beat_sheet_prompt(
    self,
    outline: str,
    context: Dict,
    target_words_per_chapter: int = 3500,
    target_beat_count: int = 4,  # 新增
    words_per_beat: List[int] = None  # 新增
) -> Prompt:
    """构建节拍表生成提示词（使用动态节拍数和字数分配）
    
    Args:
        outline: 章节大纲
        context: 上下文信息
        target_words_per_chapter: 目标章节字数
        target_beat_count: 目标节拍数量
        words_per_beat: 每个节拍的目标字数列表
    """
    
    if words_per_beat is None or len(words_per_beat) != target_beat_count:
        # 降级：平均分配
        avg_words = target_words_per_chapter // target_beat_count
        words_per_beat = [avg_words] * target_beat_count
    
    # 计算总字数范围
    total_words_min = int(target_words_per_chapter * 0.8)  # 80%
    total_words_max = int(target_words_per_chapter * 1.2)  # 120%
    
    system_prompt = f"""你是一位专业的小说编剧，擅长将章节大纲拆解为具体的场景（Scene）。

⚠️ 核心原则：必须严格遵循章节大纲，不得偏离大纲的核心场景、任务和终态。

你的任务是将章节大纲拆解为 {target_beat_count} 个场景，每个场景应该：
1. 有明确的场景目标（Scene Goal）
2. 指定 POV 角色（从哪个角色的视角叙述）
3. 指定地点（可选）
4. 指定情绪基调（例如：紧张、温馨、悲伤、激烈）
5. 预估字数（根据下面的分配）

场景字数分配：
{chr(10).join(f"- 场景 {i+1}: {words} 字" for i, words in enumerate(words_per_beat))}

请以 JSON 格式返回场景列表，格式如下：
{{
  "scenes": [
    {{
      "title": "场景标题",
      "goal": "这个场景要达成什么目标",
      "pov_character": "POV 角色名称",
      "location": "地点（可选）",
      "tone": "情绪基调",
      "estimated_words": {words_per_beat[0]}
    }}
  ]
}}

⚠️ 严格约束：
- 场景必须在大纲指定的地点发生
- 场景必须推进大纲指定的任务
- 场景必须包含大纲指定的冲突
- 最后一个场景的终态必须与大纲的终态一致
- 上下文信息（故事线、伏笔）仅作为参考，不得替代大纲内容

注意事项：
- 场景之间要有逻辑连贯性
- 每个场景聚焦一个明确目标，避免贪多
- POV 角色应该是章节中的主要角色
- 预估字数总和应该在 {total_words_min}-{total_words_max} 字之间（目标：{target_words_per_chapter} 字）
- 充分利用提供的上下文信息（人物、故事线、伏笔、地点、时间线）
"""
    
    # 构建用户提示词（保持原有逻辑）
    user_prompt = f"""章节大纲：
{outline}

"""
    
    # 添加主要人物信息
    if context.get("characters"):
        user_prompt += "\n=== 主要人物 ===\n"
        for char in context["characters"]:
            user_prompt += f"- {char['name']} ({char['role']}): {char['brief']}\n"
    
    # ... 其他上下文信息（保持原有代码）...
    
    user_prompt += f"\n请基于以上信息生成 {target_beat_count} 个场景（JSON 格式）："
    
    return Prompt(
        system=system_prompt,
        user=user_prompt
    )
```

---

## 数据库迁移

### 新增字段

```sql
-- 在 novels 表中新增 planning_config 字段
ALTER TABLE novels ADD COLUMN planning_config TEXT;

-- planning_config 存储 JSON 格式：
-- {
--   "chapters_per_act": 5,
--   "acts_per_volume": 3,
--   "volumes_per_part": 2
-- }
```

### 数据迁移脚本

```python
# scripts/migrations/add_planning_config.py

import sqlite3
import json
from pathlib import Path

def migrate_planning_config(db_path: str):
    """为现有小说添加默认的 planning_config"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 获取所有没有 planning_config 的小说
    cursor.execute("""
        SELECT id FROM novels 
        WHERE planning_config IS NULL OR planning_config = ''
    """)
    
    novels = cursor.fetchall()
    
    default_config = {
        "chapters_per_act": 5,
        "acts_per_volume": 3,
        "volumes_per_part": 2
    }
    
    for (novel_id,) in novels:
        cursor.execute("""
            UPDATE novels 
            SET planning_config = ? 
            WHERE id = ?
        """, (json.dumps(default_config), novel_id))
    
    conn.commit()
    conn.close()
    
    print(f"已为 {len(novels)} 本小说添加默认 planning_config")

if __name__ == "__main__":
    from application.paths import get_db_path
    db_path = get_db_path()
    migrate_planning_config(db_path)
```

---

## 实施优先级

| 优先级 | 问题 | 解决方案 | 预计工作量 |
|--------|------|---------|-----------|
| **P0** | 规划覆盖冲突 | `confirm_act_planning` 增加 `force_overwrite` 参数 | 2小时 |
| **P0** | 判断已有规划 | `_handle_act_planning` 增加规划检查逻辑 | 3小时 |
| **P0** | 数量判断和补齐 | 增加 `_supplement_act_chapters` 方法 | 4小时 |
| **P1** | 动态节拍调整 | 创建 `BeatCalculator` 类并集成 | 3小时 |
| **P1** | 参数统一性 | Novel 实体增加 `PlanningConfig` | 2小时 |
| **P1** | 续写规划携带背景 | `continue_planning` 增加背景提取 | 4小时 |

**总计：约 18 小时（2-3 个工作日）**

---

## 测试计划

### 单元测试

```python
# tests/unit/application/blueprint/services/test_beat_calculator.py

import pytest
from application.blueprint.services.beat_calculator import BeatCalculator

def test_calculate_beat_count():
    """测试节拍数量计算"""
    assert BeatCalculator.calculate_beat_count(1000) == 3
    assert BeatCalculator.calculate_beat_count(2000) == 3
    assert BeatCalculator.calculate_beat_count(3500) == 4
    assert BeatCalculator.calculate_beat_count(5000) == 6
    assert BeatCalculator.calculate_beat_count(8000) == 7  # 上限

def test_calculate_words_per_beat():
    """测试每个节拍字数分配"""
    words = BeatCalculator.calculate_words_per_beat(3500, 4)
    assert len(words) == 4
    assert sum(words) == 3500
    assert all(w >= 800 for w in words)  # 每个节拍至少800字

def test_validate_beat_count():
    """测试节拍数量验证"""
    # 合理的配置
    is_valid, _ = BeatCalculator.validate_beat_count(3500, 4)
    assert is_valid
    
    # 节拍太少
    is_valid, reason = BeatCalculator.validate_beat_count(3500, 2)
    assert not is_valid
    assert "不能少于3个" in reason
    
    # 节拍太多
    is_valid, reason = BeatCalculator.validate_beat_count(3500, 10)
    assert not is_valid
    assert "不能超过7个" in reason
    
    # 平均字数太少
    is_valid, reason = BeatCalculator.validate_beat_count(1000, 5)
    assert not is_valid
    assert "低于最小值" in reason
```

