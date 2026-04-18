"""State lock generation and versioning service."""
from __future__ import annotations

import logging
import json
import re
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from application.ai.structured_json_pipeline import parse_and_repair_json, sanitize_llm_output, validate_json_schema
from application.core.state_lock_inference_contract import StateLockInferencePayload
from application.core.dtos.state_lock_dto import LOCK_GROUP_KEYS, StateLockSnapshotDTO
from application.world.services.bible_service import BibleService
from application.world.services.knowledge_service import KnowledgeService
from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.value_objects.chapter_id import ChapterId
from infrastructure.persistence.database.sqlite_chapter_fusion_repository import SqliteChapterFusionRepository
from infrastructure.persistence.database.sqlite_state_lock_repository import SqliteStateLockRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

if TYPE_CHECKING:
    from domain.ai.services.llm_service import LLMService


logger = logging.getLogger(__name__)


class StateLockService:
    def __init__(
        self,
        *,
        chapter_repository: ChapterRepository,
        story_node_repository: StoryNodeRepository,
        knowledge_service: KnowledgeService,
        bible_service: BibleService,
        state_lock_repository: SqliteStateLockRepository,
        fusion_repository: SqliteChapterFusionRepository,
        llm_service: Optional["LLMService"] = None,
    ):
        self.chapter_repository = chapter_repository
        self.story_node_repository = story_node_repository
        self.knowledge_service = knowledge_service
        self.bible_service = bible_service
        self.state_lock_repository = state_lock_repository
        self.fusion_repository = fusion_repository
        self.llm_service = llm_service

    async def generate_state_locks(self, chapter_id: str, *, plan_version: Optional[int] = None) -> StateLockSnapshotDTO:
        logger.info("state lock generation start chapter_id=%s plan_version=%s", chapter_id, plan_version)
        chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            raise ValueError("Chapter not found")

        plan = self._get_chapter_plan(chapter.novel_id.value, chapter_id, chapter.number)
        plan_meta = getattr(plan, "metadata", {}) or {}
        resolved_plan_version = int(plan_version or plan_meta.get("version") or 1)

        knowledge = self.knowledge_service.get_knowledge(chapter.novel_id.value)
        bible = self.bible_service.get_bible_by_novel(chapter.novel_id.value)
        previous_summary = next((ch for ch in knowledge.chapters if ch.chapter_id == chapter.number - 1), None)
        current_summary = next((ch for ch in knowledge.chapters if ch.chapter_id == chapter.number), None)
        facts = [fact for fact in knowledge.facts if fact.chapter_id is None or fact.chapter_id <= chapter.number]

        locks, inference_notes = self._build_lock_groups(
            chapter=chapter,
            plan=plan,
            previous_summary=previous_summary,
            current_summary=current_summary,
            facts=facts,
            bible=bible,
        )
        locks, inference_notes = await self._apply_llm_inference_if_needed(
            chapter=chapter,
            plan=plan,
            previous_summary=previous_summary,
            current_summary=current_summary,
            facts=facts,
            locks=locks,
            inference_notes=inference_notes,
        )
        previous = self.state_lock_repository.get_current_by_chapter(chapter_id)
        critical_change = self._detect_critical_change(previous.locks if previous else None, locks)
        snapshot = self.state_lock_repository.save_snapshot(
            chapter_id=chapter_id,
            novel_id=chapter.novel_id.value,
            plan_version=resolved_plan_version,
            locks=locks,
            source="generated",
            change_reason="",
            changed_fields=[],
            inference_notes=inference_notes,
            critical_change=critical_change,
        )
        logger.info(
            "state lock generation saved chapter_id=%s state_lock_id=%s version=%s plan_version=%s critical_change=%s inference_notes=%s",
            chapter_id,
            snapshot.state_lock_id,
            snapshot.version,
            snapshot.plan_version,
            bool(critical_change.get("changed")),
            len(inference_notes),
        )
        self._mark_impacted_fusion_drafts(chapter_id, previous, snapshot)
        return self.get_current_state_locks(chapter_id)

    def get_current_state_locks(self, chapter_id: str) -> StateLockSnapshotDTO:
        snapshot = self.state_lock_repository.get_current_by_chapter(chapter_id)
        if snapshot is None:
            raise ValueError("State locks not found")
        return self._with_statuses(snapshot)

    def update_state_locks(
        self,
        state_lock_id: str,
        *,
        locks: Dict[str, Dict[str, Any]],
        change_reason: str,
    ) -> StateLockSnapshotDTO:
        logger.info("state lock manual update start state_lock_id=%s", state_lock_id)
        if not change_reason.strip():
            raise ValueError("change_reason is required")
        current = self.state_lock_repository.get_current_by_chapter(self._chapter_id_for_lock(state_lock_id))
        if current is None or current.state_lock_id != state_lock_id:
            raise ValueError("State lock not found")
        normalized = self._normalize_groups(locks)
        changed_fields = self._changed_fields(current.locks, normalized)
        normalized = self._apply_manual_status(normalized, changed_fields, change_reason.strip())
        critical_change = self._detect_critical_change(current.locks, normalized)
        snapshot = self.state_lock_repository.save_snapshot(
            chapter_id=current.chapter_id,
            novel_id=current.novel_id,
            plan_version=current.plan_version,
            locks=normalized,
            source="manual_edit",
            change_reason=change_reason.strip(),
            changed_fields=changed_fields,
            inference_notes=[],
            critical_change=critical_change,
        )
        logger.info(
            "state lock manual update saved chapter_id=%s state_lock_id=%s version=%s changed_fields=%s critical_change=%s",
            current.chapter_id,
            snapshot.state_lock_id,
            snapshot.version,
            ",".join(changed_fields) if changed_fields else "-",
            bool(critical_change.get("changed")),
        )
        self._mark_impacted_fusion_drafts(current.chapter_id, current, snapshot)
        return self.get_current_state_locks(current.chapter_id)

    def has_version(self, chapter_id: str, version: int) -> bool:
        return self.state_lock_repository.has_version(chapter_id, version)

    def load_version(self, chapter_id: str, version: int) -> Optional[StateLockSnapshotDTO]:
        snapshot = self.state_lock_repository.get_version_by_chapter(chapter_id, version)
        return self._with_statuses(snapshot) if snapshot else None

    def evaluate_text_violations(
        self,
        chapter_id: str,
        version: int,
        *,
        text: str,
        end_state: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        snapshot = self.state_lock_repository.get_version_by_chapter(chapter_id, version)
        if snapshot is None:
            return []
        locks = snapshot.locks
        lowered = text or ""
        violations: List[Dict[str, Any]] = []
        for entry in locks.get("character_lock", {}).get("entries", []):
            if entry.get("kind") == "forbidden_character" and str(entry.get("value") or "").strip():
                name = str(entry["value"]).strip()
                if name and name in lowered:
                    violations.append(
                        {
                            "group": "character_lock",
                            "entry_key": entry.get("key") or name,
                            "severity": "P0",
                            "message": f"正文包含被禁止人物：{name}",
                        }
                    )
        for entry in locks.get("numeric_lock", {}).get("entries", []):
            label = str(entry.get("label") or "").strip()
            value = entry.get("value")
            if label and value not in (None, "") and label in lowered and str(value) not in lowered:
                violations.append(
                    {
                        "group": "numeric_lock",
                        "entry_key": entry.get("key") or label,
                        "severity": "P0",
                        "message": f"{label} 与锁定数值 {value} 不一致",
                    }
                )
        expected_end = self._first_entry_value(locks.get("ending_lock", {}))
        actual_end = ""
        if isinstance(end_state, dict):
            actual_end = str(end_state.get("location") or end_state.get("state") or "")
        if expected_end and actual_end and expected_end != actual_end:
            violations.append(
                {
                    "group": "ending_lock",
                    "entry_key": "ending_target",
                    "severity": "P0",
                    "message": f"终态落点应为 {expected_end}，实际为 {actual_end}",
                }
            )
        return violations

    def _chapter_id_for_lock(self, state_lock_id: str) -> str:
        current = self.state_lock_repository.db.fetch_one(
            "SELECT chapter_id FROM state_locks WHERE state_lock_id = ?",
            (state_lock_id,),
        )
        if current is None:
            raise ValueError("State lock not found")
        return current["chapter_id"]

    def _get_chapter_plan(self, novel_id: str, chapter_id: str, chapter_number: int):
        nodes = self.story_node_repository.get_by_novel_sync(novel_id)
        for node in nodes:
            if node.id == chapter_id:
                return node
        for node in nodes:
            if getattr(node, "node_type", None).value == "chapter" and node.number == chapter_number:
                return node
        return None

    def _build_lock_groups(
        self,
        *,
        chapter,
        plan,
        previous_summary,
        current_summary,
        facts,
        bible,
    ) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
        plan_outline = getattr(plan, "outline", "") or getattr(chapter, "outline", "") or ""
        plan_desc = getattr(plan, "description", "") or ""
        metadata = getattr(plan, "metadata", {}) or {}
        characters = list(getattr(bible, "characters", []) or [])
        locations = list(getattr(bible, "locations", []) or [])

        involved_characters = []
        for character in characters:
            if character.name and character.name in f"{plan_outline}\n{plan_desc}":
                involved_characters.append(character.name)
        pov_id = getattr(plan, "pov_character_id", None)
        if pov_id:
            pov = next((character.name for character in characters if character.id == pov_id), pov_id)
            involved_characters.insert(0, pov)
        involved_characters = list(dict.fromkeys(filter(None, involved_characters)))

        inferred_locations = []
        for location in locations:
            if location.name and location.name in f"{plan_outline}\n{plan_desc}":
                inferred_locations.append(location.name)
        prev_end_location = self._extract_location(previous_summary.ending_state if previous_summary else "")
        if prev_end_location:
            inferred_locations.insert(0, prev_end_location)
        inferred_locations = list(dict.fromkeys(filter(None, inferred_locations)))

        ending_target = (
            self._extract_location(getattr(current_summary, "ending_state", "") or "")
            or str(getattr(plan, "timeline_end", "") or "").strip()
            or (inferred_locations[-1] if inferred_locations else "")
        )

        event_lines = []
        if current_summary and current_summary.beat_sections:
            event_lines.extend(current_summary.beat_sections)
        if current_summary and current_summary.key_events:
            event_lines.extend([segment.strip() for segment in re.split(r"[；;\n]", current_summary.key_events) if segment.strip()])
        if not event_lines:
            event_lines.extend([segment.strip(" -") for segment in plan_outline.splitlines() if segment.strip()])
        event_lines = list(dict.fromkeys(event_lines))

        numeric_entries = []
        for index, match in enumerate(re.finditer(r"([A-Za-z\u4e00-\u9fff]{1,16})[:：]?\s*(\d+(?:\.\d+)?)\s*([A-Za-z\u4e00-\u9fff%]*)", plan_outline)):
            label = match.group(1).strip()
            if len(label) <= 1:
                continue
            numeric_entries.append(
                self._entry(
                    key=f"numeric_{index + 1}",
                    label=label,
                    value=f"{match.group(2)}{match.group(3)}".strip(),
                    source="chapter_plan",
                    kind="numeric_constraint",
                )
            )

        facts_items = []
        forbidden_characters = []
        forbidden_events = []
        for fact in facts:
            predicate = str(getattr(fact, "predicate", "") or "")
            subject = str(getattr(fact, "subject", "") or "")
            obj = str(getattr(fact, "object", "") or "")
            if any(token in predicate for token in ("禁止", "禁入", "不得")):
                forbidden_characters.append(subject or obj)
                forbidden_events.append(obj or predicate)
            if any(token in predicate for token in ("持有", "拥有", "携带", "遗失", "典当")):
                facts_items.append(obj or subject)

        locks = {
            "time_lock": {
                "entries": [
                    self._entry("timeline_start", "时间起点", str(getattr(plan, "timeline_start", "") or ""), source="chapter_plan"),
                    self._entry("timeline_end", "时间终点", str(getattr(plan, "timeline_end", "") or ""), source="chapter_plan"),
                ]
            },
            "location_lock": {
                "entries": [
                    *[
                        self._entry(
                            key=f"location_{index + 1}",
                            label="允许地点",
                            value=location,
                            source="story_bible",
                            kind="allowed_location",
                        )
                        for index, location in enumerate(inferred_locations)
                    ],
                    self._entry("required_end_location", "章节终态地点", ending_target, source="fact_store", kind="ending_location"),
                ]
            },
            "character_lock": {
                "entries": [
                    *[
                        self._entry(
                            key=f"character_{index + 1}",
                            label="关键人物",
                            value=name,
                            source="story_bible",
                            kind="required_character",
                        )
                        for index, name in enumerate(involved_characters)
                    ],
                    *[
                        self._entry(
                            key=f"forbidden_character_{index + 1}",
                            label="禁入人物",
                            value=name,
                            source="fact_store",
                            kind="forbidden_character",
                        )
                        for index, name in enumerate(list(dict.fromkeys(filter(None, forbidden_characters))))
                    ],
                ]
            },
            "item_lock": {
                "entries": [
                    self._entry(
                        key=f"item_{index + 1}",
                        label="关键道具",
                        value=item,
                        source="fact_store",
                        kind="required_item",
                    )
                    for index, item in enumerate(list(dict.fromkeys(filter(None, facts_items))))
                ]
            },
            "numeric_lock": {"entries": numeric_entries},
            "event_lock": {
                "entries": [
                    *[
                        self._entry(
                            key=f"event_{index + 1}",
                            label="关键事件",
                            value=line,
                            source="chapter_plan",
                            kind="required_event",
                        )
                        for index, line in enumerate(event_lines)
                    ],
                    *[
                        self._entry(
                            key=f"forbidden_event_{index + 1}",
                            label="禁止事件",
                            value=line,
                            source="fact_store",
                            kind="forbidden_event",
                        )
                        for index, line in enumerate(list(dict.fromkeys(filter(None, forbidden_events))))
                    ],
                ]
            },
            "ending_lock": {
                "entries": [
                    self._entry("ending_target", "目标终态", ending_target, source="fact_store", kind="ending_target")
                ]
            },
        }
        locks["time_lock"]["entries"] = [entry for entry in locks["time_lock"]["entries"] if entry["value"]]
        inference_notes = []
        if prev_end_location and ending_target and prev_end_location != ending_target:
            inference_notes.append("章节终态根据上章章末状态与当前规划共同归一。")
        if len(involved_characters) > 1:
            inference_notes.append("人物锁按 POV 与规划中显式提及的人物归纳。")
        return self._normalize_groups(locks), inference_notes

    @staticmethod
    def _entry(key: str, label: str, value: Any, *, source: str, kind: str = "constraint") -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "value": value,
            "source": source,
            "kind": kind,
            "status": "normal",
            "metadata": {},
        }

    def _normalize_groups(self, groups: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        for key in LOCK_GROUP_KEYS:
            group = deepcopy(groups.get(key) or {"entries": []})
            entries = []
            for entry in group.get("entries", []):
                if not isinstance(entry, dict):
                    continue
                item = {
                    "key": str(entry.get("key") or f"{key}_{len(entries) + 1}"),
                    "label": str(entry.get("label") or entry.get("key") or ""),
                    "value": entry.get("value"),
                    "source": str(entry.get("source") or "manual"),
                    "kind": str(entry.get("kind") or "constraint"),
                    "status": str(entry.get("status") or "normal"),
                    "metadata": dict(entry.get("metadata") or {}),
                }
                if item["value"] in ("", None, []):
                    continue
                entries.append(item)
            normalized[key] = {"entries": entries}
        return normalized

    def _with_statuses(self, snapshot: StateLockSnapshotDTO) -> StateLockSnapshotDTO:
        chapter = self.chapter_repository.get_by_id(ChapterId(snapshot.chapter_id))
        text = chapter.content if chapter else ""
        latest = self.state_lock_repository.get_current_by_chapter(snapshot.chapter_id)
        output = deepcopy(snapshot)
        output.locks = self._normalize_groups(output.locks)
        newer_exists = latest.version > output.version if latest else False
        simple_violations = self.evaluate_text_violations(snapshot.chapter_id, snapshot.version, text=text)
        violation_keys = {(issue["group"], issue["entry_key"]) for issue in simple_violations}
        for group_key, group in output.locks.items():
            for entry in group.get("entries", []):
                metadata = dict(entry.get("metadata") or {})
                if group_key == "ending_lock" and newer_exists:
                    metadata["newer_version_exists"] = True
                if entry.get("status") != "manually_modified":
                    entry["status"] = "violated" if (group_key, entry.get("key")) in violation_keys else "normal"
                entry["metadata"] = metadata
        return output

    @staticmethod
    def _extract_location(text: str) -> str:
        if not text:
            return ""
        parts = [segment.strip() for segment in re.split(r"[，。,；;\n]", text) if segment.strip()]
        return parts[-1] if parts else text.strip()

    @staticmethod
    def _first_entry_value(group: Dict[str, Any]) -> str:
        entries = group.get("entries", []) if isinstance(group, dict) else []
        if not entries:
            return ""
        return str(entries[0].get("value") or "").strip()

    def _changed_fields(self, previous: Dict[str, Dict[str, Any]], current: Dict[str, Dict[str, Any]]) -> List[str]:
        changed = []
        for key in LOCK_GROUP_KEYS:
            if previous.get(key, {"entries": []}) != current.get(key, {"entries": []}):
                changed.append(key)
        return changed

    def _apply_manual_status(
        self,
        groups: Dict[str, Dict[str, Any]],
        changed_fields: List[str],
        reason: str,
    ) -> Dict[str, Dict[str, Any]]:
        groups = deepcopy(groups)
        for group_key in changed_fields:
            for entry in groups.get(group_key, {}).get("entries", []):
                entry["status"] = "manually_modified"
                metadata = dict(entry.get("metadata") or {})
                metadata["change_reason"] = reason
                entry["metadata"] = metadata
        return groups

    def _detect_critical_change(
        self,
        previous: Dict[str, Dict[str, Any]] | None,
        current: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if previous is None:
            return {"changed": False, "domains": []}
        domains = []
        for key in ("ending_lock", "numeric_lock", "character_lock", "event_lock"):
            if previous.get(key, {"entries": []}) != current.get(key, {"entries": []}):
                domains.append(key)
        return {"changed": bool(domains), "domains": domains}

    def _mark_impacted_fusion_drafts(
        self,
        chapter_id: str,
        previous: StateLockSnapshotDTO | None,
        current: StateLockSnapshotDTO,
    ) -> None:
        if previous is None:
            return
        critical = current.critical_change or {}
        if not critical.get("changed"):
            return
        status = "needs_refusion" if "ending_lock" in critical.get("domains", []) else "stale"
        logger.info(
            "state lock impacted fusion drafts chapter_id=%s current_version=%s status=%s domains=%s",
            chapter_id,
            current.version,
            status,
            ",".join(critical.get("domains", [])) if critical.get("domains") else "-",
        )
        self.fusion_repository.mark_drafts_stale(
            chapter_id=chapter_id,
            min_state_lock_version=current.version,
            status=status,
        )

    @staticmethod
    def _should_use_llm_inference(
        *,
        ending_target: str,
        inferred_locations: List[str],
        involved_characters: List[str],
        facts: List[Any],
    ) -> bool:
        if not ending_target:
            return True
        if len(inferred_locations) > 1:
            return True
        if not involved_characters and len(facts) > 0:
            return True
        return False

    async def _apply_llm_inference_if_needed(
        self,
        *,
        chapter,
        plan,
        previous_summary,
        current_summary,
        facts: List[Any],
        locks: Dict[str, Dict[str, Any]],
        inference_notes: List[str],
    ) -> tuple[Dict[str, Dict[str, Any]], List[str]]:
        ending_target = self._first_entry_value(locks.get("ending_lock", {}))
        inferred_locations = [
            str(entry.get("value") or "").strip()
            for entry in locks.get("location_lock", {}).get("entries", [])
            if entry.get("kind") == "allowed_location"
        ]
        involved_characters = [
            str(entry.get("value") or "").strip()
            for entry in locks.get("character_lock", {}).get("entries", [])
            if entry.get("kind") == "required_character"
        ]
        if not self._should_use_llm_inference(
            ending_target=ending_target,
            inferred_locations=inferred_locations,
            involved_characters=involved_characters,
            facts=facts,
        ):
            logger.info(
                "state lock inference skipped reason=signal_sufficient ending_target=%s location_count=%s character_count=%s fact_count=%s",
                bool(ending_target),
                len(inferred_locations),
                len(involved_characters),
                len(facts),
            )
            return locks, inference_notes
        logger.info(
            "state lock inference running chapter_title=%s ending_target=%s location_count=%s character_count=%s fact_count=%s",
            str(getattr(chapter, "title", "") or ""),
            bool(ending_target),
            len(inferred_locations),
            len(involved_characters),
            len(facts),
        )
        llm_candidate = await self._infer_with_llm(
            chapter_title=str(getattr(chapter, "title", "") or ""),
            chapter_outline=str(getattr(plan, "outline", "") or getattr(chapter, "outline", "") or ""),
            plan_description=str(getattr(plan, "description", "") or ""),
            previous_ending_state=str(getattr(previous_summary, "ending_state", "") or ""),
            current_ending_state=str(getattr(current_summary, "ending_state", "") or ""),
            involved_characters=involved_characters,
            inferred_locations=inferred_locations,
            fact_lines=[
                f"{getattr(fact, 'subject', '')} {getattr(fact, 'predicate', '')} {getattr(fact, 'object', '')}".strip()
                for fact in facts[:20]
            ],
        )
        if llm_candidate is None:
            logger.warning("state lock inference failed reason=llm_unavailable_or_invalid_output")
            return locks, inference_notes
        inference_notes = list(inference_notes) + [note for note in llm_candidate.notes if note]
        if llm_candidate.ending_target and not ending_target:
            locks["ending_lock"]["entries"] = [
                self._entry(
                    "ending_target",
                    "目标终态",
                    llm_candidate.ending_target,
                    source="llm_inference",
                    kind="ending_target",
                )
            ]
            required_end = next(
                (
                    entry
                    for entry in locks["location_lock"]["entries"]
                    if entry.get("key") == "required_end_location"
                ),
                None,
            )
            if required_end is not None:
                required_end["value"] = llm_candidate.ending_target
                required_end["source"] = "llm_inference"
        for mapping in llm_candidate.alias_mappings:
            for entry in locks["character_lock"]["entries"]:
                if entry.get("value") == mapping.canonical_name:
                    metadata = dict(entry.get("metadata") or {})
                    aliases = list(metadata.get("aliases") or [])
                    if mapping.alias and mapping.alias not in aliases:
                        aliases.append(mapping.alias)
                    metadata["aliases"] = aliases
                    entry["metadata"] = metadata
        existing_items = {str(entry.get("value") or "").strip() for entry in locks["item_lock"]["entries"]}
        for index, item in enumerate(llm_candidate.inferred_items, start=1):
            if item and item not in existing_items:
                locks["item_lock"]["entries"].append(
                    self._entry(
                        key=f"llm_item_{index}",
                        label="推断道具",
                        value=item,
                        source="llm_inference",
                        kind="required_item",
                    )
                )
        existing_events = {str(entry.get("value") or "").strip() for entry in locks["event_lock"]["entries"]}
        for index, event in enumerate(llm_candidate.inferred_events, start=1):
            if event and event not in existing_events:
                locks["event_lock"]["entries"].append(
                    self._entry(
                        key=f"llm_event_{index}",
                        label="推断事件",
                        value=event,
                        source="llm_inference",
                        kind="required_event",
                    )
                )
        inference_notes.append("LLM 已参与别名/终态歧义归一。")
        logger.info(
            "state lock inference completed ending_target=%s alias_mappings=%s inferred_items=%s inferred_events=%s notes=%s",
            bool(llm_candidate.ending_target),
            len(llm_candidate.alias_mappings),
            len(llm_candidate.inferred_items),
            len(llm_candidate.inferred_events),
            len(llm_candidate.notes),
        )
        return self._normalize_groups(locks), inference_notes

    async def _infer_with_llm(
        self,
        *,
        chapter_title: str,
        chapter_outline: str,
        plan_description: str,
        previous_ending_state: str,
        current_ending_state: str,
        involved_characters: List[str],
        inferred_locations: List[str],
        fact_lines: List[str],
    ) -> Optional[StateLockInferencePayload]:
        if self.llm_service is None:
            return None
        prompt = Prompt(
            system=(
                "你是章节状态锁推断助手。"
                "只输出一个 JSON 对象。"
                "任务是补充章节终态、人物别名映射、隐含道具和隐含事件。"
            ),
            user=(
                "请根据以下上下文补充状态锁候选，"
                "若无法确定请保留空字符串或空数组。\n\n"
                f"章节标题：{chapter_title or '未命名章节'}\n"
                f"章节大纲：\n{chapter_outline or '无'}\n\n"
                f"规划描述：\n{plan_description or '无'}\n\n"
                f"上章终态：{previous_ending_state or '无'}\n"
                f"当前章终态描述：{current_ending_state or '无'}\n"
                f"已识别人物：{json.dumps(involved_characters, ensure_ascii=False)}\n"
                f"候选地点：{json.dumps(inferred_locations, ensure_ascii=False)}\n"
                f"事实线索：{json.dumps(fact_lines, ensure_ascii=False)}\n\n"
                "返回字段：ending_target, alias_mappings, inferred_items, inferred_events, notes。"
            ),
        )
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=800, temperature=0.2),
            )
        except Exception:
            return None
        cleaned = sanitize_llm_output(result.content if hasattr(result, "content") else str(result))
        data, errors = parse_and_repair_json(cleaned)
        if data is None or errors:
            return None
        payload, schema_errors = validate_json_schema(data, StateLockInferencePayload)
        if payload is None or schema_errors:
            return None
        return payload
