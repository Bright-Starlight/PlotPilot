"""Character reaction validator."""
from typing import Dict, Any, List
import logging

from domain.ai.value_objects.prompt import Prompt
from .base_validator import BaseValidator, ValidationResult, ValidationIssue

logger = logging.getLogger(__name__)


class CharacterReactionValidator(BaseValidator):
    """人物反应验证器"""

    async def validate(
        self,
        chapter_content: str,
        key_characters: List[str],
        key_events: List[str],
    ) -> ValidationResult:
        """验证人物反应完整性"""

        prompt = self._build_prompt(
            chapter_content,
            key_characters,
            key_events,
        )

        try:
            result = await self._call_llm(prompt)

            missing_reactions = result.get("missing_reactions", [])
            issues = [
                ValidationIssue(
                    type="missing_reaction",
                    severity=reaction.get("severity", "medium"),
                    description=f"{reaction.get('character')}对\"{reaction.get('event')}\"缺少反应：{reaction.get('reason')}",
                )
                for reaction in missing_reactions
            ]

            return ValidationResult(
                is_valid=result.get("all_reacted", False),
                issues=issues,
                suggestions=result.get("suggestions", []),
                metadata={"validator": "character_reaction"},
            )

        except Exception as e:
            logger.error(f"人物反应验证失败: {e}")
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"error": str(e)},
            )

    def _build_prompt(
        self,
        content: str,
        characters: List[str],
        events: List[str],
    ) -> Prompt:
        """构建验证提示词"""

        system = """你是小说人物反应审查专家。你的任务是检查关键人物对关键事件是否有合理反应。

合理反应包括：
1. 语言反应（台词、对话）
2. 动作反应（肢体动作、表情）
3. 心理反应（内心独白、情绪变化）
4. 生理反应（呼吸、心跳、冷汗等）

特别注意：
- 在场的关键人物必须有反应
- 反应应该符合人物性格和当前情境
- 不是所有人物都需要对所有事件反应，但重要人物对重要事件必须有反应

输出JSON格式：
{
  "all_reacted": true/false,
  "missing_reactions": [
    {
      "character": "人物名",
      "event": "事件描述",
      "severity": "critical|high|medium",
      "reason": "为什么这个人物应该有反应"
    }
  ],
  "suggestions": ["建议在XX处增加XX的反应", ...]
}

严重程度定义：
- critical: 关键人物对核心事件完全没有反应
- high: 重要人物对重要事件缺少反应
- medium: 次要人物或次要事件的反应缺失"""

        char_list = "、".join(characters)
        event_list = "\n".join(f"- {e}" for e in events)

        user = f"""章节正文：
{content}

关键人物：{char_list}

关键事件：
{event_list}

请检查每个关键人物对每个关键事件是否有合理反应，输出JSON。"""

        return Prompt(system=system, user=user)
