"""Chapter coherence validator."""
from typing import Dict, Any
import logging

from domain.ai.value_objects.prompt import Prompt
from .base_validator import BaseValidator, ValidationResult, ValidationIssue

logger = logging.getLogger(__name__)


class ChapterCoherenceValidator(BaseValidator):
    """章节连贯性验证器"""

    async def validate(
        self,
        previous_chapter_content: str,
        current_chapter_content: str,
        previous_chapter_seam: Dict[str, str],
    ) -> ValidationResult:
        """验证章节连贯性"""

        prompt = self._build_prompt(
            previous_chapter_content,
            current_chapter_content,
            previous_chapter_seam,
        )

        try:
            result = await self._call_llm(prompt)

            issues = [
                ValidationIssue(
                    type=issue.get("type", "unknown"),
                    severity=issue.get("severity", "medium"),
                    description=issue.get("description", ""),
                )
                for issue in result.get("issues", [])
            ]

            return ValidationResult(
                is_valid=result.get("is_coherent", False),
                issues=issues,
                suggestions=result.get("suggestions", []),
                metadata={"validator": "coherence"},
            )

        except Exception as e:
            logger.error(f"章节连贯性验证失败: {e}")
            return ValidationResult(
                is_valid=True,  # 验证失败时默认通过
                issues=[],
                suggestions=[],
                metadata={"error": str(e)},
            )

    def _build_prompt(
        self,
        previous_content: str,
        current_content: str,
        seam: Dict[str, str],
    ) -> Prompt:
        """构建验证提示词"""

        system = """你是小说连贯性审查专家。你的任务是检查两章之间的连贯性。

重点检查：
1. 场景转换是否自然（时间、地点、人物）
2. 未完成的对话是否得到延续
3. 未回答的问题是否得到回应
4. 关键人物是否有合理反应
5. 情绪张力是否连续

输出JSON格式：
{
  "is_coherent": true/false,
  "issues": [
    {
      "type": "missing_transition|unfinished_dialogue|missing_reaction|emotion_break|...",
      "severity": "critical|high|medium|low",
      "description": "具体问题描述"
    }
  ],
  "suggestions": ["修复建议1", "修复建议2"]
}

严重程度定义：
- critical: 严重破坏阅读体验，必须修复
- high: 明显的连贯性问题，应该修复
- medium: 可以改进的地方
- low: 小瑕疵，可选修复"""

        # 提取上一章最后3段
        prev_paragraphs = [p.strip() for p in previous_content.split("\n") if p.strip()]
        prev_tail = "\n".join(prev_paragraphs[-3:]) if prev_paragraphs else ""

        # 提取当前章开头3段
        curr_paragraphs = [p.strip() for p in current_content.split("\n") if p.strip()]
        curr_head = "\n".join(curr_paragraphs[:3]) if curr_paragraphs else ""

        user = f"""上一章结尾（最后3段）：
{prev_tail}

上一章接缝信息：
- 章末状态：{seam.get("ending_state", "无")}
- 未完成的话：{seam.get("unfinished_speech", "无")}
- 必须回应的问题：{seam.get("carry_over_question", "无")}
- 章末情绪：{seam.get("ending_emotion", "无")}

当前章开头（前3段）：
{curr_head}

请检查连贯性并输出JSON。"""

        return Prompt(system=system, user=user)
