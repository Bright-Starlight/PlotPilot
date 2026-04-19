"""Suspense resolution validator."""
from typing import Dict, Any, List
import logging

from domain.ai.value_objects.prompt import Prompt
from .base_validator import BaseValidator, ValidationResult, ValidationIssue

logger = logging.getLogger(__name__)


class SuspenseResolutionValidator(BaseValidator):
    """悬念解答验证器"""

    async def validate(
        self,
        previous_suspense: List[str],
        current_chapter_content: str,
    ) -> ValidationResult:
        """验证悬念解答"""

        if not previous_suspense:
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"validator": "suspense_resolution", "note": "无悬念需要验证"},
            )

        prompt = self._build_prompt(
            previous_suspense,
            current_chapter_content,
        )

        try:
            result = await self._call_llm(prompt)

            unhandled = result.get("unhandled_suspense", [])
            issues = [
                ValidationIssue(
                    type=f"suspense_{item.get('status', 'unhandled')}",
                    severity=item.get("severity", "medium"),
                    description=f"悬念\"{item.get('suspense')}\"未处理：{item.get('reason')}",
                )
                for item in unhandled
            ]

            return ValidationResult(
                is_valid=result.get("all_handled", False),
                issues=issues,
                suggestions=result.get("suggestions", []),
                metadata={"validator": "suspense_resolution"},
            )

        except Exception as e:
            logger.error(f"悬念解答验证失败: {e}")
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"error": str(e)},
            )

    def _build_prompt(
        self,
        suspense_list: List[str],
        content: str,
    ) -> Prompt:
        """构建验证提示词"""

        system = """你是小说悬念处理审查专家。你的任务是检查上一章的悬念在本章是否得到合理处理。

合理处理包括：
1. 直接解答（给出答案）
2. 部分解答（给出线索）
3. 合理延续（有意保留，但有新进展）
4. 转移焦点（用更大悬念覆盖）

不合理处理：
1. 完全忽略（没有任何提及）
2. 突兀跳过（没有过渡就换话题）

输出JSON格式：
{
  "all_handled": true/false,
  "unhandled_suspense": [
    {
      "suspense": "悬念内容",
      "status": "ignored|abruptly_skipped",
      "severity": "critical|high|medium",
      "reason": "为什么这个悬念应该被处理"
    }
  ],
  "suggestions": ["建议在XX处回应XX悬念", ...]
}

严重程度定义：
- critical: 核心悬念被完全忽略
- high: 重要悬念被突兀跳过
- medium: 次要悬念处理不够充分"""

        suspense_text = "\n".join(f"- {s}" for s in suspense_list)

        user = f"""上一章留下的悬念：
{suspense_text}

本章正文：
{content}

请检查每个悬念是否得到合理处理，输出JSON。"""

        return Prompt(system=system, user=user)
