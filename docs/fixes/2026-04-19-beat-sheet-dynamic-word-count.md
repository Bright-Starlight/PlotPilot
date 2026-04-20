# 节拍表动态字数配置修复

> 修复日期：2026-04-19
> 问题：节拍生成提示词中的预估字数是硬编码的（500-1000字），未根据小说的全局配置动态调整

## 问题描述

### 原问题

在 `application/blueprint/services/beat_sheet_service.py` 的 `_build_beat_sheet_prompt` 方法中，提示词硬编码了：

```python
5. 预估字数（每个场景 500-1000 字）
...
- 预估字数总和应该在 2000-4000 字之间
```

这导致：
1. 所有小说的节拍字数都是固定的，无法适应不同小说的字数需求
2. 对于短篇小说（如 `novel-1776499481673` 的 1000 字/章），生成的节拍字数过多
3. 对于长篇小说（如 3500 字/章），生成的节拍字数可能不足

### 小说配置

每个小说在 `novels` 表中有 `target_words_per_chapter` 字段：

```sql
SELECT id, title, target_words_per_chapter FROM novels WHERE id = 'novel-1776499481673';
-- 结果：novel-1776499481673|《大明改命人》|1000
```

## 修复方案

### 修改1：`generate_beat_sheet` 方法

**文件**：`application/blueprint/services/beat_sheet_service.py:50-118`

**修改内容**：

1. 在生成节拍表前，获取章节信息和小说配置
2. 从小说配置中读取 `target_words_per_chapter`
3. 将目标字数传递给 `_build_beat_sheet_prompt` 方法

```python
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
logger.info(f"Target words per chapter: {target_words_per_chapter}")

# 2. 构建提示词（传入目标字数）
prompt = self._build_beat_sheet_prompt(outline, context, target_words_per_chapter)
```

### 修改2：`_build_beat_sheet_prompt` 方法

**文件**：`application/blueprint/services/beat_sheet_service.py:360-396`

**修改内容**：

1. 添加 `target_words_per_chapter` 参数（默认值 3500）
2. 动态计算每个场景的字数范围
3. 动态计算总字数范围
4. 在提示词中使用动态计算的值

```python
def _build_beat_sheet_prompt(
    self,
    outline: str,
    context: Dict,
    target_words_per_chapter: int = 3500
) -> Prompt:
    """构建节拍表生成提示词（使用增强的上下文）

    Args:
        outline: 章节大纲
        context: 上下文信息
        target_words_per_chapter: 目标章节字数（从小说配置获取）
    """

    # 动态计算场景字数范围
    # 假设 3-5 个场景，计算每个场景的合理字数范围
    min_scenes = 3
    max_scenes = 5
    min_words_per_scene = target_words_per_chapter // max_scenes  # 例如：1000 / 5 = 200
    max_words_per_scene = target_words_per_chapter // min_scenes  # 例如：1000 / 3 = 333
    total_words_min = int(target_words_per_chapter * 0.8)  # 80% 的目标字数
    total_words_max = int(target_words_per_chapter * 1.2)  # 120% 的目标字数

    system_prompt = f"""你是一位专业的小说编剧，擅长将章节大纲拆解为具体的场景（Scene）。

⚠️ 核心原则：必须严格遵循章节大纲，不得偏离大纲的核心场景、任务和终态。

你的任务是将章节大纲拆解为 3-5 个场景，每个场景应该：
1. 有明确的场景目标（Scene Goal）
2. 指定 POV 角色（从哪个角色的视角叙述）
3. 指定地点（可选）
4. 指定情绪基调（例如：紧张、温馨、悲伤、激烈）
5. 预估字数（每个场景 {min_words_per_scene}-{max_words_per_scene} 字）

...

注意事项：
- 场景之间要有逻辑连贯性
- 每个场景聚焦一个明确目标，避免贪多
- POV 角色应该是章节中的主要角色
- 预估字数总和应该在 {total_words_min}-{total_words_max} 字之间（目标：{target_words_per_chapter} 字）
- 充分利用提供的上下文信息（人物、故事线、伏笔、地点、时间线）
"""
```

## 效果对比

### 修改前

**所有小说**：
- 每个场景：500-1000 字
- 总字数：2000-4000 字

### 修改后

**小说 A（target_words_per_chapter = 1000）**：
- 每个场景：200-333 字
- 总字数：800-1200 字

**小说 B（target_words_per_chapter = 3500）**：
- 每个场景：700-1166 字
- 总字数：2800-4200 字

**小说 C（target_words_per_chapter = 5000）**：
- 每个场景：1000-1666 字
- 总字数：4000-6000 字

## 额外改进

在修改提示词时，还加入了以下改进：

### 1. 强化大纲遵循约束

```python
⚠️ 核心原则：必须严格遵循章节大纲，不得偏离大纲的核心场景、任务和终态。

⚠️ 严格约束：
- 场景必须在大纲指定的地点发生
- 场景必须推进大纲指定的任务
- 场景必须包含大纲指定的冲突
- 最后一个场景的终态必须与大纲的终态一致
- 上下文信息（故事线、伏笔）仅作为参考，不得替代大纲内容
```

这个改进可以解决第31章节拍草稿偏离大纲的问题。

## 测试验证

运行单元测试：

```bash
python -m pytest tests/unit/application/services/test_beat_sheet_service.py -v
```

结果：
```
tests/unit/application/services/test_beat_sheet_service.py::test_generate_beat_sheet_requires_state_lock_version PASSED
tests/unit/application/services/test_beat_sheet_service.py::test_retrieve_relevant_context_accepts_timeline_event_without_description PASSED

2 passed, 2 warnings in 0.24s
```

## 后续建议

### 1. 重新生成第31章节拍草稿

由于第31章的节拍草稿是用旧版本生成的，建议重新生成：

```sql
-- 1. 删除旧节拍草稿
DELETE FROM beat_sheets WHERE chapter_id = 'chapter-novel-1776499481673-chapter-31';

-- 2. 通过 API 重新生成
POST /api/v1/beat-sheets/generate
{
  "chapter_id": "chapter-novel-1776499481673-chapter-31",
  "outline": "海禁迷渊曾是繁华的走私港口...",
  "state_lock_version": 1
}
```

### 2. 验证其他章节

检查其他章节的节拍表是否也需要重新生成：

```sql
SELECT 
    bs.chapter_id,
    c.number,
    c.title,
    SUM(json_extract(scene.value, '$.estimated_words')) as total_words,
    n.target_words_per_chapter
FROM beat_sheets bs
JOIN chapters c ON bs.chapter_id = c.id
JOIN novels n ON c.novel_id = n.id,
json_each(json_extract(bs.data, '$.scenes')) as scene
GROUP BY bs.chapter_id
HAVING total_words > n.target_words_per_chapter * 1.5 
    OR total_words < n.target_words_per_chapter * 0.5;
```

## 相关文档

- [第31章大纲与融合草稿差异分析](../chapter-coherence-optimization.md)
- [节拍表生成服务](../../application/blueprint/services/beat_sheet_service.py)
