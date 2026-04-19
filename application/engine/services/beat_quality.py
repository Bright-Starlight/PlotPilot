"""节拍级生成质量评估。"""
from __future__ import annotations

from dataclasses import dataclass
import re


MIN_ABSOLUTE_BEAT_CHARS = 80
MIN_SENTENCE_COUNT = 2
COMMON_ACTION_TOKENS = (
    "走", "看", "抬", "抬手", "伸手", "退", "进", "推", "拉", "握", "抓", "按",
    "站", "坐", "跪", "转身", "逼近", "后退", "开口", "说道", "问", "答", "笑",
    "骂", "喝", "斩", "劈", "刺", "扑", "撞", "追", "逃", "翻", "落", "起身",
)


@dataclass(frozen=True)
class BeatQualityReport:
    char_count: int
    paragraph_count: int
    sentence_count: int
    has_dialogue: bool
    has_action_verb: bool
    min_chars: int
    passed: bool
    failure_reasons: tuple[str, ...]


def assess_beat_content(content: str, target_words: int) -> BeatQualityReport:
    text = (content or "").strip()
    compact_text = "".join(text.split())
    char_count = len(compact_text)
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    sentence_count = len([part for part in re.split(r"[。！？!?]+", text) if part.strip()])
    has_dialogue = any(token in text for token in ("“", "”", "\"", "「", "」", "："))
    has_action_verb = any(token in text for token in COMMON_ACTION_TOKENS)
    min_chars = max(MIN_ABSOLUTE_BEAT_CHARS, min(int(target_words or 0), int((target_words or 0) * 0.35) or 0))

    failure_reasons: list[str] = []
    if char_count < min_chars:
        failure_reasons.append(f"字数不足（{char_count} < {min_chars}）")
    if sentence_count < MIN_SENTENCE_COUNT:
        failure_reasons.append("句子过少")
    if not has_dialogue and not has_action_verb:
        failure_reasons.append("缺少动作或对话推进")

    return BeatQualityReport(
        char_count=char_count,
        paragraph_count=len(paragraphs),
        sentence_count=sentence_count,
        has_dialogue=has_dialogue,
        has_action_verb=has_action_verb,
        min_chars=min_chars,
        passed=not failure_reasons,
        failure_reasons=tuple(failure_reasons),
    )


def build_retry_suffix(report: BeatQualityReport) -> str:
    reasons = "；".join(report.failure_reasons) or "输出质量不足"
    return (
        "\n\n【重试要求】\n"
        f"- 上一轮失败原因：{reasons}\n"
        f"- 本段至少写到 {report.min_chars} 字以上。\n"
        "- 必须出现可见动作推进或人物对话，不能只写意象、摘要句或提纲句。\n"
        "- 直接续写正文，不要解释，不要写提纲，不要复述规则。\n"
    )
