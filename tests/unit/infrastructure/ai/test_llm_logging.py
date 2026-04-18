import logging

import pytest

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.provider_factory import DynamicLLMService
from interfaces.api.middleware.logging_config import setup_logging


def test_setup_logging_creates_separate_llm_log_file(tmp_path, monkeypatch):
    llm_log_file = tmp_path / "llm_trace.log"
    monkeypatch.setenv("LLM_LOG_FILE", str(llm_log_file))

    setup_logging(level=logging.INFO, log_file=None)

    logger = logging.getLogger("plotpilot.llm")
    logger.info("llm trace hello")
    for handler in logger.handlers:
        handler.flush()

    assert llm_log_file.exists()
    assert "llm trace hello" in llm_log_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_dynamic_llm_service_logs_generate_and_stream(tmp_path, monkeypatch):
    llm_log_file = tmp_path / "llm_trace.log"
    monkeypatch.setenv("LLM_LOG_FILE", str(llm_log_file))
    setup_logging(level=logging.INFO, log_file=None)

    class _FakeProvider:
        def __init__(self):
            self.settings = Settings(
                default_model="test-model",
                default_temperature=0.25,
                default_max_tokens=111,
            )

        async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
            assert prompt.user == "user prompt"
            assert config.model == "test-model"
            return GenerationResult(
                content="response text",
                token_usage=TokenUsage(input_tokens=12, output_tokens=7),
            )

        async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
            assert prompt.user == "stream prompt"
            assert config.max_tokens == 111
            yield "chunk-1"
            yield "chunk-2"

    class _FakeFactory:
        def create_active_provider(self):
            return _FakeProvider()

    service = DynamicLLMService(factory=_FakeFactory())

    result = await service.generate(
        Prompt(system="system prompt", user="user prompt"),
        GenerationConfig(),
    )
    assert result.content == "response text"

    chunks = [
        chunk async for chunk in service.stream_generate(
            Prompt(system="system prompt", user="stream prompt"),
            GenerationConfig(),
        )
    ]
    assert chunks == ["chunk-1", "chunk-2"]

    for handler in logging.getLogger("plotpilot.llm").handlers:
        handler.flush()

    log_text = llm_log_file.read_text(encoding="utf-8")
    assert "llm.generate start" in log_text
    assert "llm.generate end" in log_text
    assert "llm.stream start" in log_text
    assert "llm.stream end" in log_text
    assert "config:\n```json" in log_text
    assert "system_prompt:\n```text" in log_text
    assert "output:\n```text" in log_text
    assert "user prompt" in log_text
    assert "response text" in log_text


def test_llm_trace_logging_can_be_disabled(tmp_path, monkeypatch):
    llm_log_file = tmp_path / "llm_trace.log"
    monkeypatch.setenv("LLM_LOG_FILE", str(llm_log_file))
    monkeypatch.setenv("LLM_TRACE_ENABLED", "0")

    setup_logging(level=logging.INFO, log_file=None)

    logger = logging.getLogger("plotpilot.llm")
    assert logger.disabled is True
    logger.info("should not appear")

    assert not llm_log_file.exists() or llm_log_file.read_text(encoding="utf-8") == ""
