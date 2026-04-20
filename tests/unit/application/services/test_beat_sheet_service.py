from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from application.blueprint.services.beat_sheet_service import BeatSheetService
from application.engine.theme.theme_agent import ThemeAgent, BeatTemplate, ThemeDirectives
from domain.structure.story_node import NodeType


@dataclass
class _FakeNovelId:
    value: str


@dataclass
class _FakeChapter:
    novel_id: _FakeNovelId
    number: int
    title: str
    outline: str = ""
    content: str = ""


@dataclass
class _FakeNovel:
    id: _FakeNovelId
    genre: str = ""
    target_words_per_chapter: int = 3500


class _FakeChapterRepository:
    def __init__(self, chapter: _FakeChapter):
        self.chapter = chapter

    def get_by_id(self, chapter_id):  # noqa: ANN001
        return self.chapter

    def get_by_number(self, novel_id, number):  # noqa: ANN001
        return None


class _FakeNovelRepository:
    def __init__(self, novel: _FakeNovel = None):
        self.novel = novel or _FakeNovel(id=_FakeNovelId("novel-1"), genre="")

    def get_by_id(self, novel_id):  # noqa: ANN001
        return self.novel


class _FakeStoryNodeRepository:
    def __init__(self, nodes=None):
        self.nodes = nodes or []

    async def get_by_id(self, node_id):  # noqa: ANN001
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    async def get_by_novel(self, novel_id):  # noqa: ANN001
        return self.nodes


class _FakeStorylineRepository:
    def list_active_by_novel(self, novel_id):  # noqa: ANN001
        return []

    def get_by_novel_id(self, novel_id):  # noqa: ANN001
        return []


class _FakeBeatSheetRepository:
    async def save(self, beat_sheet):
        return None

    async def get_by_chapter_id(self, chapter_id):  # noqa: ANN001
        return None


class _FakeLLMService:
    def __init__(self, response_content=None):
        self.response_content = response_content or '{"scenes": [{"title": "场景1", "goal": "目标", "pov_character": "主角", "estimated_words": 800}]}'

    async def generate(self, prompt, config):  # noqa: ANN001
        result = MagicMock()
        result.content = self.response_content
        return result


class _FakeThemeAgent(ThemeAgent):
    """Fake theme agent for testing"""

    def __init__(self, genre_key="xuanhuan", genre_name="玄幻", beat_templates=None, context_directives=None):
        self._genre_key = genre_key
        self._genre_name = genre_name
        self._beat_templates = beat_templates or []
        self._context_directives = context_directives or ThemeDirectives()

    @property
    def genre_key(self) -> str:
        return self._genre_key

    @property
    def genre_name(self) -> str:
        return self._genre_name

    def get_beat_templates(self):
        return self._beat_templates

    def get_context_directives(self, novel_id, chapter_number, outline):
        return self._context_directives


@pytest.mark.asyncio
async def test_generate_beat_sheet_requires_state_lock_version():
    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
                outline="旧大纲",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
    )

    with pytest.raises(ValueError, match="state_lock_version is required"):
        await service.generate_beat_sheet("chapter-1", "旧大纲")


@pytest.mark.asyncio
async def test_retrieve_relevant_context_accepts_timeline_event_without_description(monkeypatch):
    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=2,
                title="第二章",
                outline="旧大纲",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
    )

    class _FakeTimelineRepo:
        def get_by_novel_id(self, novel_id):  # noqa: ANN001
            return SimpleNamespace(
                events=[
                    SimpleNamespace(
                        chapter_number=1,
                        event="前章大事",
                        timestamp_type="relative",
                    )
                ]
            )

    monkeypatch.setattr(
        "infrastructure.persistence.database.sqlite_timeline_repository.SqliteTimelineRepository",
        lambda db: _FakeTimelineRepo(),
    )
    monkeypatch.setattr(
        "infrastructure.persistence.database.connection.get_database",
        lambda: object(),
    )

    context = await service._retrieve_relevant_context("chapter-2", "旧大纲")

    assert context["timeline_events"] == [
        {
            "description": "前章大事",
            "time_type": "relative",
            "chapter": 1,
        }
    ]


# ─── Genre-Aware Beat Template Tests ───

def test_match_beat_template_with_xuanhuan_keywords():
    """Test that xuanhuan template matches keywords like '修炼', '突破'"""
    from domain.structure.story_node import NodeType

    fake_template = BeatTemplate(
        keywords=["修炼", "突破", "闭关"],
        priority=80,
        beats=[
            ("修炼准备", 500, "sensory"),
            ("修炼过程", 1000, "cultivation"),
            ("突破", 800, "power_reveal"),
        ],
    )

    fake_agent = _FakeThemeAgent(
        genre_key="xuanhuan",
        genre_name="玄幻",
        beat_templates=[fake_template],
    )

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        novel_repo=_FakeNovelRepository(
            _FakeNovel(id=_FakeNovelId("novel-1"), genre="xuanhuan")
        ),
        theme_registry=None,
    )

    matched = service._match_beat_template(fake_agent, "主角开始修炼，突破到新境界")
    assert matched is not None
    assert matched.keywords == ["修炼", "突破", "闭关"]
    assert matched.priority == 80


def test_match_beat_template_no_match():
    """Test that no template matches when keywords don't match"""
    fake_agent = _FakeThemeAgent(
        genre_key="xuanhuan",
        genre_name="玄幻",
        beat_templates=[
            BeatTemplate(
                keywords=["修炼", "突破"],
                priority=80,
                beats=[("test", 500, "general")],
            )
        ],
    )

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        theme_registry=None,
    )

    matched = service._match_beat_template(fake_agent, "主角在朝堂上与大臣辩论")
    assert matched is None


def test_get_theme_agent_returns_agent_for_xuanhuan_novel():
    """Test that _get_theme_agent returns correct agent for xuanhuan genre"""
    fake_agent = _FakeThemeAgent(genre_key="xuanhuan", genre_name="玄幻")

    class _FakeThemeRegistry:
        def get_or_default(self, genre):
            if genre == "xuanhuan":
                return fake_agent
            return None

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        theme_registry=_FakeThemeRegistry(),
    )

    novel = _FakeNovel(id=_FakeNovelId("novel-1"), genre="xuanhuan")
    agent = service._get_theme_agent(novel)
    assert agent is fake_agent
    assert agent.genre_key == "xuanhuan"


def test_get_theme_agent_returns_none_for_empty_genre():
    """Test that _get_theme_agent returns None for empty genre"""
    class _FakeThemeRegistry:
        def get_or_default(self, genre):
            return None

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        theme_registry=_FakeThemeRegistry(),
    )

    novel = _FakeNovel(id=_FakeNovelId("novel-1"), genre="")
    agent = service._get_theme_agent(novel)
    assert agent is None


# ─── Macro Context Tests ───

@pytest.mark.asyncio
async def test_get_macro_context_with_complete_hierarchy():
    """Test _get_macro_context retrieves Act/Volume/Part descriptions with full planning info"""
    from domain.structure.story_node import StoryNode

    part_node = StoryNode(
        id="part-1",
        novel_id="novel-1",
        parent_id=None,
        node_type=NodeType.PART,
        number=1,
        title="第一部",
        description="废柴觉醒，踏上修炼之路",
        themes=["逆袭", "成长"],
        order_index=0,
    )

    volume_node = StoryNode(
        id="volume-1",
        novel_id="novel-1",
        parent_id="part-1",
        node_type=NodeType.VOLUME,
        number=1,
        title="第一卷",
        description="本卷主线：主角从外门弟子成长为内门核心",
        themes=["修炼", "宗门"],
        order_index=0,
    )

    act_node = StoryNode(
        id="act-1",
        novel_id="novel-1",
        parent_id="volume-1",
        node_type=NodeType.ACT,
        number=1,
        title="第一幕",
        description="本幕核心冲突：主角在宗门大比中击败天才，奠定地位",
        key_events=["宗门大比", "击败天才"],
        narrative_arc="起承转合",
        conflicts=["主角vs天才"],
        themes=["对决", "成长"],
        order_index=0,
    )

    chapter_node = StoryNode(
        id="chapter-1",
        novel_id="novel-1",
        parent_id="act-1",
        node_type=NodeType.CHAPTER,
        number=1,
        title="第一章",
        description="",
        order_index=0,
    )

    story_node_repo = _FakeStoryNodeRepository([
        part_node, volume_node, act_node, chapter_node
    ])

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        story_node_repo=story_node_repo,
    )

    macro_context = await service._get_macro_context("chapter-1")

    # Act should include description + key_events + narrative_arc + conflicts + themes
    assert "本幕核心冲突" in macro_context.get("act", "")
    assert "关键事件" in macro_context.get("act", "")
    assert "叙事弧线" in macro_context.get("act", "")
    assert "核心冲突" in macro_context.get("act", "")
    # Volume should include description + themes
    assert "本卷主线" in macro_context.get("volume", "")
    assert "主题" in macro_context.get("volume", "")
    # Part should include description + themes
    assert "废柴觉醒" in macro_context.get("part", "")
    assert "主题" in macro_context.get("part", "")


@pytest.mark.asyncio
async def test_get_macro_context_with_partial_hierarchy():
    """Test _get_macro_context works with incomplete hierarchy (no Part)"""
    from domain.structure.story_node import StoryNode

    volume_node = StoryNode(
        id="volume-1",
        novel_id="novel-1",
        parent_id=None,
        node_type=NodeType.VOLUME,
        number=1,
        title="第一卷",
        description="本卷主线：主角成长",
        themes=["成长"],
        order_index=0,
    )

    act_node = StoryNode(
        id="act-1",
        novel_id="novel-1",
        parent_id="volume-1",
        node_type=NodeType.ACT,
        number=1,
        title="第一幕",
        description="本幕核心冲突",
        key_events=["事件1", "事件2"],
        order_index=0,
    )

    chapter_node = StoryNode(
        id="chapter-1",
        novel_id="novel-1",
        parent_id="act-1",
        node_type=NodeType.CHAPTER,
        number=1,
        title="第一章",
        description="",
        order_index=0,
    )

    story_node_repo = _FakeStoryNodeRepository([
        volume_node, act_node, chapter_node
    ])

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        story_node_repo=story_node_repo,
    )

    macro_context = await service._get_macro_context("chapter-1")

    # Act should include description + key_events
    assert "本幕核心冲突" in macro_context.get("act", "")
    assert "关键事件" in macro_context.get("act", "")
    # Volume should include description + themes
    assert "本卷主线" in macro_context.get("volume", "")
    assert "成长" in macro_context.get("volume", "")
    # Part should be None
    assert macro_context.get("part") is None


# ─── Build Prompt Tests ───

def test_build_beat_sheet_prompt_includes_macro_context():
    """Test that _build_beat_sheet_prompt includes Act/Volume/Part descriptions"""
    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
    )

    macro_context = {
        "act": "本幕核心冲突：主角在宗门大比中击败天才",
        "volume": "本卷主线：主角从外门弟子成长为内门核心",
        "part": "第一部：废柴觉醒，踏上修炼之路",
    }

    prompt = service._build_beat_sheet_prompt(
        outline="章节大纲内容",
        context={},
        target_words_per_chapter=3500,
        target_beat_count=4,
        words_per_beat=[875, 875, 875, 875],
        macro_context=macro_context,
    )

    assert "本幕核心冲突" in prompt.user
    assert "本卷主线" in prompt.user
    assert "第一部：废柴觉醒" in prompt.user


def test_build_beat_sheet_prompt_includes_beat_type_labels():
    """Test that _build_beat_sheet_prompt includes beat type labels when provided"""
    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
    )

    beat_type_labels = ["cultivation", "action", "power_reveal", "emotion"]

    prompt = service._build_beat_sheet_prompt(
        outline="章节大纲内容",
        context={},
        target_words_per_chapter=3500,
        target_beat_count=4,
        words_per_beat=[875, 875, 875, 875],
        beat_type_labels=beat_type_labels,
    )

    assert "cultivation" in prompt.system
    assert "power_reveal" in prompt.system


def test_match_beat_template_with_history_keywords():
    """Test that history template matches keywords like '朝堂', '战争', '权谋'"""
    fake_template = BeatTemplate(
        keywords=["朝堂", "战争", "权谋"],
        priority=85,
        beats=[
            ("朝堂阴谋", 800, "court_debate"),
            ("战争准备", 700, "action"),
            ("权谋博弈", 800, "dialogue"),
        ],
    )

    fake_agent = _FakeThemeAgent(
        genre_key="history",
        genre_name="历史",
        beat_templates=[fake_template],
    )

    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        theme_registry=None,
    )

    matched = service._match_beat_template(fake_agent, "主角在朝堂上与权臣展开激烈博弈")
    assert matched is not None
    assert matched.keywords == ["朝堂", "战争", "权谋"]
    assert matched.priority == 85


def test_get_theme_agent_returns_none_when_no_registry():
    """Test that _get_theme_agent returns None when no registry is provided"""
    service = BeatSheetService(
        beat_sheet_repo=_FakeBeatSheetRepository(),
        chapter_repo=_FakeChapterRepository(
            _FakeChapter(
                novel_id=_FakeNovelId("novel-1"),
                number=1,
                title="第一章",
            )
        ),
        storyline_repo=_FakeStorylineRepository(),
        llm_service=_FakeLLMService(),
        vector_store=None,
        bible_service=None,
        theme_registry=None,
    )

    novel = _FakeNovel(id=_FakeNovelId("novel-1"), genre="xuanhuan")
    agent = service._get_theme_agent(novel)
    assert agent is None


# ─── ContinuousPlanningService Tests ───

def test_build_theme_context_prompt_returns_directives():
    """Test _build_theme_context_prompt returns formatted ThemeDirectives"""
    from application.blueprint.services.continuous_planning_service import ContinuousPlanningService

    fake_agent = _FakeThemeAgent(
        genre_key="xuanhuan",
        genre_name="玄幻",
        context_directives=ThemeDirectives(
            world_rules="修炼体系分九境，每境有初、中、后期",
            atmosphere="快意恩仇，热血成长",
            taboos="禁止无脑碾压，禁止金手指滥用",
            tropes_to_use="扮猪吃老虎，步步高升",
            tropes_to_avoid="境界注水，后宫收集器",
        ),
    )

    class _FakeThemeRegistry:
        def get_or_default(self, genre):
            if genre == "xuanhuan":
                return fake_agent
            return None

    class _FakeNovelRepo:
        def get_by_id(self, novel_id):
            return _FakeNovel(id=_FakeNovelId("novel-1"), genre="xuanhuan")

    service = ContinuousPlanningService(
        story_node_repo=MagicMock(),
        chapter_element_repo=MagicMock(),
        llm_service=MagicMock(),
        theme_registry=_FakeThemeRegistry(),
        novel_repository=_FakeNovelRepo(),
    )

    context_text = service._build_theme_context_prompt("novel-1", 1, "章节大纲")

    assert "修炼体系分九境" in context_text
    assert "快意恩仇" in context_text
    assert "扮猪吃老虎" in context_text
    assert "禁止无脑碾压" in context_text


def test_build_theme_context_prompt_returns_empty_for_unknown_genre():
    """Test _build_theme_context_prompt returns empty string for unknown genre"""
    from application.blueprint.services.continuous_planning_service import ContinuousPlanningService

    class _FakeThemeRegistry:
        def get_or_default(self, genre):
            return None

    class _FakeNovelRepo:
        def get_by_id(self, novel_id):
            return _FakeNovel(id=_FakeNovelId("novel-1"), genre="unknown_genre")

    service = ContinuousPlanningService(
        story_node_repo=MagicMock(),
        chapter_element_repo=MagicMock(),
        llm_service=MagicMock(),
        theme_registry=_FakeThemeRegistry(),
        novel_repository=_FakeNovelRepo(),
    )

    context_text = service._build_theme_context_prompt("novel-1", 1, "章节大纲")
    assert context_text == ""


