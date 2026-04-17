import pytest
from domain.novel.value_objects.chapter_state import ChapterState


class TestChapterState:
    """测试 ChapterState 值对象"""

    def test_create_empty_state(self):
        """测试创建空状态"""
        state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        assert state.new_characters == []
        assert state.character_actions == []
        assert state.relationship_changes == []
        assert state.events == []

    def test_create_state_with_new_characters(self):
        """测试创建包含新角色的状态"""
        state = ChapterState(
            new_characters=[
                {
                    "name": "张三",
                    "description": "主角的朋友",
                    "first_appearance": 5
                }
            ],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        assert len(state.new_characters) == 1
        assert state.new_characters[0]["name"] == "张三"
        assert state.new_characters[0]["description"] == "主角的朋友"
        assert state.new_characters[0]["first_appearance"] == 5

    def test_create_state_with_character_actions(self):
        """测试创建包含角色行为的状态"""
        state = ChapterState(
            new_characters=[],
            character_actions=[
                {
                    "character_id": "char-1",
                    "action": "做出了重要决定",
                    "chapter": 5
                }
            ],
            relationship_changes=[],
            events=[]
        )

        assert len(state.character_actions) == 1
        assert state.character_actions[0]["character_id"] == "char-1"
        assert state.character_actions[0]["action"] == "做出了重要决定"

    def test_create_state_with_relationship_changes(self):
        """测试创建包含关系变化的状态"""
        state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[
                {
                    "char1": "char-1",
                    "char2": "char-2",
                    "old_type": "stranger",
                    "new_type": "friend",
                    "chapter": 5
                }
            ],
            events=[]
        )

        assert len(state.relationship_changes) == 1
        assert state.relationship_changes[0]["char1"] == "char-1"
        assert state.relationship_changes[0]["char2"] == "char-2"
        assert state.relationship_changes[0]["old_type"] == "stranger"
        assert state.relationship_changes[0]["new_type"] == "friend"

    def test_create_state_with_events(self):
        """测试创建包含事件的状态"""
        state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[
                {
                    "type": "conflict",
                    "description": "主角与反派对峙",
                    "involved_characters": ["char-1", "char-2"],
                    "chapter": 5
                }
            ]
        )

        assert len(state.events) == 1
        assert state.events[0]["type"] == "conflict"
        assert state.events[0]["description"] == "主角与反派对峙"
        assert state.events[0]["involved_characters"] == ["char-1", "char-2"]

    def test_state_immutable(self):
        """测试状态对象不可变"""
        state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        with pytest.raises(AttributeError):
            state.new_characters = []

    def test_has_new_characters(self):
        """测试检查是否有新角色"""
        state_with_chars = ChapterState(
            new_characters=[{"name": "张三", "description": "测试", "first_appearance": 1}],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        state_without_chars = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        assert state_with_chars.has_new_characters() is True
        assert state_without_chars.has_new_characters() is False

    def test_has_relationship_changes(self):
        """测试检查是否有关系变化"""
        state_with_changes = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[
                {"char1": "c1", "char2": "c2", "old_type": "stranger", "new_type": "friend", "chapter": 1}
            ],
            events=[]
        )

        state_without_changes = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        assert state_with_changes.has_relationship_changes() is True
        assert state_without_changes.has_relationship_changes() is False

    def test_has_timeline_events(self):
        """测试检查是否有时间线事件"""
        state_with_events = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[],
            timeline_events=[{"event": "test", "timestamp": "2024-01-01", "timestamp_type": "absolute"}]
        )

        state_without_events = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        assert state_with_events.has_timeline_events() is True
        assert state_without_events.has_timeline_events() is False

    def test_has_storyline_activity(self):
        """测试检查是否有故事线活动"""
        state_with_activity = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[],
            advanced_storylines=[{"storyline_id": "s1", "progress_summary": "test"}]
        )

        state_without_activity = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            events=[]
        )

        assert state_with_activity.has_storyline_activity() is True
        assert state_without_activity.has_storyline_activity() is False
