# 规划系统改进方案（第2部分）

## 章节补齐功能实现

### 补齐规划方法

```python
# application/engine/services/autopilot_daemon.py

async def _supplement_act_chapters(
    self,
    novel: Novel,
    target_act,
    existing_chapters: List,
    shortage_count: int
) -> None:
    """补齐幕的章节规划
    
    Args:
        novel: 小说实体
        target_act: 目标幕节点
        existing_chapters: 已有章节列表
        shortage_count: 缺少的章节数量
    """
    logger.info(
        f"[{novel.novel_id}] 开始补齐幕 {target_act.number} 的章节规划，"
        f"需要补充 {shortage_count} 章"
    )
    
    # 1. 获取最后一章的信息作为续写起点
    existing_chapters.sort(key=lambda c: c.number)
    last_chapter = existing_chapters[-1]
    last_chapter_summary = (
        last_chapter.outline or 
        last_chapter.description or 
        last_chapter.title or 
        "无"
    )
    
    # 2. 获取上下文
    bible_context = self.planning_service._get_bible_context(novel.novel_id.value)
    
    # 3. 构建补齐规划提示词
    prompt = self._build_supplement_chapters_prompt(
        act_node=target_act,
        last_chapter_number=last_chapter.number,
        last_chapter_summary=last_chapter_summary,
        bible_context=bible_context,
        shortage_count=shortage_count
    )
    
    # 4. 调用 LLM 生成补充章节
    try:
        response = await self.llm_service.generate(
            prompt,
            GenerationConfig(max_tokens=4096, temperature=0.7)
        )
        
        from application.ai.structured_json_pipeline import parse_and_repair_json
        plan = parse_and_repair_json(
            response.content if hasattr(response, 'content') else str(response)
        )
        
        supplement_chapters = plan.get("chapters", [])
        
        if not supplement_chapters:
            logger.warning(f"[{novel.novel_id}] 补齐规划未生成章节，使用占位章节")
            supplement_chapters = self._fallback_supplement_chapters(
                target_act, 
                last_chapter.number, 
                shortage_count
            )
        
        # 5. 确认补充的章节规划
        await self.planning_service.confirm_act_planning(
            act_id=target_act.id,
            chapters=supplement_chapters,
            force_overwrite=False  # 不覆盖已有章节
        )
        
        logger.info(f"[{novel.novel_id}] 成功补齐 {len(supplement_chapters)} 章")
        
    except Exception as e:
        logger.error(f"[{novel.novel_id}] 补齐章节规划失败: {e}", exc_info=True)
        # 降级：使用占位章节
        fallback_chapters = self._fallback_supplement_chapters(
            target_act, 
            last_chapter.number, 
            shortage_count
        )
        await self.planning_service.confirm_act_planning(
            act_id=target_act.id,
            chapters=fallback_chapters,
            force_overwrite=False
        )

def _build_supplement_chapters_prompt(
    self,
    act_node,
    last_chapter_number: int,
    last_chapter_summary: str,
    bible_context: Dict,
    shortage_count: int
) -> Prompt:
    """构建补齐章节的提示词"""
    system_msg = """你是专业的小说章节规划助手。
你的任务是基于已有章节的内容，补充后续章节的规划。
必须确保：
1. 延续已有章节的剧情逻辑
2. 推进幕的整体目标
3. 保持章节编号连续"""
    
    user_msg = f"""幕信息：《{act_node.title}》
幕描述：{act_node.description or '无'}

最后一章（第 {last_chapter_number} 章）：
{last_chapter_summary}

可用人物：
{chr(10).join(f"- {c['name']}" for c in bible_context.get('characters', [])[:10])}

请补充后续 {shortage_count} 个章节（从第 {last_chapter_number + 1} 章开始）。

输出 JSON 格式：
{{
  "chapters": [
    {{
      "number": {last_chapter_number + 1},
      "title": "章节标题",
      "description": "章节简介",
      "outline": "章节大纲（100-200字）"
    }}
  ]
}}"""
    
    return Prompt(system=system_msg, user=user_msg)

def _fallback_supplement_chapters(
    self,
    act_node,
    last_chapter_number: int,
    shortage_count: int
) -> List[Dict]:
    """降级：生成占位补充章节"""
    chapters = []
    for i in range(shortage_count):
        chapter_num = last_chapter_number + i + 1
        chapters.append({
            "number": chapter_num,
            "title": f"第 {chapter_num} 章（待规划）",
            "description": f"继续推进《{act_node.title}》的剧情",
            "outline": f"本章将继续发展幕的核心冲突和目标"
        })
    return chapters
```

---

## 方案 3：参数统一性

### 在 Novel 实体中增加全局配置

```python
# domain/novel/entities/novel.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class PlanningConfig:
    """规划配置（全局统一）"""
    chapters_per_act: int = 5  # 每幕章节数（默认5）
    acts_per_volume: int = 3   # 每卷幕数（默认3）
    volumes_per_part: int = 2  # 每部卷数（默认2）
    
    # 动态计算
    @property
    def chapters_per_volume(self) -> int:
        return self.chapters_per_act * self.acts_per_volume
    
    @property
    def chapters_per_part(self) -> int:
        return self.chapters_per_volume * self.volumes_per_part

class Novel(BaseEntity):
    """小说聚合根"""
    
    def __init__(
        self,
        # ... 现有参数 ...
        planning_config: Optional[PlanningConfig] = None,  # 新增
    ):
        # ... 现有代码 ...
        self.planning_config = planning_config or PlanningConfig()
```

### 使用统一配置

```python
# autopilot_daemon.py
def _get_default_chapter_count(self, novel: Novel) -> int:
    """获取默认章节数（使用全局配置）"""
    if novel.planning_config:
        return novel.planning_config.chapters_per_act
    return 5  # 降级默认值

# continuous_planning_service.py
async def plan_act_chapters(
    self, 
    act_id: str, 
    custom_chapter_count: Optional[int] = None
) -> Dict:
    act_node = await self.story_node_repo.get_by_id(act_id)
    if not act_node:
        raise ValueError(f"幕节点不存在: {act_id}")
    
    # 优先级：custom > act_node.suggested > novel.planning_config > 默认5
    novel = self.novel_repository.get_by_id(NovelId(act_node.novel_id))
    chapter_count = (
        custom_chapter_count 
        or act_node.suggested_chapter_count 
        or (novel.planning_config.chapters_per_act if novel and novel.planning_config else None)
        or 5
    )
    
    # ... 继续规划逻辑
```

---

## 方案 4：续写规划功能（携带小说背景设定）

### 续写规划主方法

```python
# application/blueprint/services/continuous_planning_service.py

async def continue_planning(
    self, 
    novel_id: str,
    target_chapter_count: int = 10
) -> Dict:
    """续写规划：基于已写章节内容 + 小说背景设定生成后续规划
    
    Args:
        novel_id: 小说ID
        target_chapter_count: 续写目标章节数
    
    Returns:
        续写规划结果
    """
    # 1. 获取小说实体（包含 premise 等背景信息）
    novel = self.novel_repository.get_by_id(NovelId(novel_id))
    if not novel:
        raise ValueError(f"小说不存在: {novel_id}")
    
    # 2. 获取小说的完整背景设定（从 StoryKnowledge）
    novel_background = await self._get_novel_background(novel_id)
    
    # 3. 获取已写章节的摘要
    written_chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
    written_chapters.sort(key=lambda c: c.number)
    
    if not written_chapters:
        raise ValueError("无已写章节，无法续写规划")
    
    # 4. 提取最近章节的状态和趋势
    recent_chapters = written_chapters[-5:]
    recent_summary = await self._summarize_recent_chapters(recent_chapters)
    
    # 5. 获取 Bible 上下文
    bible_context = self._get_bible_context(novel_id)
    
    # 6. 获取待回收伏笔
    pending_foreshadowings = await self._get_pending_foreshadowings(novel_id)
    
    # 7. 构建续写规划提示词（携带完整背景）
    prompt = self._build_continue_planning_prompt(
        novel_premise=novel.premise,  # 新增：小说梗概
        novel_background=novel_background,  # 新增：完整背景设定
        recent_summary=recent_summary,
        bible_context=bible_context,
        pending_foreshadowings=pending_foreshadowings,
        target_count=target_chapter_count,
        last_chapter_number=written_chapters[-1].number
    )
    
    # 8. 调用 LLM 生成续写规划
    response = await self.llm_service.generate(
        prompt, 
        GenerationConfig(max_tokens=4096, temperature=0.7)
    )
    
    plan = self._parse_llm_response(response)
    
    # 9. 创建新的幕/卷（如果需要）并确认规划
    return await self._confirm_continue_planning(novel_id, plan)
```

