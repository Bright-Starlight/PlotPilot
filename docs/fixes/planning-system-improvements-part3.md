# 规划系统改进方案（第3部分）

## 获取小说背景设定

### 从 StoryKnowledge 提取背景信息

```python
# application/blueprint/services/continuous_planning_service.py

async def _get_novel_background(self, novel_id: str) -> Dict[str, Any]:
    """获取小说的完整背景设定
    
    从 StoryKnowledge 中提取：
    - premise_lock: 梗概锁定（新书设置向导生成的故事设定）
    - 核心设定三元组
    
    Returns:
        {
            "premise_lock": "小说梗概",
            "world_setting": "世界观设定",
            "core_conflicts": "核心冲突",
            "character_relationships": "角色关系"
        }
    """
    background = {
        "premise_lock": "",
        "world_setting": "",
        "core_conflicts": "",
        "character_relationships": ""
    }
    
    try:
        # 获取 StoryKnowledge
        knowledge = self.knowledge_service.get_knowledge(novel_id)
        
        # 1. 梗概锁定（最重要的背景信息）
        if knowledge.premise_lock:
            background["premise_lock"] = knowledge.premise_lock
        
        # 2. 从知识三元组中提取核心设定
        if knowledge.facts:
            # 提取世界观设定
            world_facts = [
                f for f in knowledge.facts 
                if f.predicate in ["世界观", "设定", "背景", "时代"]
            ]
            if world_facts:
                background["world_setting"] = "\n".join(
                    f"- {f.subject} {f.predicate} {f.object}" 
                    for f in world_facts[:5]
                )
            
            # 提取核心冲突
            conflict_facts = [
                f for f in knowledge.facts 
                if f.predicate in ["冲突", "对立", "矛盾", "敌对"]
            ]
            if conflict_facts:
                background["core_conflicts"] = "\n".join(
                    f"- {f.subject} {f.predicate} {f.object}" 
                    for f in conflict_facts[:5]
                )
            
            # 提取角色关系
            relation_facts = [
                f for f in knowledge.facts 
                if f.predicate in ["关系", "是", "属于", "师徒", "朋友", "敌人"]
            ]
            if relation_facts:
                background["character_relationships"] = "\n".join(
                    f"- {f.subject} {f.predicate} {f.object}" 
                    for f in relation_facts[:10]
                )
        
    except Exception as e:
        logger.warning(f"获取小说背景设定失败: {e}")
    
    return background

async def _summarize_recent_chapters(self, chapters: List[Chapter]) -> str:
    """总结最近章节的内容和趋势"""
    summaries = []
    for ch in chapters:
        if ch.content:
            # 提取章节摘要（可以调用 LLM 或使用已有的 state）
            summary = f"第{ch.number}章《{ch.title}》: {ch.content[:200]}..."
            summaries.append(summary)
    return "\n".join(summaries)

async def _get_pending_foreshadowings(self, novel_id: str) -> List[Dict]:
    """获取待回收伏笔"""
    if not self.foreshadowing_repository:
        return []
    
    all_foreshadowings = self.foreshadowing_repository.get_by_novel_id(novel_id)
    # 筛选未回收的伏笔
    pending = [f for f in all_foreshadowings if not f.is_resolved]
    return [
        {"description": f.description, "chapter": f.chapter_number} 
        for f in pending
    ]
```

### 构建续写规划提示词

```python
def _build_continue_planning_prompt(
    self,
    novel_premise: str,  # 新增
    novel_background: Dict[str, Any],  # 新增
    recent_summary: str,
    bible_context: Dict,
    pending_foreshadowings: List[Dict],
    target_count: int,
    last_chapter_number: int
) -> Prompt:
    """构建续写规划提示词（携带完整背景）"""
    system_msg = """你是专业的小说续写规划助手。
你的任务是基于小说的背景设定、已写章节的内容和趋势，规划后续章节的发展。
必须确保：
1. 严格遵循小说的背景设定和世界观
2. 延续已有剧情的逻辑和风格
3. 回收待解决的伏笔
4. 推进主要故事线
5. 保持角色行为的一致性"""
    
    # 构建背景信息部分
    background_section = f"""=== 小说背景设定 ===
梗概：{novel_premise or '无'}

故事设定：
{novel_background.get('premise_lock', '无')}

世界观：
{novel_background.get('world_setting', '无')}

核心冲突：
{novel_background.get('core_conflicts', '无')}

角色关系：
{novel_background.get('character_relationships', '无')}
"""
    
    user_msg = f"""{background_section}

=== 最近章节摘要 ===
{recent_summary}

=== 待回收伏笔 ===
{chr(10).join(f"- {f['description']} (第{f['chapter']}章埋下)" for f in pending_foreshadowings) if pending_foreshadowings else '无'}

=== 可用人物 ===
{chr(10).join(f"- {c['name']}: {c.get('description', '')[:50]}" for c in bible_context.get('characters', [])[:10])}

=== 可用地点 ===
{chr(10).join(f"- {l['name']}: {l.get('description', '')[:50]}" for c in bible_context.get('locations', [])[:10])}

请基于以上信息，规划后续 {target_count} 个章节（从第 {last_chapter_number + 1} 章开始）。

⚠️ 重要约束：
1. 必须严格遵循「小说背景设定」中的世界观和核心冲突
2. 必须延续「最近章节摘要」中的剧情逻辑
3. 优先回收「待回收伏笔」
4. 合理使用「可用人物」和「可用地点」

输出 JSON 格式：
{{
  "acts": [
    {{
      "title": "幕标题",
      "description": "幕描述",
      "suggested_chapter_count": 5,
      "chapters": [
        {{
          "number": {last_chapter_number + 1},
          "title": "章节标题",
          "outline": "章节大纲（100-200字）",
          "description": "章节简介"
        }}
      ]
    }}
  ]
}}"""
    
    return Prompt(system=system_msg, user=user_msg)
```

---

## 方案 5：动态节拍数量调整

### 节拍计算器

```python
# application/blueprint/services/beat_calculator.py (新建文件)

class BeatCalculator:
    """节拍数量计算器"""
    
    # 节拍字数范围配置
    MIN_WORDS_PER_BEAT = 600   # 每个节拍最少600字
    MAX_WORDS_PER_BEAT = 1200  # 每个节拍最多1200字
    IDEAL_WORDS_PER_BEAT = 800 # 理想每个节拍800字
    
    @staticmethod
    def calculate_beat_count(target_words_per_chapter: int) -> int:
        """根据章节字数计算合理的节拍数量
        
        Args:
            target_words_per_chapter: 目标章节字数
        
        Returns:
            建议的节拍数量（3-7个）
        
        Examples:
            1000字 -> 3个节拍
            2000字 -> 3个节拍
            3500字 -> 4个节拍
            5000字 -> 6个节拍
            8000字 -> 7个节拍（上限）
        """
        if target_words_per_chapter <= 0:
            return 3  # 默认最少3个节拍
        
        # 基于理想字数计算
        ideal_count = target_words_per_chapter / BeatCalculator.IDEAL_WORDS_PER_BEAT
        
        # 四舍五入并限制范围
        beat_count = round(ideal_count)
        beat_count = max(3, min(7, beat_count))  # 限制在 3-7 个节拍
        
        return beat_count
    
    @staticmethod
    def calculate_words_per_beat(
        target_words_per_chapter: int, 
        beat_count: int
    ) -> List[int]:
        """计算每个节拍的目标字数
        
        Args:
            target_words_per_chapter: 目标章节字数
            beat_count: 节拍数量
        
        Returns:
            每个节拍的目标字数列表
        
        Example:
            calculate_words_per_beat(3500, 4) -> [875, 875, 875, 875]
            calculate_words_per_beat(3502, 4) -> [876, 876, 875, 875]
        """
        if beat_count <= 0:
            return []
        
        # 平均分配
        avg_words = target_words_per_chapter // beat_count
        remainder = target_words_per_chapter % beat_count
        
        # 前面的节拍多分配余数
        words_per_beat = [avg_words] * beat_count
        for i in range(remainder):
            words_per_beat[i] += 1
        
        return words_per_beat
    
    @staticmethod
    def validate_beat_count(
        target_words_per_chapter: int,
        beat_count: int
    ) -> tuple[bool, str]:
        """验证节拍数量是否合理
        
        Args:
            target_words_per_chapter: 目标章节字数
            beat_count: 节拍数量
        
        Returns:
            (是否合理, 原因说明)
        """
        if beat_count < 3:
            return False, "节拍数量不能少于3个"
        
        if beat_count > 7:
            return False, "节拍数量不能超过7个"
        
        avg_words = target_words_per_chapter / beat_count
        
        if avg_words < BeatCalculator.MIN_WORDS_PER_BEAT:
            return False, f"平均每个节拍仅{avg_words:.0f}字，低于最小值{BeatCalculator.MIN_WORDS_PER_BEAT}字"
        
        if avg_words > BeatCalculator.MAX_WORDS_PER_BEAT:
            return False, f"平均每个节拍{avg_words:.0f}字，超过最大值{BeatCalculator.MAX_WORDS_PER_BEAT}字"
        
        return True, "节拍数量合理"
```

### 使用示例

```python
# 使用示例
def get_beat_count_for_chapter(chapter: Chapter, novel: Novel) -> int:
    """获取章节的节拍数量"""
    target_words = novel.target_words_per_chapter or 3500
    return BeatCalculator.calculate_beat_count(target_words)

# 验证示例
target_words = 1000
beat_count = 5
is_valid, reason = BeatCalculator.validate_beat_count(target_words, beat_count)
if not is_valid:
    print(f"警告: {reason}")
    # 使用推荐的节拍数
    beat_count = BeatCalculator.calculate_beat_count(target_words)
```

