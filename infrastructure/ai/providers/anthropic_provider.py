"""Anthropic LLM 提供商实现"""
from typing import AsyncIterator, Optional
from anthropic import Anthropic
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider


class AnthropicProvider(BaseProvider):
    """Anthropic LLM 提供商实现

    使用 Anthropic API 实现 LLM 服务。
    """

    def __init__(self, settings: Settings):
        """初始化 Anthropic 提供商

        Args:
            settings: AI 配置设置

        Raises:
            ValueError: 如果 API key 未设置
        """
        super().__init__(settings)

        if not settings.api_key:
            raise ValueError("API key is required for AnthropicProvider")

        self.client = Anthropic(api_key=settings.api_key)

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成文本

        Args:
            prompt: 提示词
            config: 生成配置

        Returns:
            生成结果
        """
        # 调用 Anthropic API
        response = self.client.messages.create(
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            system=prompt.system,
            messages=prompt.to_messages()
        )

        # 提取响应内容
        content = response.content[0].text

        # 创建 token 使用统计
        token_usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens
        )

        return GenerationResult(content=content, token_usage=token_usage)
