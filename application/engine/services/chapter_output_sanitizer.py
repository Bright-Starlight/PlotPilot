"""章节正文清洗工具。

用于移除 LLM 偶发输出的思考块、分析说明和续写元信息，确保最终写入章节库的是纯正文。
"""
from __future__ import annotations

import re

_THINK_BLOCK_PATTERNS = (
    re.compile(r"<think\|?>.*?</think\|?>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<thinking>.*?</thinking>", re.DOTALL | re.IGNORECASE),
)

_META_LINE_PATTERNS = (
    re.compile(r"^\s*#\s*(续写|思考|分析|AI思考)\b.*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\.\s*(当前字数|目标字数|需要补写|让我分析|用户要求我|让我仔细|分析一下).*$"),
    re.compile(r"^\s*(让我分析一下当前的情况|让我仔细阅读当前的内容|用户要求我|当前字数：|目标字数：|需要补写：|让我分析一下|我来分析一下|先分析一下|下面分析一下|接下来分析一下).*$"),
    re.compile(r"^\s*(当前字数|目标字数|需要补写|补写轮次|已有章节内容如下|请从末尾自然续写|硬性要求|让我分析|分析一下|让我仔细|用户要求我).*$"),
)


def _is_meta_paragraph(paragraph: str) -> bool:
    lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return False
    return all(any(pattern.match(line) for pattern in _META_LINE_PATTERNS) for line in lines)


def sanitize_chapter_output(text: str) -> str:
    """清洗章节正文，去掉思考过程和分析说明。"""
    content = (text or "").strip()
    if not content:
        return content

    for pattern in _THINK_BLOCK_PATTERNS:
        content = pattern.sub("", content)

    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", content)]
    kept_paragraphs = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        if _is_meta_paragraph(paragraph):
            continue
        kept_paragraphs.append(paragraph)

    cleaned = "\n\n".join(kept_paragraphs).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned
