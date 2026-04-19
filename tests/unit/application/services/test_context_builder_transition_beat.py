"""测试 ContextBuilder 的过渡节拍功能（方案3）"""
import pytest
from unittest.mock import Mock

from application.engine.services.context_builder import ContextBuilder, Beat


class TestTransitionBeat:
    """测试过渡节拍生成"""

    @pytest.fixture
    def context_builder(self):
        """创建 ContextBuilder 实例"""
        return ContextBuilder(
            bible_service=Mock(),
            storyline_manager=Mock(),
            relationship_engine=Mock(),
            vector_store=Mock(),
            novel_repository=Mock(),
            chapter_repository=Mock(),
        )

    def test_no_transition_beat_when_no_seam(self, context_builder):
        """测试：没有接缝信息时，不生成过渡节拍"""
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam=None,
        )

        # 验证没有过渡节拍（第一个节拍不是过渡节拍）
        assert len(beats) > 0
        assert not beats[0].description.startswith("承接上一章")

    def test_no_transition_beat_when_seam_empty(self, context_builder):
        """测试：接缝信息为空时，不生成过渡节拍"""
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam={
                "ending_state": "主角站在门口",
                "ending_emotion": "紧张",
                "unfinished_speech": "",
                "carry_over_question": "",
            },
        )

        # 验证没有过渡节拍
        assert len(beats) > 0
        assert not beats[0].description.startswith("承接上一章")

    def test_transition_beat_with_unfinished_speech(self, context_builder):
        """测试：有未完成的话时，生成过渡节拍"""
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam={
                "ending_state": "主角站在门口",
                "ending_emotion": "紧张",
                "unfinished_speech": "而我——",
                "carry_over_question": "",
            },
        )

        # 验证生成了过渡节拍
        assert len(beats) > 0
        assert beats[0].description.startswith("承接上一章")
        assert "完成未完成的话" in beats[0].description
        assert "而我——" in beats[0].description
        assert beats[0].target_words == 200
        assert beats[0].focus == "emotion"  # 紧张情绪，聚焦 emotion

    def test_transition_beat_with_carry_over_question(self, context_builder):
        """测试：有悬念问题时，生成过渡节拍"""
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam={
                "ending_state": "主角站在门口",
                "ending_emotion": "平静",
                "unfinished_speech": "",
                "carry_over_question": "她是谁？",
            },
        )

        # 验证生成了过渡节拍
        assert len(beats) > 0
        assert beats[0].description.startswith("承接上一章")
        assert "回应悬念问题" in beats[0].description
        assert "她是谁？" in beats[0].description
        assert beats[0].target_words == 200
        assert beats[0].focus == "dialogue"  # 平静情绪，默认聚焦 dialogue

    def test_transition_beat_with_both(self, context_builder):
        """测试：同时有未完成的话和悬念问题时，生成过渡节拍"""
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam={
                "ending_state": "主角站在门口",
                "ending_emotion": "震惊",
                "unfinished_speech": "而我——",
                "carry_over_question": "她是谁？",
            },
        )

        # 验证生成了过渡节拍
        assert len(beats) > 0
        assert beats[0].description.startswith("承接上一章")
        assert "完成未完成的话" in beats[0].description
        assert "回应悬念问题" in beats[0].description
        assert "而我——" in beats[0].description
        assert "她是谁？" in beats[0].description
        assert beats[0].target_words == 200
        assert beats[0].focus == "emotion"  # 震惊情绪，聚焦 emotion

    def test_transition_beat_focus_selection(self, context_builder):
        """测试：根据情绪选择聚焦点"""
        # 测试强烈情绪 -> emotion
        for emotion in ["紧张", "恐惧", "震惊", "愤怒"]:
            beats = context_builder.magnify_outline_to_beats(
                chapter_number=5,
                outline="主角发现真相",
                target_chapter_words=2000,
                previous_chapter_seam={
                    "ending_emotion": emotion,
                    "unfinished_speech": "而我——",
                },
            )
            assert beats[0].focus == "emotion", f"情绪 {emotion} 应该聚焦 emotion"

        # 测试其他情绪 -> dialogue
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam={
                "ending_emotion": "平静",
                "unfinished_speech": "而我——",
            },
        )
        assert beats[0].focus == "dialogue"

    def test_transition_beat_is_first(self, context_builder):
        """测试：过渡节拍总是在第一个位置"""
        beats = context_builder.magnify_outline_to_beats(
            chapter_number=5,
            outline="主角发现真相",
            target_chapter_words=2000,
            previous_chapter_seam={
                "unfinished_speech": "而我——",
            },
        )

        # 验证过渡节拍在第一个位置
        assert len(beats) > 1
        assert beats[0].description.startswith("承接上一章")
        # 第二个节拍应该是正常的大纲节拍
        assert not beats[1].description.startswith("承接上一章")
