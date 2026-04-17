"""章节融合 LLM 输出契约。"""
from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class FusionGenerationPayload(BaseModel):
    """章节融合生成结果。

    `facts_used` 要求逐条回填输入中的关键事实文本，便于服务端做缺失校验。
    """

    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, description="融合后的自然正文")
    facts_used: List[str] = Field(default_factory=list, description="正文已覆盖的关键事实")
    end_state: Dict[str, Any] = Field(default_factory=dict, description="正文收束时的终态")
    suspense_used: int = Field(default=0, ge=0, description="正文实际使用的悬念数")
    open_questions: List[str] = Field(default_factory=list, description="正文仍未解决的问题")
    model_warnings: List[str] = Field(default_factory=list, description="模型自报的风险或不足")


def fusion_generation_response_format() -> Dict[str, Any]:
    """构建结构化 JSON response_format。"""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "chapter_fusion_generation",
            "description": "章节融合稿生成结果，包含自然正文、事实覆盖、终态和风险信息。",
            "schema": FusionGenerationPayload.model_json_schema(mode="validation"),
            "strict": True,
        },
    }
