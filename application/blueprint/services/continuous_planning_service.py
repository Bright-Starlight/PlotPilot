"""AI 持续规划服务

整合宏观规划、幕级规划、AI 续规划为统一的服务
"""

import json
import uuid
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
from json_repair import repair_json

from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource
from domain.structure.chapter_element import ChapterElement, ElementType, RelationType, Importance
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.repositories.chapter_repository import ChapterRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.audit.services.macro_merge_engine import MacroMergeEngine, MergePlan, MergeConflictException

logger = logging.getLogger(__name__)
_macro_plan_progress_store: Dict[str, Dict] = {}
_macro_plan_result_store: Dict[str, Dict] = {}


class PlanningMode(str, Enum):
    """规划确认模式"""
    SKIP_IF_EXISTS = "skip"      # 已有规划时跳过，返回已有规划
    APPEND = "append"             # 追加模式：保留已有规划，追加新章节
    OVERWRITE = "overwrite"       # 覆盖模式：删除已有规划，写入新规划


def _sanitize_llm_json_output(raw: str) -> str:
    content = (raw or "").strip()
    content = re.sub(r"\x1b\[[0-9;]*m", "", content)
    content = re.sub(r"<think\|?>.*?</think\|?>", "", content, flags=re.DOTALL)
    content = re.sub(r"<thinking>.*?</thinking>", "", content, flags=re.DOTALL)
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]
    return content.strip()


def _extract_outer_json_value(text: str) -> str:
    obj_start = text.find("{")
    arr_start = text.find("[")
    if obj_start != -1:
        start = obj_start
    elif arr_start != -1:
        start = arr_start
    else:
        return text

    root_char = text[start]
    root_close = "}" if root_char == "{" else "]"
    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == root_char:
            depth += 1
            continue
        if ch == root_close:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return text[start:]


def _repair_json_string(text: str) -> str:
    text = text.strip()
    if not text:
        return text

    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    def _close_json(s: str) -> str:
        s = s.strip()
        if not s:
            return "{}"

        in_string = False
        escape = False
        stack = []
        result = []

        for ch in s:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == "\\" and in_string:
                result.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string:
                result.append(ch)
                continue
            if ch == "{":
                stack.append("}")
                result.append(ch)
                continue
            if ch == "[":
                stack.append("]")
                result.append(ch)
                continue
            if ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
                result.append(ch)
                continue
            result.append(ch)

        if in_string:
            result.append('"')

        repaired = "".join(result).rstrip()
        while repaired.endswith(","):
            repaired = repaired[:-1].rstrip()
        while stack:
            while repaired.endswith(","):
                repaired = repaired[:-1].rstrip()
            repaired += stack.pop()
        return repaired

    candidate = text
    retries = 15
    while retries > 0 and candidate:
        repaired = _close_json(candidate)
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            last_comma = candidate.rfind(",")
            if last_comma == -1:
                break
            candidate = candidate[:last_comma]
        retries -= 1
    return _close_json(text)


# 导出 MergeConflictException 供路由层使用
__all__ = ['ContinuousPlanningService', 'MergeConflictException']


def get_macro_plan_progress(novel_id: str) -> Dict:
    return _macro_plan_progress_store.get(novel_id, {
        "status": "idle",
        "current": 0,
        "total": 0,
        "percent": 0,
        "message": "",
    }).copy()


def get_macro_plan_result(novel_id: str) -> Dict:
    return _macro_plan_result_store.get(novel_id, {
        "ready": False,
        "result": None,
        "error": None,
    }).copy()


class ContinuousPlanningService:
    """AI 持续规划服务

    统一的规划服务，包含：
    1. 宏观规划：生成部-卷-幕结构框架
    2. 幕级规划：为指定幕生成章节规划
    3. AI 续规划：自动判断何时创建新幕
    """

    def __init__(
        self,
        story_node_repo: StoryNodeRepository,
        chapter_element_repo: ChapterElementRepository,
        llm_service: LLMService,
        bible_service=None,
        chapter_repository: Optional[ChapterRepository] = None,
        knowledge_service=None,
        novel_repository=None,
        foreshadowing_repository=None,
        theme_registry=None,
    ):
        self.story_node_repo = story_node_repo
        self.chapter_element_repo = chapter_element_repo
        self.llm_service = llm_service
        self.bible_service = bible_service
        self.chapter_repository = chapter_repository
        self.knowledge_service = knowledge_service
        self.novel_repository = novel_repository
        self.foreshadowing_repository = foreshadowing_repository
        self.theme_registry = theme_registry

    def _build_theme_context_prompt(self, novel_id: str, chapter_number: int, outline: str) -> str:
        """构建题材上下文提示词

        从 ThemeAgent 获取 world_rules、atmosphere、taboos、tropes 等内容，
        格式化为可注入 prompt 的文本。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲

        Returns:
            格式化后的题材上下文文本，空字符串 if 无 agent
        """
        if not self.theme_registry or not self.novel_repository:
            return ""

        try:
            # Get novel to find genre
            novel = self.novel_repository.get_by_id(novel_id)
            if not novel:
                return ""

            genre = getattr(novel, 'genre', None) or ""
            if not genre:
                return ""

            agent = self.theme_registry.get_or_default(genre)
            if not agent:
                return ""

            directives = agent.get_context_directives(novel_id, chapter_number, outline)
            return directives.to_context_text()

        except Exception as e:
            logger.warning(f"Failed to build theme context prompt: {e}")
            return ""

    # ==================== 宏观规划 ====================

    async def generate_macro_plan(
        self,
        novel_id: str,
        target_chapters: int,
        structure_preference: Optional[Dict[str, int]]
    ) -> Dict:
        """生成宏观规划

        Args:
            novel_id: 小说 ID
            target_chapters: 目标章节数
            structure_preference: 结构偏好配置（None 表示快速生成模式，AI 自主决定）
                - parts: 部数
                - volumes_per_part: 每部卷数
                - acts_per_volume: 每卷幕数

        Returns:
            包含 success、structure、quality_metrics 的字典
        """
        import time
        start_time = time.time()

        logger.info(f"Generating macro plan for novel {novel_id}")
        self._update_macro_progress(novel_id, status="running", current=0, total=0, message="正在准备结构规划")

        # 获取 Bible 信息
        bible_context = self._get_bible_context(novel_id)

        # 获取小说题材
        genre = ""
        if self.novel_repository:
            novel = self.novel_repository.get_by_id(NovelId(novel_id))
            if novel:
                genre = novel.genre

        try:
            if structure_preference is None:
                # 构建提示词
                prompt = self._build_macro_planning_prompt(
                    bible_context=bible_context,
                    target_chapters=target_chapters,
                    structure_preference=structure_preference,
                    genre=genre,
                )

                # 调用 LLM 生成规划
                config = GenerationConfig(max_tokens=4096, temperature=0.7)
                response = await self.llm_service.generate(prompt, config)
                structure = self._parse_llm_response(response)
            else:
                structure = await self._generate_precise_macro_plan(
                    novel_id=novel_id,
                    bible_context=bible_context,
                    target_chapters=target_chapters,
                    structure_preference=structure_preference,
                    genre=genre,
                )

            # 评估规划质量
            elapsed_time = time.time() - start_time
            quality_metrics = self._evaluate_macro_plan_quality(
                structure=structure,
                bible_context=bible_context,
                target_chapters=target_chapters,
                structure_preference=structure_preference
            )

            logger.info(f"[MacroPlanQuality] novel={novel_id}, time={elapsed_time:.2f}s, metrics={quality_metrics}")
            self._update_macro_progress(
                novel_id,
                status="completed",
                current=self._get_total_volumes(structure_preference),
                total=self._get_total_volumes(structure_preference),
                message="结构规划生成完成",
            )

            return {
                "success": True,
                "structure": structure.get("parts", []),
                "quality_metrics": quality_metrics,
                "generation_time": elapsed_time
            }
        except Exception:
            self._update_macro_progress(
                novel_id,
                status="failed",
                message="结构规划生成失败",
            )
            raise

    async def _generate_precise_macro_plan(
        self,
        novel_id: str,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict[str, int],
        genre: str = "",
    ) -> Dict:
        """精密模式：系统先搭固定骨架，整版生成后再定向补全缺失字段。"""
        skeleton = self._build_precise_structure_skeleton(target_chapters, structure_preference)
        total_volumes = self._get_total_volumes(structure_preference)
        self._update_macro_progress(
            novel_id,
            status="running",
            current=0,
            total=total_volumes,
            message="正在生成整版叙事骨架",
        )

        prompt = self._build_precise_macro_prompt(
            bible_context=bible_context,
            target_chapters=target_chapters,
            structure_preference=structure_preference,
            skeleton=skeleton,
            genre=genre,
        )
        config = GenerationConfig(
            max_tokens=self._calculate_precise_max_tokens(structure_preference),
            temperature=0.7,
        )
        response = await self.llm_service.generate(prompt, config)
        updates = self._parse_llm_response(response)
        self._merge_precise_structure_updates(
            skeleton=skeleton,
            updates=updates,
            target_chapters=target_chapters,
            rebalance=False,
        )
        self._update_macro_progress(
            novel_id,
            status="running",
            current=max(total_volumes - 1, 0),
            total=total_volumes,
            message="正在检查并补全缺失字段",
        )

        incomplete_acts = self._find_incomplete_precise_acts(skeleton)
        if incomplete_acts:
            repair_prompt = self._build_precise_repair_prompt(
                bible_context=bible_context,
                target_chapters=target_chapters,
                structure_preference=structure_preference,
                incomplete_acts=incomplete_acts,
                full_skeleton=skeleton,  # 传递完整结构树
            )
            repair_config = GenerationConfig(
                max_tokens=self._calculate_precise_repair_max_tokens(incomplete_acts),
                temperature=0.5,
            )
            repair_response = await self.llm_service.generate(repair_prompt, repair_config)
            repair_updates = self._parse_llm_response(repair_response)
            self._merge_precise_structure_updates(
                skeleton=skeleton,
                updates=repair_updates,
                target_chapters=target_chapters,
                rebalance=False,
            )

        all_acts = [
            act
            for part in skeleton.get("parts", [])
            for volume in part.get("volumes", [])
            for act in volume.get("acts", [])
        ]
        self._rebalance_act_chapters(all_acts, target_chapters)
        return skeleton

    def _build_precise_structure_skeleton(
        self,
        target_chapters: int,
        structure_preference: Dict[str, int]
    ) -> Dict:
        """按用户指定网格构造固定骨架，节点数量不交给 AI 决定。"""
        parts = structure_preference.get("parts", 3)
        volumes_per_part = structure_preference.get("volumes_per_part", 3)
        acts_per_volume = structure_preference.get("acts_per_volume", 3)
        total_acts = max(parts * volumes_per_part * acts_per_volume, 1)
        avg_chapters_per_act = max(target_chapters // total_acts, 1)

        structure = {"parts": []}
        for part_index in range(1, parts + 1):
            part_node = {
                "node_id": f"P{part_index}",
                "title": f"第{part_index}部",
                "description": "",
                "volumes": [],
            }
            for volume_index in range(1, volumes_per_part + 1):
                volume_node = {
                    "node_id": f"V{part_index}_{volume_index}",
                    "title": f"第{volume_index}卷",
                    "description": "",
                    "acts": [],
                }
                for act_index in range(1, acts_per_volume + 1):
                    volume_node["acts"].append({
                        "node_id": f"A{part_index}_{volume_index}_{act_index}",
                        "title": f"第{act_index}幕",
                        "description": "",
                        "estimated_chapters": avg_chapters_per_act,
                        "narrative_goal": "",
                        "plot_points": [],
                        "key_characters": [],
                        "key_locations": [],
                        "emotional_arc": "",
                        "setup_for": [],
                        "payoff_from": [],
                    })
                part_node["volumes"].append(volume_node)
            structure["parts"].append(part_node)
        return structure

    def _merge_precise_structure_updates(
        self,
        skeleton: Dict,
        updates: Dict,
        target_chapters: int,
        rebalance: bool = True,
    ) -> Dict:
        """将 AI 返回的内容更新合并回固定骨架。"""
        node_index: Dict[str, Dict] = {}
        acts: List[Dict] = []

        for part in skeleton.get("parts", []):
            node_index[part["node_id"]] = part
            for volume in part.get("volumes", []):
                node_index[volume["node_id"]] = volume
                for act in volume.get("acts", []):
                    node_index[act["node_id"]] = act
                    acts.append(act)

        for update in updates.get("node_updates", []):
            if not isinstance(update, dict):
                continue
            node_id = str(update.get("node_id") or "").strip()
            if not node_id or node_id not in node_index:
                continue
            self._apply_precise_node_update(node_index[node_id], update)

        if rebalance:
            self._rebalance_act_chapters(acts, target_chapters)
        return skeleton

    def _apply_precise_node_update(self, node: Dict, update: Dict) -> None:
        title = str(update.get("title") or "").strip()
        description = str(update.get("description") or "").strip()
        if title:
            node["title"] = title
        if description:
            node["description"] = description

        if "estimated_chapters" in node:
            estimated = update.get("estimated_chapters")
            try:
                node["estimated_chapters"] = max(int(estimated), 0)
            except (TypeError, ValueError):
                pass
            for field in (
                "narrative_goal",
                "emotional_arc",
            ):
                value = str(update.get(field) or "").strip()
                if value:
                    node[field] = value
            for field in (
                "plot_points",
                "key_characters",
                "key_locations",
                "setup_for",
                "payoff_from",
            ):
                value = update.get(field)
                if isinstance(value, list):
                    node[field] = [str(item).strip() for item in value if str(item).strip()]

    def _rebalance_act_chapters(self, acts: List[Dict], target_chapters: int) -> None:
        """将各幕 estimated_chapters 归一到目标总章数。"""
        if not acts:
            return

        min_each = 1 if target_chapters >= len(acts) else 0
        remaining = max(target_chapters - min_each * len(acts), 0)

        weights = []
        for act in acts:
            try:
                value = int(act.get("estimated_chapters", 0) or 0)
            except (TypeError, ValueError):
                value = 0
            weights.append(max(value, 1))

        total_weight = sum(weights) or len(acts)
        scaled = [weight * remaining / total_weight for weight in weights]
        allocations = [int(value) for value in scaled]
        leftover = remaining - sum(allocations)
        remainders = sorted(
            enumerate(scaled),
            key=lambda item: item[1] - int(item[1]),
            reverse=True,
        )
        for index, _ in remainders[:leftover]:
            allocations[index] += 1

        for act, extra in zip(acts, allocations):
            act["estimated_chapters"] = min_each + extra

    def _calculate_precise_max_tokens(self, structure_preference: Dict[str, int]) -> int:
        total_volumes = self._get_total_volumes(structure_preference)
        total_acts = max(
            structure_preference.get("parts", 0)
            * structure_preference.get("volumes_per_part", 0)
            * structure_preference.get("acts_per_volume", 0),
            1,
        )
        return min(12_000, max(3_072, 2_048 + total_volumes * 400 + total_acts * 120))

    def _calculate_precise_repair_max_tokens(self, incomplete_acts: List[Dict]) -> int:
        return min(6_000, max(1_536, 768 + len(incomplete_acts) * 320))

    def _find_incomplete_precise_acts(self, skeleton: Dict) -> List[Dict]:
        required_text_fields = ("narrative_goal", "emotional_arc")
        required_list_fields = ("plot_points", "key_characters", "key_locations")
        incomplete = []
        for part in skeleton.get("parts", []):
            part_id = part.get("node_id", "")
            part_title = part.get("title", "")
            for volume in part.get("volumes", []):
                volume_id = volume.get("node_id", "")
                volume_title = volume.get("title", "")
                volume_acts = volume.get("acts", [])
                for act_idx, act in enumerate(volume_acts):
                    missing_fields = [
                        field for field in required_text_fields
                        if not str(act.get(field) or "").strip()
                    ]
                    missing_fields.extend(
                        field for field in required_list_fields
                        if not isinstance(act.get(field), list) or not act.get(field)
                    )
                    if missing_fields:
                        incomplete.append({
                            "node_id": act["node_id"],
                            "title": act.get("title", ""),
                            "description": act.get("description", ""),
                            "estimated_chapters": act.get("estimated_chapters", 0),
                            "setup_for": act.get("setup_for", []),
                            "payoff_from": act.get("payoff_from", []),
                            "missing_fields": missing_fields,
                            # 层级上下文
                            "part_id": part_id,
                            "part_title": part_title,
                            "volume_id": volume_id,
                            "volume_title": volume_title,
                            # 同卷其他幕（用于理解前后关系）
                            "sibling_acts": [
                                {
                                    "node_id": sibling["node_id"],
                                    "title": sibling.get("title", ""),
                                    "description": sibling.get("description", ""),
                                }
                                for sibling_idx, sibling in enumerate(volume_acts)
                                if sibling_idx != act_idx
                            ],
                        })
        return incomplete

    def _get_total_volumes(self, structure_preference: Optional[Dict[str, int]]) -> int:
        if not structure_preference:
            return 0
        return max(
            structure_preference.get("parts", 0) * structure_preference.get("volumes_per_part", 0),
            0,
        )

    def _update_macro_progress(
        self,
        novel_id: str,
        *,
        status: str,
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        progress = _macro_plan_progress_store.get(novel_id, {
            "status": "idle",
            "current": 0,
            "total": 0,
            "percent": 0,
            "message": "",
        }).copy()
        progress["status"] = status
        if current is not None:
            progress["current"] = current
        if total is not None:
            progress["total"] = total
        total_value = progress.get("total", 0) or 0
        current_value = progress.get("current", 0) or 0
        progress["percent"] = round(current_value / total_value * 100, 1) if total_value else 0
        if message is not None:
            progress["message"] = message
        _macro_plan_progress_store[novel_id] = progress

    def initialize_macro_plan_task(self, novel_id: str) -> None:
        _macro_plan_result_store[novel_id] = {
            "ready": False,
            "result": None,
            "error": None,
        }
        self._update_macro_progress(
            novel_id,
            status="running",
            current=0,
            total=0,
            message="正在准备结构规划",
        )

    def store_macro_plan_result(self, novel_id: str, result: Dict) -> None:
        _macro_plan_result_store[novel_id] = {
            "ready": True,
            "result": result,
            "error": None,
        }

    def store_macro_plan_error(self, novel_id: str, error: str) -> None:
        _macro_plan_result_store[novel_id] = {
            "ready": False,
            "result": None,
            "error": error,
        }

    def _evaluate_macro_plan_quality(
        self,
        structure: Dict,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict[str, int]
    ) -> Dict:
        """评估宏观规划质量

        用于持续优化提示词效果，记录关键指标：
        - 结构完整性：部/卷/幕数量是否符合预期
        - 世界观融合度：Bible 元素在结构中的出现比例
        - 冲突密度：每幕是否有明确的冲突描述
        - 标题质量：标题长度、词汇多样性等
        """
        parts = structure.get("parts", [])

        # 基础统计
        part_count = len(parts)
        volume_count = sum(len(p.get("volumes", [])) for p in parts)
        act_count = sum(
            len(v.get("acts", []))
            for p in parts
            for v in p.get("volumes", [])
        )

        # 检查结构偏好匹配度
        expected_parts = structure_preference.get("parts") if structure_preference else None
        structure_match = {
            "parts_match": expected_parts is None or part_count == expected_parts,
            "expected_parts": expected_parts,
            "actual_parts": part_count
        }

        # 收集所有幕
        all_acts = []
        for p in parts:
            for v in p.get("volumes", []):
                all_acts.extend(v.get("acts", []))

        # 评估冲突密度
        acts_with_conflict = sum(
            1 for a in all_acts
            if a.get("core_conflict") and len(a.get("core_conflict", "")) > 10
        )
        conflict_density = acts_with_conflict / len(all_acts) if all_acts else 0

        # 评估世界观融合度
        bible_chars = {c.get("name", "").lower() for c in bible_context.get("characters", [])}
        bible_locations = {l.get("name", "").lower() for l in bible_context.get("locations", [])}

        char_mentions = 0
        location_mentions = 0
        for act in all_acts:
            desc = act.get("description", "").lower()
            title = act.get("title", "").lower()
            text = desc + " " + title

            for char in bible_chars:
                if char and char in text:
                    char_mentions += 1
                    break

            for loc in bible_locations:
                if loc and loc in text:
                    location_mentions += 1
                    break

        world_fusion = {
            "character_coverage": char_mentions / len(all_acts) if all_acts else 0,
            "location_coverage": location_mentions / len(all_acts) if all_acts else 0
        }

        # 评估标题质量
        titles = [a.get("title", "") for a in all_acts]
        avg_title_length = sum(len(t) for t in titles) / len(titles) if titles else 0

        # 检查标题是否包含动词（简单启发式）
        action_words = ["战", "杀", "破", "夺", "逃", "追", "救", "毁", "变", "觉醒", "背叛", "降临", "崛起", "坠落", "燃烧", "冻结", "撕裂", "缝合"]
        titles_with_action = sum(1 for t in titles if any(w in t for w in action_words))
        title_action_ratio = titles_with_action / len(titles) if titles else 0

        # 检查是否有情绪反转字段（新提示词特性）
        acts_with_emotion = sum(1 for a in all_acts if a.get("emotional_turn"))
        emotion_field_ratio = acts_with_emotion / len(all_acts) if all_acts else 0

        return {
            "structure_stats": {
                "parts": part_count,
                "volumes": volume_count,
                "acts": act_count
            },
            "structure_match": structure_match,
            "conflict_density": round(conflict_density, 2),
            "world_fusion": {
                "character_coverage": round(world_fusion["character_coverage"], 2),
                "location_coverage": round(world_fusion["location_coverage"], 2)
            },
            "title_quality": {
                "avg_length": round(avg_title_length, 1),
                "action_word_ratio": round(title_action_ratio, 2)
            },
            "prompt_version_features": {
                "emotional_turn_field": round(emotion_field_ratio, 2),
                "key_characters_field": round(sum(1 for a in all_acts if a.get("key_characters")) / len(all_acts), 2) if all_acts else 0
            }
        }

    async def confirm_macro_plan(self, novel_id: str, structure: List[Dict]) -> Dict:
        """确认宏观规划（旧版本，不安全，保留用于向后兼容）

        ⚠️ 警告：此方法不检查已有数据，可能导致僵尸节点或数据丢失
        推荐使用 confirm_macro_plan_safe() 方法
        """
        logger.warning(f"Using unsafe confirm_macro_plan for novel {novel_id}")
        logger.info(f"Confirming macro plan for novel {novel_id}")

        created_nodes = []
        order_index = 0
        part_number = 0
        volume_number = 0
        act_number = 0

        for part_data in structure:
            part_number += 1
            part_data["number"] = part_number
            part_node = self._create_node_from_data(
                novel_id, None, NodeType.PART, part_data, order_index
            )
            created_nodes.append(part_node)
            order_index += 1

            for volume_data in part_data.get("volumes", []):
                volume_number += 1
                volume_data["number"] = volume_number
                volume_node = self._create_node_from_data(
                    novel_id, part_node.id, NodeType.VOLUME, volume_data, order_index
                )
                created_nodes.append(volume_node)
                order_index += 1

                for act_data in volume_data.get("acts", []):
                    act_number += 1
                    act_data["number"] = act_number
                    act_node = self._create_node_from_data(
                        novel_id, volume_node.id, NodeType.ACT, act_data, order_index
                    )
                    created_nodes.append(act_node)
                    order_index += 1

        await self.story_node_repo.save_batch(created_nodes)

        return {
            "success": True,
            "created_nodes": len(created_nodes),
            "message": f"已创建 {len(created_nodes)} 个结构节点"
        }

    async def confirm_macro_plan_safe(self, novel_id: str, structure: List[Dict]) -> Dict:
        """安全的宏观规划确认（带血缘继承的智能合并）

        核心机制：
        1. 自底向上标记承载者（有正文的节点）
        2. 三路比对（create/update/delete）
        3. 冲突检测（红色阻断）
        4. 原子性事务执行

        Args:
            novel_id: 小说 ID
            structure: 新的宏观结构（部-卷-幕）

        Returns:
            合并结果，包含 summary（GREEN/YELLOW/RED 状态）

        Raises:
            MergeConflictException: 当新结构试图删除包含正文的节点时
        """
        logger.info(f"[SafeMerge] Starting safe macro plan confirmation for novel {novel_id}")

        # 阶段 1：深度扫描 - 获取旧结构
        old_nodes_entities = await self.story_node_repo.get_by_novel(novel_id)
        logger.info(f"[SafeMerge] Found {len(old_nodes_entities)} existing nodes")

        # 标准化旧节点：Entity → Dict（Enum 序列化）
        old_nodes = [
            {
                "id": node.id,
                "novel_id": node.novel_id,
                "parent_id": node.parent_id,
                "node_type": node.node_type.value,  # NodeType.CHAPTER → 'CHAPTER'
                "number": node.number,
                "title": node.title,
                "description": node.description,
                "order_index": node.order_index,
            }
            for node in old_nodes_entities
        ]

        # 标准化新节点：扁平化嵌套结构 → 平面列表
        new_nodes = self._flatten_structure_to_nodes(novel_id, structure)
        logger.info(f"[SafeMerge] Generated {len(new_nodes)} new nodes")

        # 阶段 2：匹配与继承 - 执行比对
        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()
        logger.info(f"[SafeMerge] Merge plan: creates={len(plan.creates)}, updates={len(plan.updates)}, deletes={len(plan.deletes)}, conflicts={len(plan.conflicts)}")

        # 阶段 3：冲突检测 - 红色阻断
        if plan.has_fatal_conflict:
            logger.error(f"[SafeMerge] Fatal conflicts detected: {plan.conflicts}")
            raise MergeConflictException(
                message="重构导致部分已有正文的章节孤立",
                conflicts=plan.conflicts
            )

        # 阶段 4：执行合并 - 原子性事务
        logger.info(f"[SafeMerge] Applying merge plan...")
        await self.story_node_repo.apply_merge_plan(
            creates=plan.creates,
            updates=plan.updates,
            deletes=plan.deletes
        )

        logger.info(f"[SafeMerge] Merge completed successfully: {plan.summary}")
        return {
            "success": True,
            "summary": plan.summary
        }

    # ==================== 幕级规划 ====================

    async def plan_act_chapters(
        self, act_id: str, custom_chapter_count: Optional[int] = None
    ) -> Dict:
        """为指定幕生成章节规划"""
        logger.info(f"Planning chapters for act {act_id}")

        act_node = await self.story_node_repo.get_by_id(act_id)
        if not act_node:
            raise ValueError(f"幕节点不存在: {act_id}")

        bible_context = self._get_bible_context(act_node.novel_id)
        previous_summary = await self._get_previous_acts_summary(act_node)
        chapter_count = custom_chapter_count or act_node.suggested_chapter_count or 5

        # 获取小说的题材和子类型
        genre = ""
        sub_genres: List[str] = []
        if self.novel_repository:
            novel = self.novel_repository.get_by_id(
                NovelId(act_node.novel_id)
            )
            if novel:
                genre = getattr(novel, "genre", "") or ""
                sub_genres = getattr(novel, "sub_genres", []) or []

        prompt = self._build_act_planning_prompt(
            act_node, bible_context, previous_summary, chapter_count,
            genre=genre, sub_genres=sub_genres, novel_id=act_node.novel_id
        )

        try:
            response = await self.llm_service.generate(
                prompt, GenerationConfig(max_tokens=4096, temperature=0.7)
            )
        except Exception as e:
            logger.warning(f"幕级规划 LLM 调用失败 act={act_id}: {e}")
            return {"success": False, "act_id": act_id, "chapters": [], "error": str(e)}

        try:
            plan = self._parse_llm_response(response)
        except Exception as e:
            logger.warning(f"幕级规划 JSON 解析失败 act={act_id}: {e}")
            return {"success": False, "act_id": act_id, "chapters": [], "parse_error": str(e)}

        if not isinstance(plan, dict):
            logger.warning(f"幕级规划解析结果非对象 act={act_id}: {type(plan)}")
            return {"success": False, "act_id": act_id, "chapters": []}

        chapters = plan.get("chapters", [])
        if not isinstance(chapters, list):
            chapters = []

        return {
            "success": True,
            "act_id": act_id,
            "chapters": chapters,
        }

    def _chapter_node_to_dict(self, chapter_node) -> Dict:
        """将章节节点转换为字典格式"""
        return {
            "number": chapter_node.number,
            "title": chapter_node.title,
            "description": chapter_node.description or "",
            "outline": getattr(chapter_node, "outline", "") or ""
        }

    async def _remove_chapter_children_of_act(self, act_id: str) -> None:
        """同一幕再次确认规划时，先删掉本幕下已有章节节点及对应正文行、元素关联，避免重复堆积。"""
        children = self.story_node_repo.get_children_sync(act_id)
        chapter_nodes = [n for n in children if n.node_type == NodeType.CHAPTER]
        for n in chapter_nodes:
            await self.chapter_element_repo.delete_by_chapter(n.id)
            if self.chapter_repository:
                self.chapter_repository.delete(ChapterId(n.id))
            await self.story_node_repo.delete(n.id)

    async def confirm_act_planning(
        self,
        act_id: str,
        chapters: List[Dict],
        mode: PlanningMode = PlanningMode.SKIP_IF_EXISTS
    ) -> Dict:
        """确认幕级规划：写入 story_nodes + chapters 表（供工作台侧栏列表），并关联 Bible 元素。

        Args:
            act_id: 幕ID
            chapters: 章节列表
            mode: 规划模式（SKIP_IF_EXISTS=跳过已有规划, APPEND=追加, OVERWRITE=覆盖）
        """
        logger.info(f"Confirming act planning for act {act_id}, mode={mode.value}")

        act_node = await self.story_node_repo.get_by_id(act_id)
        if not act_node:
            raise ValueError(f"幕节点不存在: {act_id}")

        existing_chapters = self.story_node_repo.get_children_sync(act_id)
        chapter_nodes = [n for n in existing_chapters if n.node_type == NodeType.CHAPTER]

        if mode == PlanningMode.APPEND:
            logger.info(f"幕 {act_id} 追加模式：已有 {len(chapter_nodes)} 章，将追加 {len(chapters)} 章")
        elif chapter_nodes and mode == PlanningMode.SKIP_IF_EXISTS:
            logger.info(f"幕 {act_id} 已有 {len(chapter_nodes)} 个章节规划，跳过覆盖")
            return {
                "success": True,
                "act_id": act_id,
                "chapters": [self._chapter_node_to_dict(n) for n in chapter_nodes],
                "skipped": True,
                "reason": "已有规划，未覆盖"
            }
        elif chapter_nodes and mode == PlanningMode.OVERWRITE:
            await self._remove_chapter_children_of_act(act_id)

        novel_id_vo = NovelId(act_node.novel_id)
        existing_book = []
        if self.chapter_repository:
            existing_book = self.chapter_repository.list_by_novel(novel_id_vo)
        max_num = max((c.number for c in existing_book), default=0)
        next_global_number = max_num + 1

        created_chapters: List[StoryNode] = []
        created_elements: List[ChapterElement] = []

        for idx, raw in enumerate(chapters):
            row = self._normalize_act_chapter_row(raw, act_local_index=idx + 1)
            global_number = next_global_number + idx
            # 与 novel_service.add_chapter / 前端树选择一致：id 以 chapter-{全局章号} 结尾
            story_chapter_id = f"chapter-{act_node.novel_id}-chapter-{global_number}"

            chapter_node = StoryNode(
                id=story_chapter_id,
                novel_id=act_node.novel_id,
                parent_id=act_id,
                node_type=NodeType.CHAPTER,
                number=global_number,
                title=row["title"],
                order_index=act_node.order_index + 1 + idx,
                planning_status=PlanningStatus.CONFIRMED,
                planning_source=PlanningSource.AI_ACT,
                description=row.get("description"),
                outline=row.get("outline"),
                pov_character_id=row.get("pov_character_id"),
                timeline_start=row.get("timeline_start"),
                timeline_end=row.get("timeline_end"),
            )
            created_chapters.append(chapter_node)

            elements_dict = self._merged_elements_dict(row)
            elements = self._create_elements_from_data(story_chapter_id, elements_dict)
            created_elements.extend(elements)

            if self.chapter_repository:
                book_ch = Chapter(
                    id=story_chapter_id,
                    novel_id=novel_id_vo,
                    number=global_number,
                    title=row["title"],
                    content="",
                    status=ChapterStatus.DRAFT,
                )
                self.chapter_repository.save(book_ch)

        await self.story_node_repo.save_batch(created_chapters)
        await self.chapter_element_repo.save_batch(created_elements)

        act_children = self.story_node_repo.get_children_sync(act_id)
        chapter_nodes = [n for n in act_children if n.node_type == NodeType.CHAPTER]
        if chapter_nodes:
            nums = [n.number for n in chapter_nodes]
            act_node.chapter_start = min(nums)
            act_node.chapter_end = max(nums)
        else:
            act_node.chapter_start = None
            act_node.chapter_end = None
        act_node.chapter_count = len(chapter_nodes)
        await self.story_node_repo.update(act_node)

        return {
            "success": True,
            "created_chapters": len(created_chapters),
            "created_elements": len(created_elements),
            "message": f"已写入 {len(created_chapters)} 个章节（本幕旧规划已替换）",
        }

    # ==================== AI 续规划 ====================

    async def continue_planning(self, novel_id: str, current_chapter_number: int) -> Dict:
        """AI 续规划"""
        logger.info(f"Continue planning for novel {novel_id}, chapter {current_chapter_number}")

        current_act = await self._find_act_for_chapter(novel_id, current_chapter_number)
        if not current_act:
            return {"success": False, "message": "未找到当前章节所属的幕"}

        chapters_written = await self._count_written_chapters_in_act(current_act.id)
        chapters_planned = await self._count_planned_chapters_in_act(current_act.id)

        should_end = chapters_written >= chapters_planned

        if should_end:
            next_act = await self._get_next_act(current_act)

            if next_act:
                return {
                    "success": True,
                    "act_completed": True,
                    "has_next_act": True,
                    "current_act": current_act.to_dict(),
                    "next_act": next_act.to_dict(),
                    "message": f"第 {current_act.number} 幕已完成，可以开始第 {next_act.number} 幕"
                }
            else:
                return {
                    "success": True,
                    "act_completed": True,
                    "has_next_act": False,
                    "current_act": current_act.to_dict(),
                    "suggest_create_next": True,
                    "message": f"第 {current_act.number} 幕已完成，是否需要 AI 生成下一幕？"
                }
        else:
            return {
                "success": True,
                "act_completed": False,
                "current_act": current_act.to_dict(),
                "progress": f"{chapters_written}/{chapters_planned}",
                "message": f"继续第 {current_act.number} 幕"
            }

    async def create_next_act_auto(self, novel_id: str, current_act_id: str) -> Dict:
        """自动创建下一幕"""
        logger.info(f"Creating next act after {current_act_id}")

        current_act = await self.story_node_repo.get_by_id(current_act_id)
        if not current_act:
            raise ValueError(f"当前幕不存在: {current_act_id}")

        bible_context = self._get_bible_context(novel_id)
        next_act_info = await self._generate_next_act_info(novel_id, current_act, bible_context)

        next_act = self._create_node_from_data(
            novel_id,
            current_act.parent_id,
            NodeType.ACT,
            {
                "number": current_act.number + 1,
                "title": next_act_info["title"],
                "description": next_act_info["description"],
                "suggested_chapter_count": next_act_info.get("suggested_chapter_count", 5),
                "key_events": next_act_info.get("key_events", []),
                "narrative_arc": next_act_info.get("narrative_arc"),
                "conflicts": next_act_info.get("conflicts", []),
            },
            current_act.order_index + 1
        )

        await self.story_node_repo.save(next_act)

        return {
            "success": True,
            "next_act": next_act.to_dict(),
            "message": f"已创建第 {next_act.number} 幕，请为其规划章节"
        }

    # ==================== 辅助方法 ====================

    def _get_bible_context(self, novel_id: str) -> Dict:
        """获取 Bible 上下文"""
        if not self.bible_service:
            return {}

        bible = self.bible_service.get_bible_by_novel(novel_id)
        if not bible:
            return {}

        return {
            "characters": [{"id": c.id, "name": c.name, "description": c.description}
                           for c in bible.characters],
            "world_settings": [{"id": w.id, "name": w.name, "description": w.description}
                               for w in bible.world_settings],
            "locations": [{"id": l.id, "name": l.name, "description": l.description}
                          for l in bible.locations],
            "timeline_notes": [{"id": t.id, "event": t.event, "description": t.description}
                               for t in bible.timeline_notes],
        }

    def _create_node_from_data(
        self, novel_id: str, parent_id: Optional[str], node_type: NodeType,
        data: Dict, order_index: int
    ) -> StoryNode:
        """从数据创建节点"""
        suggested_count = data.get("suggested_chapter_count")
        if node_type == NodeType.ACT:
            logger.info(f"[{novel_id}] 创建幕节点: {data.get('title')}, suggested_chapter_count={suggested_count}")

        return StoryNode(
            id=f"{node_type.value}-{uuid.uuid4().hex[:8]}",
            novel_id=novel_id,
            parent_id=parent_id,
            node_type=node_type,
            number=data["number"],
            title=data["title"],
            description=data.get("description"),
            order_index=order_index,
            planning_status=PlanningStatus.CONFIRMED,
            planning_source=PlanningSource.AI_MACRO,
            suggested_chapter_count=suggested_count,
            themes=data.get("themes", []),
            key_events=data.get("key_events", []) if node_type == NodeType.ACT else [],
            narrative_arc=data.get("narrative_arc") if node_type == NodeType.ACT else None,
            conflicts=data.get("conflicts", []) if node_type == NodeType.ACT else [],
        )

    def _flatten_structure_to_nodes(self, novel_id: str, structure: List[Dict]) -> List[Dict]:
        """将嵌套的部-卷-幕结构扁平化为节点列表（用于 MacroMergeEngine）

        Args:
            novel_id: 小说 ID
            structure: 嵌套结构 [{"title": "第一部", "volumes": [...]}]

        Returns:
            平面节点列表 [{"id": "part-xxx", "node_type": "PART", ...}]
        """
        nodes = []
        order_index = 0
        part_number = 0
        volume_number = 0
        act_number = 0

        for part_data in structure:
            part_number += 1
            part_data["number"] = part_number
            part_id = f"part-{novel_id}-{part_number}"

            nodes.append({
                "id": part_id,
                "novel_id": novel_id,
                "parent_id": None,
                "node_type": "part",
                "number": part_number,
                "title": part_data["title"],
                "description": part_data.get("description", ""),
                "order_index": order_index,
            })
            order_index += 1

            for volume_data in part_data.get("volumes", []):
                volume_number += 1
                volume_data["number"] = volume_number
                volume_id = f"volume-{novel_id}-{volume_number}"

                nodes.append({
                    "id": volume_id,
                    "novel_id": novel_id,
                    "parent_id": part_id,
                    "node_type": "volume",
                    "number": volume_number,
                    "title": volume_data["title"],
                    "description": volume_data.get("description", ""),
                    "order_index": order_index,
                })
                order_index += 1

                for act_data in volume_data.get("acts", []):
                    act_number += 1
                    act_data["number"] = act_number
                    act_id = f"act-{novel_id}-{act_number}"

                    act_node = {
                        "id": act_id,
                        "novel_id": novel_id,
                        "parent_id": volume_id,
                        "node_type": "act",
                        "number": act_number,
                        "title": act_data["title"],
                        "description": act_data.get("description", ""),
                        "order_index": order_index,
                    }

                    # 保留前端传递的 suggested_chapter_count
                    if "suggested_chapter_count" in act_data:
                        act_node["suggested_chapter_count"] = act_data["suggested_chapter_count"]
                        logger.info(f"[{novel_id}] 幕 {act_number} ({act_data['title']}) suggested_chapter_count={act_data['suggested_chapter_count']}")

                    nodes.append(act_node)
                    order_index += 1

        return nodes

    def _normalize_act_chapter_row(self, raw: Dict, act_local_index: int) -> Dict:
        """LLM / 前端可能缺 number、title，或 number 为字符串；统一为可落库结构。"""
        title = (raw.get("title") or "").strip() or f"第{act_local_index}章"
        num = raw.get("number")
        try:
            num_int = int(num) if num is not None else act_local_index
        except (TypeError, ValueError):
            num_int = act_local_index
        description = raw.get("description")
        if isinstance(description, str):
            description = description.strip() or None
        else:
            description = None
        outline = raw.get("outline") or raw.get("description") or ""
        if isinstance(outline, str):
            outline = outline.strip() or None
        else:
            outline = None
        timeline_start = raw.get("timeline_start")
        if isinstance(timeline_start, str):
            timeline_start = timeline_start.strip() or None
        else:
            timeline_start = None
        timeline_end = raw.get("timeline_end")
        if isinstance(timeline_end, str):
            timeline_end = timeline_end.strip() or None
        else:
            timeline_end = None
        return {
            **raw,
            "number": num_int,
            "title": title,
            "description": description,
            "outline": outline,
            "timeline_start": timeline_start,
            "timeline_end": timeline_end,
        }

    def _merged_elements_dict(self, chapter_row: Dict) -> Dict:
        """提示词里人物/地点在 chapters[].characters；落库时期望 elements.characters 为带 id 的对象列表。"""
        merged: Dict = {}
        inner = chapter_row.get("elements")
        if isinstance(inner, dict):
            merged.update(inner)
        for key in ("characters", "locations"):
            top = chapter_row.get(key)
            if top and not merged.get(key):
                merged[key] = top
        return merged

    def _create_elements_from_data(self, chapter_id: str, elements_data: Dict) -> List[ChapterElement]:
        """从数据创建章节元素"""
        elements = []
        if not isinstance(elements_data, dict):
            return elements

        for char_data in elements_data.get("characters", []):
            if isinstance(char_data, str):
                char_data = {"id": char_data}
            if not isinstance(char_data, dict) or not char_data.get("id"):
                continue
            elements.append(ChapterElement(
                id=f"elem-{uuid.uuid4().hex[:8]}",
                chapter_id=chapter_id,
                element_type=ElementType.CHARACTER,
                element_id=str(char_data["id"]),
                relation_type=RelationType(char_data.get("relation", "appears")),
                importance=Importance(char_data.get("importance", "normal")),
            ))

        for loc_data in elements_data.get("locations", []):
            if isinstance(loc_data, str):
                loc_data = {"id": loc_data}
            if not isinstance(loc_data, dict) or not loc_data.get("id"):
                continue
            elements.append(ChapterElement(
                id=f"elem-{uuid.uuid4().hex[:8]}",
                chapter_id=chapter_id,
                element_type=ElementType.LOCATION,
                element_id=str(loc_data["id"]),
                relation_type=RelationType.SCENE,
                importance=Importance.NORMAL,
            ))

        return elements

    def _parse_llm_response(self, response) -> Dict:
        """解析 LLM 响应"""
        # 如果是 GenerationResult 对象，提取 content 属性
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = response

        cleaned = _sanitize_llm_json_output(content)
        cleaned = _extract_outer_json_value(cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        try:
            repaired = repair_json(cleaned)
            return json.loads(repaired)
        except Exception:
            pass

        cleaned = _repair_json_string(cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse planning JSON: %s", e)
            logger.error("Planning content length: %d", len(cleaned))
            logger.error("Planning raw content (first 1000 chars): %s", cleaned[:1000])
            logger.error("Planning raw content (last 500 chars): %s", cleaned[-500:])
            raise

    def _get_distribution_for_genre(self, genre: str) -> str:
        """Route genre string to distribution type."""
        genre_lower = genre.lower()
        if "xuanhuan" in genre_lower or "玄幻" in genre_lower:
            return "xuanhuan"
        elif "history" in genre_lower or "历史" in genre_lower:
            return "historical"
        else:
            return "default"

    def _get_genre_part_label(self, genre: str, part_index: int, total_parts: int) -> str:
        """Return genre-specific part label for pacing_guide.

        玄幻: 起源卷/觉醒卷/筑基卷 → 崛起卷/风云卷/乱世卷 → 巅峰卷/飞升卷/终章卷
        历史: 崛起篇/奠基篇/初锋篇 → 争锋篇/博弈篇/权倾篇/烽火篇 → 终焉篇/大一统篇/新朝篇
        default: 起源/发展/深渊/决战 (generic)
        """
        genre_type = self._get_distribution_for_genre(genre)
        is_first = part_index == 1
        is_last = part_index == total_parts
        middle_count = total_parts - 2

        if genre_type == "xuanhuan":
            if is_first:
                labels = ["起源卷", "觉醒卷", "筑基卷"]
                return labels[min(part_index - 1, len(labels) - 1)]
            elif is_last:
                labels = ["巅峰卷", "飞升卷", "终章卷"]
                return labels[min(part_index - 1, len(labels) - 1)]
            else:
                idx = (part_index - 2) % 3
                labels = ["崛起卷", "风云卷", "乱世卷"]
                return labels[idx]
        elif genre_type == "historical":
            if is_first:
                labels = ["崛起篇", "奠基篇", "初锋篇"]
                return labels[min(part_index - 1, len(labels) - 1)]
            elif is_last:
                labels = ["终焉篇", "大一统篇", "新朝篇"]
                return labels[min(part_index - 1, len(labels) - 1)]
            else:
                idx = (part_index - 2) % 4
                labels = ["争锋篇", "博弈篇", "权倾篇", "烽火篇"]
                return labels[idx]
        else:
            # Default generic labels
            if is_first:
                return "起源"
            elif is_last:
                return "决战"
            else:
                return "发展/深渊"

    def _xuanhuan_distribution(self, total_chapters: int, parts: int) -> Dict[str, List[int]]:
        """倒V形比例（境界递进）：境界越高体量越大

        - 5部: 10% - 20% - 25% - 20% - 15%
        - 4部: 12% - 24% - 28% - 24% - 12%
        - 3部: 15% - 35% - 30% - 20%
        """
        if parts == 1:
            return {"part_chapters": [total_chapters], "part_ratios": [1.0]}
        if parts == 2:
            p1 = int(total_chapters * 0.35)
            p2 = total_chapters - p1
            return {"part_chapters": [p1, p2], "part_ratios": [0.35, 0.65]}
        if parts == 3:
            p1 = int(total_chapters * 0.15)
            p3 = int(total_chapters * 0.20)
            p2 = total_chapters - p1 - p3
            return {"part_chapters": [p1, p2, p3], "part_ratios": [0.15, 0.65, 0.20]}
        if parts == 4:
            p1 = int(total_chapters * 0.12)
            p4 = int(total_chapters * 0.12)
            remaining = total_chapters - p1 - p4
            p2 = int(remaining * 0.46)
            p3 = remaining - p2
            return {"part_chapters": [p1, p2, p3, p4], "part_ratios": [0.12, 0.46, 0.30, 0.12]}
        # 5部+: 10/20/25/20/15
        ratios = [0.10, 0.20, 0.25, 0.20, 0.15]
        part_chapters = []
        part_ratios = []
        for i in range(parts):
            if i < len(ratios):
                r = ratios[i]
            else:
                r = 0.10 if i == 0 or i == parts - 1 else 0.20
            ch = int(total_chapters * r)
            part_chapters.append(ch)
            part_ratios.append(r)
        # last part absorbs remainder
        part_chapters[-1] = total_chapters - sum(part_chapters[:-1])
        part_ratios[-1] = part_chapters[-1] / total_chapters
        return {"part_chapters": part_chapters, "part_ratios": part_ratios}

    def _historical_distribution(self, total_chapters: int, parts: int) -> Dict[str, List[int]]:
        """幂函数比例（政治周期）：中间部承担最多叙事重量

        - 3部: 25% - 50% - 25%
        - 4部: 20% - 30% - 30% - 20%
        - 5部: 20% - 20% - 25% - 20% - 15% (中后部最重)
        - 6部+: 递减，首尾各10%，中间各~16%
        """
        if parts == 1:
            return {"part_chapters": [total_chapters], "part_ratios": [1.0]}
        if parts == 2:
            p1 = int(total_chapters * 0.35)
            p2 = total_chapters - p1
            return {"part_chapters": [p1, p2], "part_ratios": [0.35, 0.65]}
        if parts == 3:
            p1 = int(total_chapters * 0.25)
            p3 = int(total_chapters * 0.25)
            p2 = total_chapters - p1 - p3
            return {"part_chapters": [p1, p2, p3], "part_ratios": [0.25, 0.50, 0.25]}
        if parts == 4:
            p1 = int(total_chapters * 0.20)
            p4 = int(total_chapters * 0.20)
            remaining = total_chapters - p1 - p4
            p2 = remaining // 2
            p3 = remaining - p2
            return {"part_chapters": [p1, p2, p3, p4], "part_ratios": [0.20, 0.30, 0.30, 0.20]}
        # 5部+: 首尾各20%，中间平分60%
        first = int(total_chapters * 0.20)
        last = int(total_chapters * 0.20)
        middle_total = total_chapters - first - last
        middle_parts = parts - 2
        middle_each = middle_total // middle_parts
        part_chapters = [first]
        for i in range(middle_parts):
            if i == middle_parts - 1:
                part_chapters.append(middle_total - middle_each * (middle_parts - 1))
            else:
                part_chapters.append(middle_each)
        part_chapters.append(last)
        part_ratios = [c / total_chapters for c in part_chapters]
        return {"part_chapters": part_chapters, "part_ratios": part_ratios}

    def _calculate_chapter_distribution(self, total_chapters: int, parts: int, genre: str = "") -> Dict[str, List[int]]:
        """计算章数分配，支持题材特定比例

        Args:
            total_chapters: 总章节数
            parts: 部数
            genre: 题材类型（xuanhuan/history/空或default）

        Returns:
            {
                "part_chapters": [250, 500, 250],  # 每部的章数
                "part_ratios": [0.25, 0.5, 0.25]   # 每部的占比
            }
        """
        genre_type = self._get_distribution_for_genre(genre)
        if genre_type == "xuanhuan":
            return self._xuanhuan_distribution(total_chapters, parts)
        elif genre_type == "historical":
            return self._historical_distribution(total_chapters, parts)
        # Default: 黄金分割
        if parts == 1:
            return {"part_chapters": [total_chapters], "part_ratios": [1.0]}
        if parts == 2:
            p1 = int(total_chapters * 0.4)
            p2 = total_chapters - p1
            return {"part_chapters": [p1, p2], "part_ratios": [0.4, 0.6]}
        if parts == 3:
            p1 = int(total_chapters * 0.25)
            p3 = int(total_chapters * 0.25)
            p2 = total_chapters - p1 - p3
            return {"part_chapters": [p1, p2, p3], "part_ratios": [0.25, 0.5, 0.25]}
        if parts == 4:
            p1 = int(total_chapters * 0.2)
            p4 = int(total_chapters * 0.2)
            remaining = total_chapters - p1 - p4
            p2 = remaining // 2
            p3 = remaining - p2
            return {"part_chapters": [p1, p2, p3, p4], "part_ratios": [0.2, 0.3, 0.3, 0.2]}
        first = int(total_chapters * 0.2)
        last = int(total_chapters * 0.2)
        middle_total = total_chapters - first - last
        middle_parts = parts - 2
        middle_each = middle_total // middle_parts
        part_chapters = [first]
        for i in range(middle_parts):
            if i == middle_parts - 1:
                part_chapters.append(middle_total - middle_each * (middle_parts - 1))
            else:
                part_chapters.append(middle_each)
        part_chapters.append(last)
        part_ratios = [c / total_chapters for c in part_chapters]
        return {"part_chapters": part_chapters, "part_ratios": part_ratios}

    def _build_quick_macro_prompt(self, bible_context: Dict, target_chapters: int, genre: str = "") -> Prompt:
        """极速模式：破城槌提示词 V3（渐进式规划版）

        设计哲学：
        - 超长篇（>500章）：只规划部/卷框架，幕节点动态生成
        - 中长篇（<500章）：可以规划完整的部/卷/幕结构
        - 避免单次 LLM 输出过多内容导致截断
        """

        # 根据章节数决定规划深度
        if target_chapters > 500:
            planning_depth = "framework"  # 只规划部/卷框架
            depth_instruction = f"""
【规划深度】目标章节数>500，采用渐进式规划：
- 只输出「部」和「卷」的标题与主题（不输出具体幕）
- 【强制要求】每卷必须输出 estimated_chapters（预估章数）
- 【章数约束】所有卷的 estimated_chapters 之和必须等于 {target_chapters} 章
- 每卷建议 50-200 章，根据剧情需要灵活分配
- 幕节点将在写作过程中动态生成
"""
        elif target_chapters > 100:
            planning_depth = "partial"  # 规划前几部的幕
            depth_instruction = f"""
【规划深度】目标章节数>100，采用部分详细规划：
- 规划「部」和「卷」的完整结构
- 【强制要求】每卷必须输出 estimated_chapters（预估章数）
- 【章数约束】所有卷的 estimated_chapters 之和必须等于 {target_chapters} 章
- 只为第1-2部的卷规划幕节点（约50-100幕）
- 后续部的幕节点将在写作中动态生成
"""
        else:
            planning_depth = "full"  # 完整规划
            depth_instruction = f"""
【规划深度】目标章节数<100，完整规划所有部/卷/幕
- 【强制要求】每幕必须输出 estimated_chapters（预估章数）
- 【章数约束】所有幕的 estimated_chapters 之和必须等于 {target_chapters} 章
"""

        # 题材感知的商业节奏提示
        genre_type = self._get_distribution_for_genre(genre)
        if genre_type == "xuanhuan":
            genre_pacing = """
【题材节奏·玄幻】境界递进是核心驱动力：
- 第1部（起源/觉醒）：主角刚踏入修行路，以小副本+退婚/打脸节奏建立爽感基础，章数偏少（10-15%）
- 中间部（崛起/风云）：境界稳步提升，副本规模扩大，多方势力角逐，中段章节数最多（倒V形），每20-30章一个小高潮
- 最后部（巅峰/飞升）：终极对决+飞升大战，节奏要快、爽感要密集、情绪爆发要强
"""
        elif genre_type == "historical":
            genre_pacing = """
【题材节奏·历史】政治博弈是核心驱动力：
- 第1部（崛起/奠基）：主角政治资本积累，核心团队成形，权谋手段初现，章数偏少（20-25%）
- 中间部（争锋/博弈）：政治博弈白热化，联盟背叛频发，大高潮集中在此段（40-50%总篇幅），多线叙事要铺开
- 最后部（终焉/大一统）：新朝建立或终极权争终局，所有伏笔收束，终局要有史诗感
"""
        else:
            genre_pacing = """
【题材节奏·通用】经典叙事节奏：
- 第1部：快速建立核心冲突和主角目标
- 中间部：多线叙事推进，主角经历重大转变
- 最后部：所有伏笔收束，终极对决，情绪爆发
"""

        system_msg = f"""# 角色设定
你是一位狂热且极具市场敏锐度的顶级网文主编，精通"退婚流"、"克苏鲁修仙"、"赛博朋克反乌托邦"等各种爆款商业节奏。你的任务是帮作者打破"白纸恐惧"，利用他给出的世界观设定，瞬间推演填补出一个完整、宏大、且充满极端冲突的长篇叙事骨架。

{depth_instruction}

# 叙事结构理论指导
<STORY_THEORY>
你设计的结构应符合以下经典叙事原理：
1. 三幕剧结构：Setup（设定）→ Confrontation（对抗）→ Resolution（解决）
2. 英雄之旅：平凡世界→冒险召唤→试炼→深渊→蜕变→归来
3. 情绪曲线：开篇抓人→中段起伏（小高潮间隔3-5幕）→终局爆发
4. 钩子密度：每部结尾必须有大悬念，每卷结尾有中等悬念，每幕结尾有小悬念
</STORY_THEORY>

{genre_pacing}

# 核心推演铁律（The Icebreaker Rules V3）

# 叙事结构理论指导
<STORY_THEORY>
你设计的结构应符合以下经典叙事原理：
1. 三幕剧结构：Setup（设定）→ Confrontation（对抗）→ Resolution（解决）
2. 英雄之旅：平凡世界→冒险召唤→试炼→深渊→蜕变→归来
3. 情绪曲线：开篇抓人→中段起伏（小高潮间隔3-5幕）→终局爆发
4. 钩子密度：每部结尾必须有大悬念，每卷结尾有中等悬念，每幕结尾有小悬念
</STORY_THEORY>

# 核心推演铁律（The Icebreaker Rules V3）
<CONSTRAINTS>
1. 【结构自主】根据目标篇幅智能决定部/卷数量：
   - 短篇（<50章）：1-2部，每部2-3卷
   - 中篇（50-200章）：2-3部，每部2-4卷
   - 长篇（200-500章）：3-5部，每部3-5卷
   - 超长篇（500-2000章）：4-6部，每部4-6卷
   - 史诗（>2000章）：5-8部，每部4-8卷

2. 【极致冲突】每一幕（如果有）必须包含：
   - 核心对抗（谁 vs 谁）
   - 赌注（失败会失去什么）
   - 转折（预期违背）

3. 【世界观融合】必须深度融合提供的设定：
   - 主要角色必须出现在关键幕中
   - 关键地点必须承担叙事功能
   - 时间线事件必须影响情节走向

4. 【商业节奏】
   - 第一部：快速抛出核心悬念，建立主角目标
   - 中间部：主角经历重大失败/觉醒
   - 最后一部：所有伏笔收束，终极对决
</CONSTRAINTS>

# 输出格式
请直接输出JSON：
{{"parts": [{{"title": "部标题", "theme": "部主题", "volumes": [...]}}]}}

每卷格式（estimated_chapters 为必填字段）：
{{"title": "卷标题", "theme": "卷主题", "estimated_chapters": 预估章数（必填整数）}}

{"如果规划深度为 full 或 partial，每卷还应包含 acts 数组，每幕也必须有 estimated_chapters：" if planning_depth != "framework" else "超长篇不输出 acts，但必须确保每卷的 estimated_chapters 之和等于目标章数。"}
{"每幕格式：" if planning_depth == "full" else ""}
{{"acts": [{{"title": "幕标题", "estimated_chapters": 预估章数（必填整数）, "description": "情节摘要"}}]}}

【章数校验】请确保：所有卷/幕的 estimated_chapters 之和 = {target_chapters}

不要添加任何解释性文字。"""

        # 构建丰富的世界观上下文
        context_parts = []

        # 世界观
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")

        # 角色（带关系和弧光）
        if bible_context.get("characters"):
            chars = bible_context['characters']
            char_lines = ["【角色设定】"]
            for c in chars[:5]:  # 限制主要角色数量
                name = c.get('name', 'Unknown')
                desc = c.get('description', '')
                role = c.get('role', '')
                arc = c.get('character_arc', '')
                char_lines.append(f"- {name} ({role}): {desc}")
                if arc:
                    char_lines.append(f"  人物弧光: {arc}")
            context_parts.append("\n".join(char_lines) + "\n")

        # 角色关系
        if bible_context.get("relationships"):
            rel_lines = ["【角色关系】"]
            for r in bible_context['relationships'][:5]:
                char1 = r.get('character1', '')
                char2 = r.get('character2', '')
                rel_type = r.get('relationship_type', '')
                rel_desc = r.get('description', '')
                rel_lines.append(f"- {char1} ↔ {char2} ({rel_type}): {rel_desc}")
            context_parts.append("\n".join(rel_lines) + "\n")

        # 地点（带叙事功能）
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context['locations'][:5]:
                name = l.get('name', 'Unknown')
                desc = l.get('description', '')
                significance = l.get('significance', '')
                loc_lines.append(f"- {name}: {desc}")
                if significance:
                    loc_lines.append(f"  叙事意义: {significance}")
            context_parts.append("\n".join(loc_lines) + "\n")

        # 时间线事件
        if bible_context.get("timeline_notes"):
            time_lines = ["【时间线事件】"]
            for t in bible_context['timeline_notes'][:5]:
                event = t.get('event', '')
                desc = t.get('description', '')
                impact = t.get('impact', '')
                time_lines.append(f"- {event}: {desc}")
                if impact:
                    time_lines.append(f"  情节影响: {impact}")
            context_parts.append("\n".join(time_lines) + "\n")

        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请基于通用的商业小说套路生成结构，但仍需保持结构灵活和冲突极致。\n")

        worldview_context = "\n".join(context_parts)

        user_msg = f"""<STORY_CONTEXT>
{worldview_context}
</STORY_CONTEXT>

<TARGET_SCOPE>
目标总篇幅：精确 {target_chapters} 章
【强制约束】所有卷/幕的 estimated_chapters 之和必须等于 {target_chapters}
</TARGET_SCOPE>

请立即生成叙事骨架，严格按以下JSON格式输出：
{{
  "parts": [
    {{
      "title": "部标题（如：深渊觉醒）",
      "volumes": [
        {{
          "title": "卷标题（如：血色的黎明）",
          "acts": [
            {{
              "title": "幕标题（如：青铜门下的背叛）",
              "core_conflict": "主角 vs 反派，赌注是...",
              "emotional_turn": "从...到...",
              "description": "情节摘要...",
              "key_characters": ["角色1", "角色2"],
              "key_locations": ["地点1"]
            }}
          ]
        }}
      ]
    }}
  ]
}}"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_precise_macro_prompt(
        self,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict,
        skeleton: Dict,
        genre: str = "",
    ) -> Prompt:
        """精密模式：手术刀提示词 V2

        设计哲学：
        - 捍卫创作者的绝对主权与节奏感
        - 严格遵守用户指定的结构网格和字数节奏
        - 强调逻辑严密、中段支撑、情节容量匹配
        - 深度融合 Bible 设定进行精密推演
        - 引入叙事理论确保结构合理性
        """
        parts = structure_preference.get('parts', 3)
        volumes_per_part = structure_preference.get('volumes_per_part', 3)
        acts_per_volume = structure_preference.get('acts_per_volume', 3)
        total_acts = parts * volumes_per_part * acts_per_volume

        # 计算章数分配（题材感知）
        distribution = self._calculate_chapter_distribution(target_chapters, parts, genre)
        part_chapters = distribution["part_chapters"]

        # 计算每幕平均章数
        avg_chapters_per_act = target_chapters // total_acts if total_acts > 0 else 5

        # 构建题材感知的动态章节配额指示
        genre_type = self._get_distribution_for_genre(genre)
        pacing_guide = "<PACING_GUIDE>\n"
        for i, chapters in enumerate(part_chapters, 1):
            label = self._get_genre_part_label(genre, i, parts)
            if genre_type == "xuanhuan":
                if i == 1:
                    focus = "主角初入修行路、第一个小境界突破、核心势力初现。注意控制节奏，在50-80章内完成第一个大副本。"
                elif i == parts:
                    focus = "终极境界对决、飞升大战、所有伏笔收束。情绪爆发要强，结尾要爽。"
                else:
                    focus = "主角境界稳步提升，多方势力角逐。中段需有1-2个大型副本（每个50-80章），小高潮每20-30章一次。"
            elif genre_type == "historical":
                if i == 1:
                    focus = "主角崛起初期、政治资本积累、核心团队成形。前期不要铺太大，控制在合理规模。"
                elif i == parts:
                    focus = "大一统终局、新朝建立、所有政治线收束。终局要宏大，体现政权更迭的史诗感。"
                else:
                    focus = "政治博弈白热化、联盟与背叛、势力重新洗牌。政争/战争的大高潮应集中在此段。"
            else:
                if i == 1:
                    focus = "紧凑、抛出核心悬念、建立主角目标。"
                elif i == parts:
                    focus = "收束所有主线、终极对决、情绪爆发。"
                else:
                    focus = "容量极大、多线叙事、主角重大转变。"
            pacing_guide += f"- 第{i}部（{label}）：分配 {chapters} 章。情节要求：{focus}\n"
        pacing_guide += f"</PACING_GUIDE>\n\n<ACT_PACING>\n"
        pacing_guide += f"- 总幕数：{total_acts} 幕\n"
        pacing_guide += f"- 平均每幕：约 {avg_chapters_per_act} 章\n"
        pacing_guide += f"- 节奏建议：前1/3幕数铺垫，中1/3幕数发展+小高潮，后1/3幕数爆发+收束\n"
        pacing_guide += "</ACT_PACING>"

        system_msg = f"""# 角色设定
你是一位极其理性的长篇小说结构架构师，精通经典叙事理论和现代网文节奏。作者正在进行一项严密的叙事工程，设定了精确的篇幅限制和结构分布。你的任务是像外科手术一样，在严格遵守"结构网格"和"字数节奏"的前提下，深度融合世界观设定，分配情节张力，确保中段不塌陷，高潮不疲软。

# 叙事理论框架
<STORY_THEORY>
1. 三幕剧结构映射：
   - 第1部 ≈ 第一幕（设定）：主角现状→触发事件→拒绝改变→跨越门槛
   - 中间部 ≈ 第二幕（对抗）：试炼与盟友→深入深渊→核心考验
   - 最后部 ≈ 第三幕（解决）：回归→终极对决→新世界

2. 情绪曲线设计：
   - 每部内部：起→承→转→合
   - 幕间关系：悬念→揭示→更大悬念
   - 高潮分布：每部1个大高潮，每卷1个中高潮，每2-3幕1个小高潮

3. 角色弧光整合：
   - 主角必须在结构节点处经历关键转变
   - 反派势力应随幕推进逐步显露/强化
   - 配角应在特定幕完成其叙事功能
</STORY_THEORY>

# 精密推演铁律（The Scalpel Rules V2）
<CONSTRAINTS>
1. 【结构网格绝对服从】
   必须严格输出 {parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷 = {total_acts} 幕，不得多一个或少一个节点。

2. 【节奏匹配】
   系统已为你计算好每部的【预估章数配额】。你设计的情节容量必须能撑起这个章数：
   - 高章数配额（>100章/部）：必须设计【多线叙事】+【复杂长线副本】+【势力博弈】
   - 中章数配额（50-100章/部）：设计【主线+1-2条副线】+【阶段性目标】
   - 低章数配额（<50章/部）：情节必须是【单线程快速推进】+【紧凑冲突】

3. 【世界观深度融合】
   - 主要角色必须出现在具体幕中，标注其在该幕的角色功能（主角/反派/盟友/阻碍者）
   - 关键地点必须承担具体叙事功能（不仅是背景，而是冲突发生地/转折点）
   - 时间线事件必须与幕结构对齐（某幕必须解决某事件，或某事件触发某幕）
   - 角色关系必须在幕中体现（某幕聚焦某对关系的转变）

4. 【逻辑严密性】
   - 严禁机械降神：所有解决必须基于已铺垫的能力/资源
   - 因果清晰：每一幕的结果必须是下一幕的前提
   - 伏笔呼应：早期幕埋下的线索必须在后期幕回收

5. 【中段支撑】
   - 中间部分必须设计"次要反派的崛起"或"主角信念的暂时崩溃"
   - 每3-4幕必须有一个情绪转折点（希望→绝望，或反之）
   - 避免"中段塌陷"：确保中间幕的冲突强度不低于首尾

6. 【章数分配】
   - 每幕必须标注 estimated_chapters（参考平均每幕{avg_chapters_per_act}章）
   - 重要幕（转折点、高潮）可分配更多章数
   - 过渡幕可分配较少章数，但必须有冲突推进
</CONSTRAINTS>

{pacing_guide}

# 输出要求
请直接输出JSON格式，层级必须严格吻合结构网格。
每幕（Act）的输出字段必须包含：
- "title": "精准的情节标题（动词+名词，暗示冲突）"
- "estimated_chapters": 本幕预计占用的章数（整数）
- "narrative_goal": "本幕在整个故事结构中承担的叙事功能"
- "plot_points": ["情节点1", "情节点2", "情节点3"]（本幕包含的关键事件）
- "description": "严谨的剧情走向摘要（含因果逻辑）"
- "key_characters": ["角色ID"]（本幕涉及的角色，标注功能如：主角-李明）
- "key_locations": ["地点ID"]（本幕发生的关键地点，标注功能）
- "emotional_arc": "情绪曲线（如：平静→紧张→爆发）"
- "setup_for": ["后续幕ID或标题"]（本幕为哪些后续幕做铺垫）
- "payoff_from": ["前置幕ID或标题"]（本幕回收了哪些前置幕的伏笔）

不要添加任何解释性文字。"""

        # 构建丰富的世界观上下文（与极速模式一致）
        context_parts = []

        # 世界观
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")

        # 角色（带关系和弧光）
        if bible_context.get("characters"):
            chars = bible_context['characters']
            char_lines = ["【角色设定】"]
            for c in chars[:5]:
                name = c.get('name', 'Unknown')
                desc = c.get('description', '')
                role = c.get('role', '')
                arc = c.get('character_arc', '')
                char_id = c.get('id', 'N/A')
                char_lines.append(f"- {name} (ID: {char_id}) [{role}]: {desc}")
                if arc:
                    char_lines.append(f"  人物弧光: {arc}")
            context_parts.append("\n".join(char_lines) + "\n")

        # 角色关系
        if bible_context.get("relationships"):
            rel_lines = ["【角色关系】"]
            for r in bible_context['relationships'][:5]:
                char1 = r.get('character1', '')
                char2 = r.get('character2', '')
                rel_type = r.get('relationship_type', '')
                rel_desc = r.get('description', '')
                rel_lines.append(f"- {char1} ↔ {char2} ({rel_type}): {rel_desc}")
            context_parts.append("\n".join(rel_lines) + "\n")

        # 地点（带叙事功能）
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context['locations'][:5]:
                name = l.get('name', 'Unknown')
                desc = l.get('description', '')
                significance = l.get('significance', '')
                loc_id = l.get('id', 'N/A')
                loc_lines.append(f"- {name} (ID: {loc_id}): {desc}")
                if significance:
                    loc_lines.append(f"  叙事意义: {significance}")
            context_parts.append("\n".join(loc_lines) + "\n")

        # 时间线事件
        if bible_context.get("timeline_notes"):
            time_lines = ["【时间线事件】"]
            for t in bible_context['timeline_notes'][:5]:
                event = t.get('event', '')
                desc = t.get('description', '')
                impact = t.get('impact', '')
                time_lines.append(f"- {event}: {desc}")
                if impact:
                    time_lines.append(f"  情节影响: {impact}")
            context_parts.append("\n".join(time_lines) + "\n")

        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请生成通用的结构框架，但仍需严格遵守结构网格。\n")

        worldview_context = "\n".join(context_parts)

        skeleton_lines = ["【固定结构骨架】"]
        for part_index, part in enumerate(skeleton.get("parts", []), 1):
            skeleton_lines.append(f'- {part["node_id"]}: 第{part_index}部')
            for volume_index, volume in enumerate(part.get("volumes", []), 1):
                skeleton_lines.append(f'  - {volume["node_id"]}: 第{part_index}部第{volume_index}卷')
                for act_index, act in enumerate(volume.get("acts", []), 1):
                    skeleton_lines.append(
                        f'    - {act["node_id"]}: 第{part_index}部第{volume_index}卷第{act_index}幕，参考 {avg_chapters_per_act} 章'
                    )

        skeleton_block = "\n".join(skeleton_lines)

        user_msg = f"""<STORY_CONTEXT>
{worldview_context}
</STORY_CONTEXT>

<STRUCTURAL_GRID>
【你必须绝对服从的物理网格】
- 目标总章数：{target_chapters} 章
- 结构分布：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷 = {total_acts} 幕
- 平均每幕：约 {avg_chapters_per_act} 章
</STRUCTURAL_GRID>

{skeleton_block}

系统已经固定好了部/卷/幕的数量与层级，你不能新增、删除、合并、拆分任何节点。
你的任务只是为这些固定节点填写标题、描述和幕级字段。

请只输出 JSON，格式如下：
{{
  "node_updates": [
    {{
      "node_id": "P1 或 V1_1 或 A1_1_1",
      "title": "节点标题",
      "description": "节点描述",
      "estimated_chapters": 5,
      "narrative_goal": "仅 Act 必填",
      "plot_points": ["仅 Act 使用"],
      "key_characters": ["仅 Act 使用"],
      "key_locations": ["仅 Act 使用"],
      "emotional_arc": "仅 Act 使用",
      "setup_for": ["仅 Act 使用"],
      "payoff_from": ["仅 Act 使用"]
    }}
  ]
}}

要求：
1. 每个固定节点都必须返回一条 node_updates。
2. Part/Volume 只需填写 node_id、title、description。
3. Act 必须填写全部幕级字段。
4. 不要返回 parts/volumes/acts 树，不要添加解释文字。
5. 幕的 estimated_chapters 可以按剧情轻重分配，但总量应尽量接近 {target_chapters} 章。"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_precise_volume_prompt(
        self,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict,
        skeleton: Dict,
        part_index: int,
        volume_index: int,
    ) -> Prompt:
        """按卷生成内容，缩小上下文范围以提高字段完整度。"""
        parts = structure_preference.get('parts', 3)
        volumes_per_part = structure_preference.get('volumes_per_part', 3)
        acts_per_volume = structure_preference.get('acts_per_volume', 3)
        total_acts = parts * volumes_per_part * acts_per_volume
        avg_chapters_per_act = target_chapters // total_acts if total_acts > 0 else 5

        current_part = skeleton["parts"][part_index - 1]
        current_volume = current_part["volumes"][volume_index - 1]
        act_scope = current_volume.get("acts", [])

        context_parts = []
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")
        if bible_context.get("characters"):
            char_lines = ["【角色设定】"]
            for c in bible_context["characters"][:8]:
                char_lines.append(
                    f"- {c.get('name', 'Unknown')} (ID: {c.get('id', 'N/A')}): {c.get('description', '')}"
                )
            context_parts.append("\n".join(char_lines) + "\n")
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context["locations"][:8]:
                loc_lines.append(
                    f"- {l.get('name', 'Unknown')} (ID: {l.get('id', 'N/A')}): {l.get('description', '')}"
                )
            context_parts.append("\n".join(loc_lines) + "\n")
        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请给出通用但完整的单卷叙事设计。\n")

        scope_lines = [
            f"【当前生成范围】第{part_index}部 / 第{volume_index}卷",
            f'- {current_part["node_id"]}: {current_part["title"]}',
            f'- {current_volume["node_id"]}: {current_volume["title"]}',
        ]
        for act in act_scope:
            scope_lines.append(
                f'- {act["node_id"]}: {act["title"]}，需完整填写 narrative_goal / plot_points / key_characters / key_locations / emotional_arc / setup_for / payoff_from'
            )

        system_msg = """你是长篇小说结构设计师。当前任务不是规划整本书，而是只完成一个卷的详细结构设计。
你必须为当前卷内的每一幕填写完整字段，尤其不能遗漏 narrative_goal、plot_points、key_characters、key_locations、emotional_arc。
请直接输出 JSON，不要解释。"""

        user_msg = f"""<STORY_CONTEXT>
{"".join(context_parts)}
</STORY_CONTEXT>

【全书网格】
- 总章数：{target_chapters} 章
- 结构：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷
- 平均每幕：约 {avg_chapters_per_act} 章

{chr(10).join(scope_lines)}

请仅返回当前卷相关节点的 JSON：
{{
  "node_updates": [
    {{
      "node_id": "{current_part["node_id"]} 或 {current_volume["node_id"]} 或 {act_scope[0]["node_id"] if act_scope else 'A1_1_1'}",
      "title": "节点标题",
      "description": "节点描述",
      "estimated_chapters": 5,
      "narrative_goal": "仅 Act 必填，不能为空",
      "plot_points": ["仅 Act 使用，至少 2 条"],
      "key_characters": ["仅 Act 使用，至少 1 条"],
      "key_locations": ["仅 Act 使用，至少 1 条"],
      "emotional_arc": "仅 Act 使用，不能为空",
      "setup_for": ["仅 Act 使用"],
      "payoff_from": ["仅 Act 使用"]
    }}
  ]
}}

要求：
1. 只返回当前卷涉及的 node_updates。
2. 当前卷内每个 Act 都必须返回一条更新。
3. 每个 Act 的 narrative_goal、plot_points、key_characters、key_locations、emotional_arc 都不能为空。
4. 不要新增或删除节点。"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_precise_repair_prompt(
        self,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict,
        incomplete_acts: List[Dict],
        full_skeleton: Dict,
    ) -> Prompt:
        """只为缺字段的幕生成补丁，但提供完整结构和背景信息作为参考。"""
        parts = structure_preference.get('parts', 3)
        volumes_per_part = structure_preference.get('volumes_per_part', 3)
        acts_per_volume = structure_preference.get('acts_per_volume', 3)
        total_acts = max(parts * volumes_per_part * acts_per_volume, 1)
        avg_chapters_per_act = max(target_chapters // total_acts, 1)

        # 【复用第一次生成时的背景信息构建逻辑】
        context_parts = []

        # 世界观
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")

        # 角色（带关系和弧光）
        if bible_context.get("characters"):
            chars = bible_context['characters']
            char_lines = ["【角色设定】"]
            for c in chars[:5]:
                name = c.get('name', 'Unknown')
                desc = c.get('description', '')
                role = c.get('role', '')
                arc = c.get('character_arc', '')
                char_id = c.get('id', 'N/A')
                char_lines.append(f"- {name} (ID: {char_id}) [{role}]: {desc}")
                if arc:
                    char_lines.append(f"  人物弧光: {arc}")
            context_parts.append("\n".join(char_lines) + "\n")

        # 角色关系
        if bible_context.get("relationships"):
            rel_lines = ["【角色关系】"]
            for r in bible_context['relationships'][:5]:
                char1 = r.get('character1', '')
                char2 = r.get('character2', '')
                rel_type = r.get('relationship_type', '')
                rel_desc = r.get('description', '')
                rel_lines.append(f"- {char1} ↔ {char2} ({rel_type}): {rel_desc}")
            context_parts.append("\n".join(rel_lines) + "\n")

        # 地点（带叙事功能）
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context['locations'][:5]:
                name = l.get('name', 'Unknown')
                desc = l.get('description', '')
                significance = l.get('significance', '')
                loc_id = l.get('id', 'N/A')
                loc_lines.append(f"- {name} (ID: {loc_id}): {desc}")
                if significance:
                    loc_lines.append(f"  叙事意义: {significance}")
            context_parts.append("\n".join(loc_lines) + "\n")

        # 时间线事件
        if bible_context.get("timeline_notes"):
            time_lines = ["【时间线事件】"]
            for t in bible_context['timeline_notes'][:5]:
                event = t.get('event', '')
                desc = t.get('description', '')
                impact = t.get('impact', '')
                time_lines.append(f"- {event}: {desc}")
                if impact:
                    time_lines.append(f"  情节影响: {impact}")
            context_parts.append("\n".join(time_lines) + "\n")

        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请补齐通用但完整的叙事字段。\n")

        worldview_context = "\n".join(context_parts)

        # 构建完整的结构树展示
        structure_tree = ["【已生成的完整结构树】"]
        for part in full_skeleton.get("parts", []):
            structure_tree.append(f"\n{part['node_id']}: {part['title']}")
            structure_tree.append(f"  简介: {part.get('description', '暂无')}")
            for volume in part.get("volumes", []):
                structure_tree.append(f"  {volume['node_id']}: {volume['title']}")
                structure_tree.append(f"    简介: {volume.get('description', '暂无')}")
                for act in volume.get("acts", []):
                    structure_tree.append(f"    {act['node_id']}: {act['title']} ({act.get('estimated_chapters', 0)}章)")
                    structure_tree.append(f"      简介: {act.get('description', '暂无')}")
                    if act.get("narrative_goal"):
                        structure_tree.append(f"      叙事目标: {act['narrative_goal']}")
                    if act.get("plot_points"):
                        structure_tree.append(f"      情节点: {', '.join(act['plot_points'])}")
                    if act.get("key_characters"):
                        structure_tree.append(f"      关键角色: {', '.join(act['key_characters'])}")
                    if act.get("key_locations"):
                        structure_tree.append(f"      关键地点: {', '.join(act['key_locations'])}")
                    if act.get("emotional_arc"):
                        structure_tree.append(f"      情感曲线: {act['emotional_arc']}")
                    if act.get("setup_for"):
                        structure_tree.append(f"      铺垫: {', '.join(act['setup_for'])}")
                    if act.get("payoff_from"):
                        structure_tree.append(f"      回收: {', '.join(act['payoff_from'])}")

        # 标记待补全的幕
        incomplete_ids = {act["node_id"] for act in incomplete_acts}
        incomplete_summary = ["\n【需要补全的幕】"]
        for act in incomplete_acts:
            incomplete_summary.append(
                f"- {act['node_id']}: 缺失字段 [{', '.join(act['missing_fields'])}]"
            )

        system_msg = """你是小说结构补全助手。你会收到：
1. 完整的世界观、角色（含弧光）、角色关系、地点（含叙事意义）、时间线事件等背景信息
2. 已经生成好的完整结构树（部-卷-幕三层结构，包含所有已填写的字段）
3. 需要补全的幕列表（标注了缺失哪些字段）

# 核心原则
1. **参考完整结构树**：理解每个幕在整体叙事中的位置、前后关系、铺垫回收链
2. **基于背景信息**：严格使用提供的世界观、角色、地点、时间线事件，不要凭空创造
3. **只填缺失字段**：已有的 title、description、estimated_chapters 等字段绝对不可改动
4. **保持一致性**：补全内容需与该幕的标题、简介、所属卷部、前后幕的内容逻辑一致
5. **输出纯 JSON**：不添加任何解释文字

# 字段补全要求
- narrative_goal: 该幕的叙事目标，需与标题、简介、结构定位一致
- plot_points: 至少2个具体情节点，需考虑前后幕的情节连贯性和时间线事件
- key_characters: 至少1个角色（优先使用背景信息中的角色ID，考虑角色弧光和关系）
- key_locations: 至少1个地点（优先使用背景信息中的地点ID，考虑叙事意义）
- emotional_arc: 情感曲线，需考虑同卷其他幕的情感走向"""

        user_msg = f"""<STORY_CONTEXT>
{worldview_context}
</STORY_CONTEXT>

{"".join(structure_tree)}

{"".join(incomplete_summary)}

【全书约束】
- 总章数：{target_chapters} 章
- 结构：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷
- 平均每幕：约 {avg_chapters_per_act} 章

【输出格式】
严格输出以下 JSON 结构，每个待补全幕必须对应一条 node_updates：
{{
  "node_updates": [
    {{
      "node_id": "A1_1_1",
      "narrative_goal": "该幕的叙事目标",
      "plot_points": ["具体情节点1", "具体情节点2"],
      "key_characters": ["角色ID或名称"],
      "key_locations": ["地点ID或名称"],
      "emotional_arc": "情感曲线描述"
    }}
  ]
}}

【严格要求】
1. 必须输出 {len(incomplete_acts)} 条 node_updates（对应 {len(incomplete_acts)} 个待补全幕）
2. 只输出缺失字段，不要包含已有的 title、description、estimated_chapters、setup_for、payoff_from
3. 充分参考完整结构树中前后幕的内容，确保情节连贯、不重复、不矛盾
4. 严格使用 STORY_CONTEXT 中的角色ID和地点ID，考虑角色弧光、角色关系、地点叙事意义、时间线事件
5. 不要编造新的角色或地点，如果确实需要可标注"待定"但需说明原因"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_macro_planning_prompt(self, bible_context: Dict, target_chapters: int, structure_preference: Dict, genre: str = "") -> Prompt:
        """构建宏观规划提示词（向后兼容的包装器）

        根据 structure_preference 是否为 None 来判断模式：
        - None: 极速模式（AI自主决定）
        - Dict: 精密模式（用户指定结构）
        """
        if structure_preference is None:
            # 极速模式：使用默认的3×3×3结构
            return self._build_quick_macro_prompt(bible_context, target_chapters, genre)
        else:
            # 精密模式：使用用户指定的结构
            skeleton = self._build_precise_structure_skeleton(target_chapters, structure_preference)
            return self._build_precise_macro_prompt(
                bible_context,
                target_chapters,
                structure_preference,
                skeleton,
                genre,
            )

    def _select_planning_template(self, genre: str, sub_genres: List[str]) -> tuple[str, Dict[str, str]]:
        """根据题材和子类型选择规划提示词模板

        Returns:
            tuple: (template_id, sub_genres_context_dict)
                - template_id: 'planning-historical', 'planning-xuanhuan', 'planning-hybrid', 或 'planning-act' (默认)
                - sub_genres_context_dict: 包含 sub_genres_instruction, sub_genres_tone, sub_genres_focus 的字典
        """
        genre_lower = (genre or "").lower()
        sub_genres_lower = [s.lower() for s in (sub_genres or [])]

        # 历史小说
        if genre_lower in ("history", "historical", "历史"):
            tone_parts = []
            focus_parts = []
            instructions = []

            if any(s in sub_genres_lower for s in ["chaotang", "guānchǎng", "quánmóu"]):
                instructions.append("【朝堂权谋向】强调派系博弈、历史进程中的关键抉择、朝代政治格局")
                tone_parts.append("精通历史叙事，注重朝代考据和权谋逻辑")
                focus_parts.append("派系斗争、政治博弈、关键抉择")

            if any(s in sub_genres_lower for s in ["hougong"]):
                instructions.append("【后宫/情感向】强调人物关系网、情感张力、身份反转")
                tone_parts.append("擅长宫斗叙事，注重情感纠葛和人物命运")
                focus_parts.append("情感纠葛、人物关系、身份反转")

            if any(s in sub_genres_lower for s in ["zhichang"]):
                instructions.append("【职场/日常向】强调日常积累、势力扩张、打脸节奏")
                tone_parts.append("擅长职场叙事，注重人物成长和势力积累")
                focus_parts.append("日常积累、势力扩张、打脸节奏")

            if any(s in sub_genres_lower for s in ["qingsong"]):
                instructions.append("【轻松/幽默向】强调反套路、幽默叙事、爽感但不沉重")
                tone_parts.append("轻松幽默，擅长反套路叙事和爽感节奏")
                focus_parts.append("反套路、幽默、轻松爽感")

            if any(s in sub_genres_lower for s in ["chuanyue"]):
                instructions.append("【穿越/架空向】强调现代知识运用、信息差优势、历史知识运用")
                tone_parts.append("擅长穿越叙事，注重信息差和现代知识运用")
                focus_parts.append("现代知识、信息差、历史知识运用")

            if any(s in sub_genres_lower for s in ["wuxia"]):
                instructions.append("【武侠/军事向】强调战斗体系、势力纷争、武侠精神")
                tone_parts.append("精通武侠叙事，注重战斗场面和江湖恩怨")
                focus_parts.append("战斗场面、江湖恩怨、武侠精神")

            if not instructions:
                instructions.append("【通用历史向】遵循历史小说创作规范，注重人物塑造和情节推进")
                tone_parts.append("精通历史叙事，注重朝代考据和故事深度")
                focus_parts.append("人物塑造、情节推进")

            return "planning-historical", {
                "sub_genres_instruction": "\n".join(instructions),
                "sub_genres_tone": "；".join(tone_parts) if tone_parts else "通用历史小说风格",
                "sub_genres_focus": "、".join(focus_parts) if focus_parts else "人物塑造和情节推进",
            }

        # 玄幻小说
        if genre_lower in ("xuanhuan", "玄幻", "仙侠", "fantasy"):
            tone_parts = []
            focus_parts = []
            instructions = []

            if any(s in sub_genres_lower for s in ["xiulian"]):
                instructions.append("【修炼升级流向】强调境界突破、升级节奏、爽点密度")
                tone_parts.append("擅长玄幻爽文，精通修炼体系设定和升级节奏控制")
                focus_parts.append("境界突破、升级节奏、爽点密度")

            if any(s in sub_genres_lower for s in ["fanren"]):
                instructions.append("【凡人流/苟道流向】强调资源争夺、谨慎发育、越级挑战")
                tone_parts.append("擅长凡人流叙事，注重生存压力和厚黑发育")
                focus_parts.append("资源争夺、谨慎发育、越级挑战")

            if any(s in sub_genres_lower for s in ["xitong"]):
                instructions.append("【系统流向】强调任务奖励、系统任务、量化成长")
                tone_parts.append("擅长系统流叙事，注重任务奖励和数值反馈")
                focus_parts.append("任务奖励、系统机制、量化成长")

            if any(s in sub_genres_lower for s in ["wudi"]):
                instructions.append("【无敌流/爽文流向】强调碾压快感、打脸装逼、极致爽感")
                tone_parts.append("擅长爽文叙事，注重打脸场面和装逼时刻")
                focus_parts.append("碾压打脸、装逼时刻、极致爽感")

            if any(s in sub_genres_lower for s in ["wuxian"]):
                instructions.append("【无限流/综漫向】强调副本切换、多世界冒险、丰富挑战")
                tone_parts.append("擅长无限流叙事，注重副本结构和多世界切换")
                focus_parts.append("副本结构、多世界冒险、丰富挑战")

            if not instructions:
                instructions.append("【通用玄幻向】遵循玄幻小说创作规范，注重修炼体系和爽感节奏")
                tone_parts.append("擅长玄幻爽文，精通修炼体系设定和升级节奏控制")
                focus_parts.append("修炼体系、爽感节奏")

            return "planning-xuanhuan", {
                "sub_genres_instruction": "\n".join(instructions),
                "sub_genres_tone": "；".join(tone_parts) if tone_parts else "通用玄幻风格",
                "sub_genres_focus": "、".join(focus_parts) if focus_parts else "修炼体系和爽感节奏",
            }

        # 混合模式（历史+玄幻）
        if genre_lower in ("hybrid", "混合"):
            instructions = [
                "【历史+玄幻混合模式】历史为表（朝代背景），玄幻为里（修炼/武侠）",
                "两套逻辑体系自洽：历史朝代格局 + 修炼/武侠体系并行",
                "双重爽感：权谋博弈 + 升级打脸双线交织",
            ]
            return "planning-hybrid", {
                "sub_genres_instruction": "\n".join(instructions),
                "sub_genres_tone": "精通历史与玄幻融合叙事，兼顾权谋逻辑和修炼体系",
                "sub_genres_focus": "历史格局与修炼体系融合、权谋与打脸并行",
            }

        # 默认通用模板
        return "planning-act", {
            "sub_genres_instruction": "",
            "sub_genres_tone": "",
            "sub_genres_focus": "",
        }

    def _build_act_planning_prompt(
        self,
        act_node: StoryNode,
        bible_context: Dict,
        previous_summary: Optional[str],
        chapter_count: int,
        genre: str = "",
        sub_genres: Optional[List[str]] = None,
        novel_id: str = None,
    ) -> Prompt:
        """构建幕级规划提示词

        Args:
            act_node: 幕节点
            bible_context: Bible 上下文
            previous_summary: 前情摘要
            chapter_count: 章节数量
            genre: 题材类型（如：history, xuanhuan, hybrid）
            sub_genres: 子题材列表
            novel_id: 小说 ID（用于获取题材上下文）
        """
        template_id, sub_genres_ctx = self._select_planning_template(genre, sub_genres or [])

        # 构建上下文信息
        context_parts = [f"幕信息：《{act_node.title}》"]
        if act_node.description:
            context_parts.append(f"幕简介：{act_node.description}")

        if previous_summary:
            context_parts.append(f"\n前情提要：{previous_summary}")

        # 添加 Bible 信息
        if bible_context.get("characters"):
            char_list = [f"- {c.get('name', 'Unknown')} (ID: {c.get('id', 'N/A')})" for c in bible_context["characters"][:5]]
            context_parts.append(f"\n可用人物：\n" + "\n".join(char_list))

        if bible_context.get("locations"):
            loc_list = [f"- {l.get('name', 'Unknown')} (ID: {l.get('id', 'N/A')})" for l in bible_context["locations"][:5]]
            context_parts.append(f"\n可用地点：\n" + "\n".join(loc_list))

        context = "\n".join(context_parts)

        # 根据模板ID构建系统提示词
        if template_id == "planning-historical":
            system_msg = f"""你是一位精通历史叙事的网文专家，擅长创作以真实历史朝代为背景的网络小说。

{sub_genres_ctx['sub_genres_instruction']}

写作特点：
1. 强调历史考据感，朝代细节准确（可根据需要调整）
2. 权谋博弈：派系斗争、政治博弈、人物抉择
3. 人物塑造：立体饱满，动机合理
4. 节奏把控：张力递进，爽感与深度并存
5. 文风定位：{sub_genres_ctx['sub_genres_tone']}

你的任务是为一幕规划生成章节框架。即使信息不完整也要生成合理的框架。
请直接输出 JSON 格式，不要询问额外信息，不要添加任何解释性文字。"""
        elif template_id == "planning-xuanhuan":
            system_msg = f"""你是一位精通玄幻修仙题材的网文大师，擅长创作修炼体系完备、爽感十足的玄幻小说。

{sub_genres_ctx['sub_genres_instruction']}

写作特点：
1. 修炼体系：境界划分清晰，升级节奏明快
2. 爽点密度：战斗/打脸/机缘/装逼一条龙
3. 金手指设定：系统/老爷爷/随身空间等
4. 越级挑战：合理但不失爽感
5. 文风定位：{sub_genres_ctx['sub_genres_tone']}

你的任务是为一幕规划生成章节框架。即使信息不完整也要生成合理的框架。
请直接输出 JSON 格式，不要询问额外信息，不要添加任何解释性文字。"""
        elif template_id == "planning-hybrid":
            system_msg = f"""你是一位精通历史与玄幻融合叙事的网文大师，擅长创作历史为表（朝代背景）、玄幻为里（修炼/武侠）的混合题材小说。

{sub_genres_ctx['sub_genres_instruction']}

写作特点：
1. 历史表面：朝代背景真实可考，政治格局宏大
2. 修炼内核：修炼体系与历史朝代融合自洽
3. 双重爽感：权谋博弈+升级打脸双线并行
4. 格局宏大：个人成长与王朝兴衰交相辉映

你的任务是为一幕规划生成章节框架。即使信息不完整也要生成合理的框架。
请直接输出 JSON 格式，不要询问额外信息，不要添加任何解释性文字。"""
        else:
            system_msg = """你是一个专业的小说章节规划助手，擅长设计章节大纲和情节安排。
你的任务是为一幕规划生成章节框架。即使信息不完整也要生成合理的框架。
请直接输出 JSON 格式，不要询问额外信息，不要添加任何解释性文字。"""

        # 子类型侧重点注入到用户消息
        sub_genres_focus = sub_genres_ctx.get("sub_genres_focus", "")
        focus_note = f"\n【子类型侧重】{sub_genres_focus}" if sub_genres_focus else ""

        # 获取题材上下文（world_rules, atmosphere, taboos, tropes）
        theme_context = ""
        if novel_id and self.theme_registry:
            # For act planning, we use chapter_number=1 as a placeholder since we're planning multiple chapters
            theme_context = self._build_theme_context_prompt(novel_id, 1, "")
            if theme_context:
                theme_context = f"\n【题材上下文】\n{theme_context}"

        user_msg = f"""{context}{focus_note}{theme_context}

请为这一幕规划 {chapter_count} 个章节。如果没有详细的世界观信息，请生成通用的章节框架。

要求：
1. 每个章节需要有标题和大纲
2. 如果有可用的人物和地点，尽量关联；如果没有，可以留空
3. 章节编号从 1 开始递增

请直接输出 JSON 格式，不要添加任何说明文字：
{{
  "chapters": [
    {{
      "number": 1,
      "title": "章节标题",
      "description": "章节简介（1-2句）",
      "outline": "章节大纲（100-200字）",
      "timeline_start": "本章开场时的时间/地点/状态，可留空",
      "timeline_end": "本章结尾时的时间/地点/状态，可留空；若无法确定不要编造",
      "characters": ["人物ID"],
      "locations": ["地点ID"]
    }}
  ]
}}"""
        return Prompt(system=system_msg, user=user_msg)

    async def _get_previous_acts_summary(self, act_node: StoryNode) -> Optional[str]:
        """获取前面幕的摘要"""
        return None

    async def _find_act_for_chapter(self, novel_id: str, chapter_number: int) -> Optional[StoryNode]:
        """查找章节所属的幕"""
        tree = self.story_node_repo.get_tree(novel_id)
        acts = [n for n in tree.nodes if n.node_type == NodeType.ACT]
        return max(acts, key=lambda x: x.number) if acts else None

    async def _count_written_chapters_in_act(self, act_id: str) -> int:
        """统计已写章节数"""
        children = self.story_node_repo.get_children(act_id, None)
        return sum(1 for n in children if n.node_type == NodeType.CHAPTER and n.word_count and n.word_count > 0)

    async def _count_planned_chapters_in_act(self, act_id: str) -> int:
        """统计已规划章节数"""
        children = self.story_node_repo.get_children(act_id, None)
        return sum(1 for n in children if n.node_type == NodeType.CHAPTER)

    async def _get_next_act(self, current_act: StoryNode) -> Optional[StoryNode]:
        """获取下一幕"""
        tree = self.story_node_repo.get_tree(current_act.novel_id)
        acts = [n for n in tree.nodes if n.node_type == NodeType.ACT and n.number == current_act.number + 1]
        return acts[0] if acts else None

    async def _generate_next_act_info(self, novel_id: str, current_act: StoryNode, bible_context: Dict) -> Dict:
        """生成下一幕信息（双轨融合版）
        
        轨道一：宏观摘要线
        - 注入前一卷/前一部的高浓缩摘要
        - 提供时空基石，防止时间线错乱
        
        轨道二：微观高亮线
        - 强制注入待回收伏笔
        - 注入角色当前状态锚点
        """
        # 收集双轨上下文
        dual_track_context = await self._collect_dual_track_context(novel_id, current_act, bible_context)
        
        # 构建增强型 Prompt
        prompt = self._build_next_act_prompt_with_dual_track(current_act, dual_track_context)
        
        try:
            response = await self.llm_service.generate(prompt, GenerationConfig(max_tokens=4096, temperature=0.7))
            result = self._parse_llm_response(response)
            
            # 确保返回必要的字段
            if not isinstance(result, dict):
                result = {}
            result.setdefault("title", f"第{current_act.number + 1}幕")
            result.setdefault("description", "继续推进剧情")
            result.setdefault("suggested_chapter_count", 5)
            
            return result
        except Exception as e:
            logger.warning(f"生成下一幕信息失败: {e}")
            return {
                "title": f"第{current_act.number + 1}幕",
                "description": "描述",
                "suggested_chapter_count": 5
            }
    
    async def _collect_dual_track_context(
        self,
        novel_id: str,
        current_act: StoryNode,
        bible_context: Dict,
    ) -> Dict[str, str]:
        """收集双轨上下文
        
        Returns:
            {
                "volume_summary": "前一卷的摘要",
                "current_volume_summary": "当前卷的摘要",
                "pending_foreshadowings": "待回收伏笔列表",
                "character_states": "角色状态锚点",
            }
        """
        context = {
            "volume_summary": "",
            "current_volume_summary": "",
            "pending_foreshadowings": "",
            "character_states": "",
        }
        
        try:
            # 获取所有节点
            all_nodes = await self.story_node_repo.get_by_novel(novel_id)
            
            # 找到当前幕所属的卷
            current_volume = None
            if current_act.parent_id:
                current_volume = next(
                    (n for n in all_nodes if n.id == current_act.parent_id),
                    None
                )
            
            # 轨道一：获取卷摘要
            if current_volume:
                vol_summary = current_volume.metadata.get("summary", "") if current_volume.metadata else ""
                if vol_summary:
                    context["current_volume_summary"] = f"【当前卷进度】{current_volume.title}\n{vol_summary}"
            
            # 获取前一卷的摘要
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "volume"],
                key=lambda x: x.number
            )
            if current_volume:
                prev_volumes = [v for v in volume_nodes if v.number < (current_volume.number or 0)]
                if prev_volumes:
                    prev_vol = prev_volumes[-1]
                    prev_summary = prev_vol.metadata.get("summary", "") if prev_vol.metadata else ""
                    if prev_summary:
                        context["volume_summary"] = f"【前一卷回顾】{prev_vol.title}\n{prev_summary}"
            
            # 轨道二：获取待回收伏笔
            if hasattr(self, 'chapter_repository') and self.chapter_repository:
                try:
                    from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
                    from domain.novel.value_objects.novel_id import NovelId
                    
                    # 尝试获取伏笔仓库（通过依赖注入或直接创建）
                    if hasattr(self.story_node_repo, 'db_path'):
                        from infrastructure.persistence.database.foreshadowing_repository import ForeshadowingRepositoryImpl
                        foreshadowing_repo = ForeshadowingRepositoryImpl(self.story_node_repo.db_path)
                        registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
                        
                        if registry:
                            pending = registry.get_unresolved()
                            if pending:
                                lines = ["【待回收伏笔】"]
                                for f in pending[:5]:
                                    lines.append(f"- 第{f.planted_in_chapter}章: {f.description}")
                                context["pending_foreshadowings"] = "\n".join(lines)
                except Exception as e:
                    logger.debug(f"获取伏笔信息时出错: {e}")
            
            # 轨道二：获取角色状态
            if bible_context and bible_context.get("characters"):
                char_lines = ["【角色当前状态】"]
                for char in bible_context["characters"][:3]:
                    name = char.get("name", "")
                    desc = char.get("description", "")
                    mental = char.get("mental_state", "")
                    tic = char.get("verbal_tic", "")
                    
                    char_info = f"- {name}: {desc[:50]}"
                    if mental:
                        char_info += f" [心理: {mental}]"
                    if tic:
                        char_info += f" 口头禅: {tic}"
                    char_lines.append(char_info)
                
                context["character_states"] = "\n".join(char_lines)
        
        except Exception as e:
            logger.warning(f"收集双轨上下文失败: {e}")
        
        return context
    
    def _build_next_act_prompt_with_dual_track(
        self,
        current_act: StoryNode,
        dual_track_context: Dict[str, str],
    ) -> Prompt:
        """构建双轨融合的下一幕生成 Prompt"""
        
        system = """你是一位资深的小说结构设计师，擅长在长篇叙事中推进剧情。
你的任务是为下一幕设计详细的内容规划，确保：
1. 与前文保持连贯，不出现时间线或人物状态矛盾
2. 有意识地回收或推进已有伏笔
3. 设置新的冲突和悬念

请直接输出 JSON 格式，不要添加解释性文字。"""
        
        # 组装双轨上下文
        context_parts = []
        
        if dual_track_context.get("volume_summary"):
            context_parts.append(dual_track_context["volume_summary"])
        
        if dual_track_context.get("current_volume_summary"):
            context_parts.append(dual_track_context["current_volume_summary"])
        
        if dual_track_context.get("pending_foreshadowings"):
            context_parts.append(dual_track_context["pending_foreshadowings"])
        
        if dual_track_context.get("character_states"):
            context_parts.append(dual_track_context["character_states"])
        
        context_block = "\n\n".join(context_parts) if context_parts else "暂无前文上下文"
        
        user = f"""【双轨上下文】
{context_block}

【当前幕信息】
幕标题：{current_act.title}
幕描述：{current_act.description or '无'}
幕号：第 {current_act.number} 幕

【任务】
请生成第 {current_act.number + 1} 幕的详细规划。

【输出要求】
请输出 JSON 格式：
{{
  "title": "幕标题（动词+名词，暗示冲突）",
  "description": "幕简介（100-200字，包含核心事件、冲突、转折）",
  "suggested_chapter_count": 预估章数（整数）,
  "key_events": ["事件1", "事件2"],
  "narrative_arc": "叙事弧线（如：紧张→爆发→暂缓）",
  "foreshadow_to_resolve": ["需要回收的伏笔"],
  "foreshadow_to_plant": ["需要埋下的新伏笔"]
}}"""
        
        return Prompt(system=system, user=user)

    # ==================== 续写规划功能 ====================

    async def continue_planning(
        self,
        novel_id: str,
        target_chapter_count: int = 10
    ) -> Dict:
        """续写规划：基于已写章节内容 + 小说背景设定生成后续规划

        Args:
            novel_id: 小说ID
            target_chapter_count: 续写目标章节数

        Returns:
            续写规划结果
        """
        logger.info(f"Starting continue planning for novel {novel_id}, target chapters: {target_chapter_count}")

        # 1. 获取小说实体（包含 premise 等背景信息）
        if not self.novel_repository:
            raise ValueError("novel_repository is required for continue_planning")

        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if not novel:
            raise ValueError(f"小说不存在: {novel_id}")

        # 2. 获取小说的完整背景设定（从 StoryKnowledge）
        novel_background = await self._get_novel_background(novel_id)

        # 3. 获取已写章节的摘要
        if not self.chapter_repository:
            raise ValueError("chapter_repository is required for continue_planning")

        written_chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        written_chapters.sort(key=lambda c: c.number)

        if not written_chapters:
            raise ValueError("无已写章节，无法续写规划")

        # 4. 提取最近章节的状态和趋势
        recent_chapters = written_chapters[-5:]
        recent_summary = await self._summarize_recent_chapters(recent_chapters)

        # 5. 获取 Bible 上下文
        bible_context = self._get_bible_context(novel_id)

        # 6. 获取待回收伏笔
        pending_foreshadowings = await self._get_pending_foreshadowings(novel_id)

        # 7. 构建续写规划提示词（携带完整背景）
        prompt = self._build_continue_planning_prompt(
            novel_premise=novel.premise,
            novel_background=novel_background,
            recent_summary=recent_summary,
            bible_context=bible_context,
            pending_foreshadowings=pending_foreshadowings,
            target_count=target_chapter_count,
            last_chapter_number=written_chapters[-1].number
        )

        # 8. 调用 LLM 生成续写规划
        try:
            response = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=4096, temperature=0.7)
            )

            plan = self._parse_llm_response(response)

            # 9. 创建新的幕/卷（如果需要）并确认规划
            return await self._confirm_continue_planning(novel_id, plan)

        except Exception as e:
            logger.error(f"续写规划失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _get_novel_background(self, novel_id: str) -> Dict[str, Any]:
        """获取小说的完整背景设定

        从 StoryKnowledge 中提取：
        - premise_lock: 梗概锁定（新书设置向导生成的故事设定）
        - 核心设定三元组

        Returns:
            {
                "premise_lock": "小说梗概",
                "world_setting": "世界观设定",
                "core_conflicts": "核心冲突",
                "character_relationships": "角色关系"
            }
        """
        background = {
            "premise_lock": "",
            "world_setting": "",
            "core_conflicts": "",
            "character_relationships": ""
        }

        if not self.knowledge_service:
            logger.warning("knowledge_service not available, returning empty background")
            return background

        try:
            # 获取 StoryKnowledge
            knowledge = self.knowledge_service.get_knowledge(novel_id)

            # 1. 梗概锁定（最重要的背景信息）
            if hasattr(knowledge, 'premise_lock') and knowledge.premise_lock:
                background["premise_lock"] = knowledge.premise_lock

            # 2. 从知识三元组中提取核心设定（单次遍历优化）
            if hasattr(knowledge, 'facts') and knowledge.facts:
                world_facts = []
                conflict_facts = []
                relation_facts = []

                for f in knowledge.facts:
                    if f.predicate in ["世界观", "设定", "背景", "时代"]:
                        world_facts.append(f)
                    elif f.predicate in ["冲突", "对立", "矛盾", "敌对"]:
                        conflict_facts.append(f)
                    elif f.predicate in ["关系", "是", "属于", "师徒", "朋友", "敌人"]:
                        relation_facts.append(f)

                if world_facts:
                    background["world_setting"] = "\n".join(
                        f"- {f.subject} {f.predicate} {f.object}"
                        for f in world_facts[:5]
                    )

                if conflict_facts:
                    background["core_conflicts"] = "\n".join(
                        f"- {f.subject} {f.predicate} {f.object}"
                        for f in conflict_facts[:5]
                    )

                if relation_facts:
                    background["character_relationships"] = "\n".join(
                        f"- {f.subject} {f.predicate} {f.object}"
                        for f in relation_facts[:10]
                    )

        except Exception as e:
            logger.warning(f"获取小说背景设定失败: {e}")

        return background

    async def _summarize_recent_chapters(self, chapters: List[Chapter]) -> str:
        """总结最近章节的内容和趋势"""
        summaries = []
        for ch in chapters:
            if ch.content:
                # 提取章节摘要（可以调用 LLM 或使用已有的 state）
                summary = f"第{ch.number}章《{ch.title}》: {ch.content[:200]}..."
                summaries.append(summary)
        return "\n".join(summaries)

    async def _get_pending_foreshadowings(self, novel_id: str) -> List[Dict]:
        """获取待回收伏笔"""
        if not self.foreshadowing_repository:
            return []

        try:
            registry = self.foreshadowing_repository.get_by_novel_id(NovelId(novel_id))
            if not registry:
                return []

            # 筛选未回收的伏笔
            pending = [f for f in registry.foreshadowings if not f.is_resolved]
            return [
                {"description": f.description, "chapter": f.chapter_number}
                for f in pending
            ]
        except Exception as e:
            logger.warning(f"获取待回收伏笔失败: {e}")
            return []

    def _build_continue_planning_prompt(
        self,
        novel_premise: str,
        novel_background: Dict[str, Any],
        recent_summary: str,
        bible_context: Dict,
        pending_foreshadowings: List[Dict],
        target_count: int,
        last_chapter_number: int
    ) -> Prompt:
        """构建续写规划提示词（携带完整背景）"""
        system_msg = """你是专业的小说续写规划助手。
你的任务是基于小说的背景设定、已写章节的内容和趋势，规划后续章节的发展。
必须确保：
1. 严格遵循小说的背景设定和世界观
2. 延续已有剧情的逻辑和风格
3. 回收待解决的伏笔
4. 推进主要故事线
5. 保持角色行为的一致性"""

        # 构建背景信息部分
        background_section = f"""=== 小说背景设定 ===
梗概：{novel_premise or '无'}

故事设定：
{novel_background.get('premise_lock', '无')}

世界观：
{novel_background.get('world_setting', '无')}

核心冲突：
{novel_background.get('core_conflicts', '无')}

角色关系：
{novel_background.get('character_relationships', '无')}
"""

        user_msg = f"""{background_section}

=== 最近章节摘要 ===
{recent_summary}

=== 待回收伏笔 ===
{chr(10).join(f"- {f['description']} (第{f['chapter']}章埋下)" for f in pending_foreshadowings) if pending_foreshadowings else '无'}

=== 可用人物 ===
{chr(10).join(f"- {c['name']}: {c.get('description', '')[:50]}" for c in bible_context.get('characters', [])[:10])}

=== 可用地点 ===
{chr(10).join(f"- {l['name']}: {l.get('description', '')[:50]}" for l in bible_context.get('locations', [])[:10])}

请基于以上信息，规划后续 {target_count} 个章节（从第 {last_chapter_number + 1} 章开始）。

⚠️ 重要约束：
1. 必须严格遵循「小说背景设定」中的世界观和核心冲突
2. 必须延续「最近章节摘要」中的剧情逻辑
3. 优先回收「待回收伏笔」
4. 合理使用「可用人物」和「可用地点」

输出 JSON 格式：
{{
  "acts": [
    {{
      "title": "幕标题",
      "description": "幕描述",
      "suggested_chapter_count": 5,
      "chapters": [
        {{
          "number": {last_chapter_number + 1},
          "title": "章节标题",
          "outline": "章节大纲（100-200字）",
          "description": "章节简介"
        }}
      ]
    }}
  ]
}}"""

        return Prompt(system=system_msg, user=user_msg)

    async def _confirm_continue_planning(self, novel_id: str, plan: Dict) -> Dict:
        """确认续写规划：创建新的幕/卷并确认章节规划"""
        # TODO: 实现创建新幕/卷的逻辑
        # 这里需要根据 plan 中的 acts 创建新的幕节点，并调用 confirm_act_planning
        logger.info(f"Confirming continue planning for novel {novel_id}")
        return {
            "success": True,
            "plan": plan
        }
