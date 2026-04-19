"""Base validator for LLM-based quality checks."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List
import json
import re
import logging

from domain.ai.value_objects.prompt import Prompt
from domain.ai.services.llm_service import GenerationConfig

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Validation issue."""
    type: str  # 问题类型
    severity: str  # 严重程度：critical|high|medium|low
    description: str  # 问题描述
    location: str = ""  # 问题位置（可选）


@dataclass
class ValidationResult:
    """Validation result."""
    is_valid: bool  # 是否通过验证
    issues: List[ValidationIssue]  # 问题列表
    suggestions: List[str]  # 修复建议
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据


class BaseValidator(ABC):
    """Validator base class."""

    def __init__(self, llm_service, config: Dict[str, Any] = None):
        self.llm_service = llm_service
        self.config = config or {}

    @abstractmethod
    async def validate(self, **kwargs) -> ValidationResult:
        """Execute validation."""
        pass

    @abstractmethod
    def _build_prompt(self, **kwargs) -> Prompt:
        """Build validation prompt."""
        pass

    async def _call_llm(self, prompt: Prompt) -> Dict[str, Any]:
        """Call LLM."""
        config = GenerationConfig(
            max_tokens=self.config.get("max_tokens", 800),
            temperature=self.config.get("temperature", 0.3),
        )
        result = await self.llm_service.generate(prompt, config)
        return self._parse_llm_response(result)

    def _parse_llm_response(self, response) -> Dict[str, Any]:
        """Parse LLM response."""
        # Extract content from response
        content = ""
        if hasattr(response, "content"):
            content = response.content
        else:
            content = str(response)

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            return {}
