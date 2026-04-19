from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from application.core.services.state_lock_service import StateLockService


def _make_service() -> StateLockService:
    return StateLockService(
        chapter_repository=Mock(),
        story_node_repository=Mock(),
        knowledge_service=Mock(),
        bible_service=Mock(),
        state_lock_repository=Mock(),
        fusion_repository=Mock(),
        llm_service=None,
    )


def test_build_lock_groups_does_not_force_ending_target_from_last_inferred_location():
    service = _make_service()
    chapter = SimpleNamespace(outline="", title="密报惊变")
    plan = SimpleNamespace(
        outline="顾玄音于北京城收到残魂关密报，海禁迷渊出现异常。",
        description="两人准备南下，但本章未明确落点。",
        metadata={},
        timeline_start="",
        timeline_end="",
        pov_character_id=None,
    )
    previous_summary = SimpleNamespace(ending_state="沈墨白握紧命簿，前世记忆开始觉醒")
    current_summary = None
    facts = []
    bible = SimpleNamespace(
        characters=[],
        locations=[
            SimpleNamespace(name="北京城"),
            SimpleNamespace(name="残魂关"),
            SimpleNamespace(name="海禁迷渊"),
        ],
    )

    locks, _ = service._build_lock_groups(
        chapter=chapter,
        plan=plan,
        previous_summary=previous_summary,
        current_summary=current_summary,
        facts=facts,
        bible=bible,
    )

    ending_entries = locks["ending_lock"]["entries"]
    assert ending_entries == []
    location_values = [entry["value"] for entry in locks["location_lock"]["entries"]]
    assert "海禁迷渊" in location_values
    assert "前世记忆开始觉醒" in location_values
