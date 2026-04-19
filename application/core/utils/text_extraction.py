"""Text extraction utilities for chapter content analysis"""
import re
from typing import Dict, List

# Shared constants
EMOTION_MARKERS = [
    "愤怒", "痛苦", "震惊", "恐惧", "悲伤", "苦涩", "清醒",
    "决绝", "迟疑", "紧张", "压抑", "复杂", "不安",
]

# Pre-compiled regex patterns for performance
_UNFINISHED_SPEECH_PATTERN = re.compile(r'(["""][^""]*[——…\.]{2,}["""]?)\s*$')
_QUESTION_PATTERN = re.compile(r"[^。！？!?]{4,40}[？?]")
_CHINESE_NAME_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,4}(?=[，。、：；！？\s]|$)")


class SeamExtractor:
    """Extract seam information from chapter content

    Consolidates logic from:
    - chapter_fusion_service._extract_seam_from_content
    - autopilot_daemon._derive_seam_snapshot_from_content
    """

    @staticmethod
    def extract_seam_from_content(
        content: str,
        include_opening_hint: bool = False
    ) -> Dict[str, str]:
        """Extract seam information from chapter content

        Args:
            content: Chapter content text
            include_opening_hint: Whether to include next_opening_hint field

        Returns:
            Dictionary with seam information:
            - ending_state: Last 3 paragraphs (max 300 chars)
            - ending_emotion: Detected emotion markers
            - carry_over_question: Last 1-2 questions
            - unfinished_speech: Incomplete dialogue
            - next_opening_hint: Opening suggestion (if include_opening_hint=True)
        """
        if not content:
            return {
                "ending_state": "",
                "ending_emotion": "",
                "carry_over_question": "",
                "unfinished_speech": "",
                "next_opening_hint": "" if include_opening_hint else None,
            }

        paragraphs = [p.strip() for p in re.split(r"\n+", content) if p.strip()]
        tail_paragraphs = paragraphs[-3:] if paragraphs else []
        ending_state = "\n".join(tail_paragraphs)[-300:].strip()

        # Detect unfinished speech (ends with "——", "……", "...")
        unfinished_speech = ""
        if tail_paragraphs:
            last_para = tail_paragraphs[-1]
            unfinished_match = _UNFINISHED_SPEECH_PATTERN.search(last_para)
            if unfinished_match:
                unfinished_speech = unfinished_match.group(1)

        # Extract last 1-2 questions
        question_candidates = _QUESTION_PATTERN.findall(content)
        carry_over_question = ""
        if len(question_candidates) >= 2:
            carry_over_question = "\n".join(question_candidates[-2:])
        elif question_candidates:
            carry_over_question = question_candidates[-1].strip()

        # Extract emotion markers
        ending_emotion = ""
        if tail_paragraphs:
            tail_text = " ".join(tail_paragraphs)
            hits = [marker for marker in EMOTION_MARKERS if marker in tail_text]
            if hits:
                ending_emotion = "、".join(hits[:3])

        result = {
            "ending_state": ending_state,
            "ending_emotion": ending_emotion,
            "carry_over_question": carry_over_question,
            "unfinished_speech": unfinished_speech,
        }

        # Add next_opening_hint if requested (used by autopilot_daemon)
        if include_opening_hint:
            next_opening_hint = ""

            # If unfinished speech exists, use it as opening hint
            if unfinished_speech:
                next_opening_hint = f"承接未完成的话：{unfinished_speech}"
            else:
                # Extract potential opening hints from tail
                if tail_paragraphs:
                    tail_text = " ".join(tail_paragraphs)
                    opening_candidates = re.findall(
                        r"(?:将要|准备|打算|即将|正要)([^。！？!?]{4,20})",
                        tail_text
                    )
                    if opening_candidates:
                        next_opening_hint = opening_candidates[-1].strip("，,；; ")

            # Fallback: use last sentence if no other hint
            if not next_opening_hint and not carry_over_question and ending_state:
                sentences = [s.strip() for s in re.split(r"[。！？!?]", ending_state) if s.strip()]
                if sentences:
                    last_sentence = sentences[-1]
                    if len(last_sentence) > 8:
                        next_opening_hint = last_sentence[:30]

            result["next_opening_hint"] = next_opening_hint

        return result


class CharacterExtractor:
    """Extract character names from text"""

    # Common non-name words to filter out
    _STOPWORDS = {
        "这个", "那个", "什么", "怎么", "为什么", "如何",
        "可以", "不是", "没有", "已经", "现在", "然后",
    }

    @staticmethod
    def extract_characters_from_outline(outline: str) -> List[str]:
        """Extract character names from outline text

        Args:
            outline: Outline text

        Returns:
            List of character names (max 5)
        """
        if not outline:
            return []

        # Match 2-4 character Chinese names
        candidates = _CHINESE_NAME_PATTERN.findall(outline)

        # Deduplicate while preserving order
        seen = set()
        characters = []
        for name in candidates:
            if name not in seen and len(name) >= 2:
                if name not in CharacterExtractor._STOPWORDS:
                    seen.add(name)
                    characters.append(name)

        # Return top 5 most frequently appearing characters
        return characters[:5]
