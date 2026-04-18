from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

from application.ai.llm_control_service import LLMControlService, LLMProfile
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider
from infrastructure.ai.providers.gemini_provider import GeminiProvider
from infrastructure.ai.providers.mock_provider import MockProvider
from infrastructure.ai.providers.openai_provider import OpenAIProvider
from infrastructure.ai.url_utils import (
    normalize_anthropic_base_url,
    normalize_gemini_base_url,
    normalize_openai_base_url,
)

logger = logging.getLogger(__name__)
llm_trace_logger = logging.getLogger("plotpilot.llm")

_DEFAULT_CONFIG = GenerationConfig()


def _prompt_trace(prompt: Prompt) -> dict[str, Any]:
    return {
        "system_chars": len(prompt.system or ""),
        "user_chars": len(prompt.user or ""),
        "system": prompt.system or "",
        "user": prompt.user or "",
    }


def _config_trace(config: GenerationConfig) -> dict[str, Any]:
    return {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "temperature": config.temperature,
    }


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _json_block(value: Any) -> str:
    return f"```json\n{_pretty_json(value)}\n```"


def _section(title: str, content: str) -> str:
    return f"{title}:\n{content}"


def _text_block(text: str) -> str:
    body = text or ""
    if body:
        return f"```text\n{body}\n```"
    return "  <empty>"


def _trace_message(header: str, sections: list[tuple[str, str]]) -> str:
    lines = [header]
    for index, (title, content) in enumerate(sections):
        if index:
            lines.append("")
        lines.append(_section(title, content))
    return "\n".join(lines)


class LLMProviderFactory:
    def __init__(self, control_service: Optional[LLMControlService] = None):
        self.control_service = control_service or LLMControlService()

    def create_from_profile(self, profile: Optional[LLMProfile]) -> LLMService:
        if profile is None:
            return MockProvider()

        resolved = self.control_service.resolve_profile(profile)
        if not resolved.api_key.strip() or not resolved.model.strip():
            return MockProvider()

        settings = self._profile_to_settings(resolved)
        if resolved.protocol == 'anthropic':
            return AnthropicProvider(settings)
        if resolved.protocol == 'gemini':
            return GeminiProvider(settings)
        return OpenAIProvider(settings)

    def create_active_provider(self) -> LLMService:
        return self.create_from_profile(self.control_service.resolve_active_profile())

    def _profile_to_settings(self, profile: LLMProfile) -> Settings:
        if profile.protocol == 'anthropic':
            normalized_base_url = normalize_anthropic_base_url(profile.base_url)
        elif profile.protocol == 'gemini':
            normalized_base_url = normalize_gemini_base_url(profile.base_url)
        else:
            normalized_base_url = normalize_openai_base_url(profile.base_url)

        return Settings(
            default_model=profile.model,
            default_temperature=profile.temperature,
            default_max_tokens=profile.max_tokens,
            api_key=profile.api_key,
            base_url=normalized_base_url,
            timeout_seconds=profile.timeout_seconds,
            extra_headers=profile.extra_headers,
            extra_query=profile.extra_query,
            extra_body=profile.extra_body,
            provider_name=profile.name,
            protocol=profile.protocol,
            use_legacy_chat_completions=profile.use_legacy_chat_completions,
            profile_id=profile.id,
        )


class DynamicLLMService(LLMService):
    """动态读取当前激活配置，适配长生命周期服务/守护进程。"""

    def __init__(self, factory: Optional[LLMProviderFactory] = None):
        self.factory = factory or LLMProviderFactory()

    def _resolve_provider(self) -> LLMService:
        return self.factory.create_active_provider()

    @staticmethod
    def _merge_config(config: GenerationConfig, provider: LLMService) -> GenerationConfig:
        settings = getattr(provider, 'settings', None)
        if settings is None:
            return config

        model = config.model
        if not model or model == _DEFAULT_CONFIG.model:
            model = settings.default_model

        max_tokens = config.max_tokens
        if max_tokens == _DEFAULT_CONFIG.max_tokens:
            max_tokens = settings.default_max_tokens

        temperature = config.temperature
        if temperature == _DEFAULT_CONFIG.temperature:
            temperature = settings.default_temperature

        return GenerationConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        provider = self._resolve_provider()
        effective_config = self._merge_config(config, provider)
        provider_name = provider.__class__.__name__
        trace_enabled = llm_trace_logger.isEnabledFor(logging.INFO)
        if trace_enabled:
            llm_trace_logger.info(
                _trace_message(
                    "llm.generate start",
                    [
                        ("provider", provider_name),
                        ("config", _json_block(_config_trace(effective_config))),
                        (
                            "prompt",
                            _json_block(_prompt_trace(prompt)),
                        ),
                        ("system_prompt", _text_block(prompt.system or "")),
                        ("user_prompt", _text_block(prompt.user or "")),
                    ],
                ),
            )
        try:
            result = await provider.generate(prompt, effective_config)
            if trace_enabled:
                llm_trace_logger.info(
                    _trace_message(
                        "llm.generate end",
                        [
                            ("provider", provider_name),
                            ("output_chars", str(len(result.content or ""))),
                            (
                                "token_usage",
                                _json_block(
                                    {
                                        "input_tokens": getattr(result.token_usage, "input_tokens", None)
                                        if getattr(result, "token_usage", None)
                                        else None,
                                        "output_tokens": getattr(result.token_usage, "output_tokens", None)
                                        if getattr(result, "token_usage", None)
                                        else None,
                                    }
                                ),
                            ),
                            ("output", _text_block(result.content or "")),
                        ],
                    ),
                )
            return result
        except Exception as e:
            if trace_enabled:
                llm_trace_logger.warning(
                    _trace_message(
                        "llm.generate error",
                        [
                            ("provider", provider_name),
                            ("config", _json_block(_config_trace(effective_config))),
                            ("prompt_chars", str(len(prompt.user or ""))),
                            ("error_type", type(e).__name__),
                            ("error", str(e)),
                        ],
                    ),
                    exc_info=True,
                )
            raise

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        provider = self._resolve_provider()
        effective_config = self._merge_config(config, provider)
        provider_name = provider.__class__.__name__
        trace_enabled = llm_trace_logger.isEnabledFor(logging.INFO)
        if trace_enabled:
            llm_trace_logger.info(
                _trace_message(
                    "llm.stream start",
                    [
                        ("provider", provider_name),
                        ("config", _json_block(_config_trace(effective_config))),
                        ("prompt", _json_block(_prompt_trace(prompt))),
                        ("system_prompt", _text_block(prompt.system or "")),
                        ("user_prompt", _text_block(prompt.user or "")),
                    ],
                ),
            )
        output_parts: list[str] = []
        output_chars = 0
        try:
            async for chunk in provider.stream_generate(prompt, effective_config):
                text = chunk or ""
                output_chars += len(text)
                if trace_enabled:
                    output_parts.append(text)
                yield chunk
            if trace_enabled:
                llm_trace_logger.info(
                    _trace_message(
                        "llm.stream end",
                        [
                            ("provider", provider_name),
                            ("output_chars", str(output_chars)),
                            ("output", _text_block("".join(output_parts))),
                        ],
                    ),
                )
        except Exception as e:
            if trace_enabled:
                llm_trace_logger.warning(
                    _trace_message(
                        "llm.stream error",
                        [
                            ("provider", provider_name),
                            ("config", _json_block(_config_trace(effective_config))),
                            ("prompt_chars", str(len(prompt.user or ""))),
                            ("output_chars", str(output_chars)),
                            ("error_type", type(e).__name__),
                            ("error", str(e)),
                        ],
                    ),
                    exc_info=True,
                )
            raise
