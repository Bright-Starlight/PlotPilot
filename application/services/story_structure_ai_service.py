"""叙事结构 AI 生成服务

负责智能生成和管理叙事结构（部-卷-幕-章）
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from domain.structure.story_node import StoryNode, NodeType
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)


class StoryStructureAIService:
    """叙事结构 AI 生成服务

    智能生成叙事结构，而非固定模板：
    - 首次进入时生成第一幕
    - 章节完成后判断是否结束当前幕
    - 自动创建下一幕/卷/部
    """

    def __init__(self, repository: StoryNodeRepository, llm_service: Optional[LLMService] = None, bible_service=None):
        self.repository = repository
        self.llm_service = llm_service
        self.bible_service = bible_service

    async def initialize_first_act(self, novel_id: str) -> Dict[str, Any]:
        """初始化第一幕

        首次进入工作台时调用，AI 生成第一幕的结构和大纲

        Args:
            novel_id: 小说 ID

        Returns:
            生成结果，包含创建的节点信息
        """
        logger.info(f"Initializing first act for novel: {novel_id}")

        # 检查作品设定是否存在
        if self.bible_service:
            bible = self.bible_service.get_bible_by_novel(novel_id)
            if not bible:
                logger.warning(f"No bible found for novel {novel_id}")
                return {
                    "success": False,
                    "message": "请先创建作品设定（Story Bible）",
                    "nodes_created": 0,
                    "error_code": "BIBLE_REQUIRED"
                }

            # 检查是否有文风设定
            if not bible.style_notes or len(bible.style_notes) == 0:
                logger.warning(f"No style notes found in bible for novel {novel_id}")
                return {
                    "success": False,
                    "message": "请先填写文风设定",
                    "nodes_created": 0,
                    "error_code": "STYLE_REQUIRED"
                }

        # 检查是否已有结构（排除章节节点，只检查幕/卷/部）
        existing = await self.repository.get_tree(novel_id)
        structure_nodes = [n for n in existing.nodes if n.node_type in [NodeType.PART, NodeType.VOLUME, NodeType.ACT]]
        if structure_nodes:
            logger.info(f"Structure already exists for novel {novel_id}, skipping initialization")
            return {
                "success": False,
                "message": "叙事结构已存在",
                "nodes_created": 0
            }

        # 使用 AI 生成第一幕的标题和描述
        act_title, act_description = await self._generate_act_metadata(
            novel_id=novel_id,
            act_number=1,
            context="这是故事的第一幕，需要引入主要人物、设定和初始冲突"
        )

        # 创建第一幕节点
        act_node = StoryNode(
            id=f"act-{novel_id}-1",
            novel_id=novel_id,
            node_type=NodeType.ACT,
            number=1,
            title=act_title,
            description=act_description,
            parent_id=None,
            order_index=1,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.repository.save(act_node)

        logger.info(f"Created first act: {act_node.id}")

        return {
            "success": True,
            "message": "第一幕已创建",
            "nodes_created": 1,
            "act_id": act_node.id,
            "act_title": act_title
        }

    async def check_act_completion(
        self,
        novel_id: str,
        chapter_number: int
    ) -> Dict[str, Any]:
        """检查幕是否完成

        章节生成完成后调用，判断当前幕是否应该结束

        Args:
            novel_id: 小说 ID
            chapter_number: 刚完成的章节号

        Returns:
            检查结果，包含是否需要创建新幕
        """
        logger.info(f"Checking act completion for novel {novel_id}, chapter {chapter_number}")

        # 获取当前章节所属的幕
        tree = self.repository.get_tree(novel_id)
        current_act = self._find_act_for_chapter(tree, chapter_number)

        if not current_act:
            logger.warning(f"No act found for chapter {chapter_number}")
            return {
                "act_completed": False,
                "should_create_next": False
            }

        # 使用 AI 判断是否应该结束当前幕
        chapters_in_act = self._count_chapters_in_act(current_act)
        should_end = await self._should_end_act(
            novel_id=novel_id,
            current_act=current_act,
            chapter_number=chapter_number,
            chapters_in_act=chapters_in_act
        )

        logger.info(f"Act {current_act.id} has {chapters_in_act} chapters, should_end={should_end}")

        return {
            "act_completed": should_end,
            "should_create_next": should_end,
            "current_act_id": current_act.id,
            "chapters_in_act": chapters_in_act
        }

    async def create_next_act(
        self,
        novel_id: str,
        previous_act_id: str
    ) -> Dict[str, Any]:
        """创建下一幕

        当前幕完成后自动调用

        Args:
            novel_id: 小说 ID
            previous_act_id: 上一幕的 ID

        Returns:
            创建结果
        """
        logger.info(f"Creating next act for novel {novel_id} after {previous_act_id}")

        # 获取上一幕信息
        previous_act = self.repository.get_by_id(previous_act_id)
        if not previous_act:
            raise ValueError(f"Previous act not found: {previous_act_id}")

        # 计算新幕的编号
        next_number = previous_act.number + 1

        # 检查是否需要创建新卷或新部
        parent_id = previous_act.parent_id
        should_create_volume = await self._should_create_new_volume(novel_id, previous_act)
        should_create_part = await self._should_create_new_part(novel_id, previous_act)

        if should_create_part:
            # 创建新部
            parent_id = await self._create_next_part(novel_id, previous_act.parent_id)
        elif should_create_volume:
            # 创建新卷
            parent_id = await self._create_next_volume(novel_id, previous_act.parent_id)

        # 使用 AI 生成下一幕的标题和描述
        act_title, act_description = await self._generate_act_metadata(
            novel_id=novel_id,
            act_number=next_number,
            context=f"这是第{next_number}幕，承接第{previous_act.number}幕的剧情发展"
        )

        # 创建新幕节点
        act_node = StoryNode(
            id=f"act-{novel_id}-{next_number}",
            novel_id=novel_id,
            node_type=NodeType.ACT,
            number=next_number,
            title=act_title,
            description=act_description,
            parent_id=parent_id,
            order_index=previous_act.order_index + 1,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.repository.save(act_node)

        logger.info(f"Created next act: {act_node.id}")

        return {
            "success": True,
            "message": f"第{next_number}幕已创建",
            "act_id": act_node.id,
            "act_title": act_title,
            "act_number": next_number
        }

    def _find_act_for_chapter(
        self,
        tree,
        chapter_number: int
    ) -> Optional[StoryNode]:
        """查找章节所属的幕

        由于当前没有章节范围信息，返回最新的幕节点
        """
        # 如果是 StoryTree 对象，获取其 nodes 列表
        nodes = tree.nodes if hasattr(tree, 'nodes') else tree

        # 获取所有幕节点，返回最新的一个
        acts = [node for node in nodes if node.node_type == NodeType.ACT]
        if acts:
            # 按编号排序，返回最大的（最新的）
            return max(acts, key=lambda x: x.number)

        return None

    def _chapter_in_range(self, act: StoryNode, chapter_number: int) -> bool:
        """判断章节是否在幕的范围内"""
        if act.chapter_start and act.chapter_end:
            return act.chapter_start <= chapter_number <= act.chapter_end
        return False

    def _count_chapters_in_act(self, act: StoryNode) -> int:
        """统计幕中的章节数

        通过parent_id查询实际关联的章节数
        """
        # 方法1: 通过parent_id查询子章节
        children = self.repository.get_children(act.id, act.novel_id)
        chapter_count = len([node for node in children if node.node_type == NodeType.CHAPTER])

        if chapter_count > 0:
            return chapter_count

        # 方法2: 如果有章节范围信息，使用它（向后兼容）
        if act.chapter_start and act.chapter_end:
            return act.chapter_end - act.chapter_start + 1

        # 否则返回 0
        return 0

    async def _generate_act_metadata(
        self,
        novel_id: str,
        act_number: int,
        context: str
    ) -> tuple[str, str]:
        """使用 AI 生成幕的标题和描述

        Args:
            novel_id: 小说 ID
            act_number: 幕编号
            context: 上下文信息

        Returns:
            (标题, 描述) 元组
        """
        if not self.llm_service:
            # 降级：无 LLM 时使用默认值
            logger.warning("No LLM service available, using default act metadata")
            return f"第{act_number}幕", f"第{act_number}幕的内容"

        try:
            # 构建提示词
            system_prompt = """你是一位专业的小说结构规划师。
你的任务是为小说的某一幕生成标题和描述。

要求：
1. 标题简洁有力，能概括这一幕的核心主题（10字以内）
2. 描述详细说明这一幕的主要情节发展和目标（50-100字）
3. 返回格式为 JSON：{"title": "标题", "description": "描述"}
"""

            user_prompt = f"""小说ID: {novel_id}
幕编号: 第{act_number}幕
上下文: {context}

请生成这一幕的标题和描述。"""

            prompt = Prompt(system=system_prompt, user=user_prompt)
            config = GenerationConfig(
                model="claude-sonnet-4-6",
                max_tokens=500,
                temperature=0.7
            )

            result = await self.llm_service.generate(prompt, config)

            # 解析 JSON 响应
            import json
            content = result.content.strip()
            # 移除可能的 markdown 代码块标记
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)
            title = data.get("title", f"第{act_number}幕")
            description = data.get("description", f"第{act_number}幕的内容")

            logger.info(f"Generated act metadata: title={title}, description={description}")
            return title, description

        except Exception as e:
            logger.error(f"Failed to generate act metadata: {e}", exc_info=True)
            # 降级：生成失败时使用默认值
            return f"第{act_number}幕", f"第{act_number}幕的内容"

    async def _should_end_act(
        self,
        novel_id: str,
        current_act: StoryNode,
        chapter_number: int,
        chapters_in_act: int
    ) -> bool:
        """使用 AI 判断是否应该结束当前幕

        Args:
            novel_id: 小说 ID
            current_act: 当前幕节点
            chapter_number: 当前章节号
            chapters_in_act: 幕中已有章节数

        Returns:
            是否应该结束当前幕
        """
        if not self.llm_service:
            # 降级：无 LLM 时使用简单规则（每 10 章一幕）
            logger.warning("No LLM service available, using simple rule for act completion")
            return chapters_in_act >= 10

        try:
            # 获取最近几章的内容作为上下文
            recent_chapters = await self._get_recent_chapters(novel_id, chapter_number, limit=3)

            system_prompt = """你是一位专业的小说结构分析师。
你的任务是判断当前幕是否应该结束，是否应该开始新的一幕。

判断标准：
1. 当前幕的主要情节线是否已经完成
2. 是否出现了明显的转折点或新的冲突
3. 章节数量是否合理（通常一幕包含 8-15 章）
4. 故事节奏是否需要调整

返回格式为 JSON：{"should_end": true/false, "reason": "判断理由"}
"""

            user_prompt = f"""小说ID: {novel_id}
当前幕: {current_act.title}
幕描述: {current_act.description}
当前章节号: 第{chapter_number}章
幕中已有章节数: {chapters_in_act}章

最近章节内容摘要：
{recent_chapters}

请判断当前幕是否应该结束。"""

            prompt = Prompt(system=system_prompt, user=user_prompt)
            config = GenerationConfig(
                model="claude-sonnet-4-6",
                max_tokens=300,
                temperature=0.3
            )

            result = await self.llm_service.generate(prompt, config)

            # 解析 JSON 响应
            import json
            content = result.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            data = json.loads(content)
            should_end = data.get("should_end", False)
            reason = data.get("reason", "")

            logger.info(f"AI decision for act completion: should_end={should_end}, reason={reason}")
            return should_end

        except Exception as e:
            logger.error(f"Failed to check act completion with AI: {e}", exc_info=True)
            # 降级：判断失败时使用简单规则
            return chapters_in_act >= 10

    async def _get_recent_chapters(
        self,
        novel_id: str,
        current_chapter: int,
        limit: int = 3
    ) -> str:
        """获取最近几章的内容摘要

        Args:
            novel_id: 小说 ID
            current_chapter: 当前章节号
            limit: 获取章节数量

        Returns:
            章节内容摘要
        """
        try:
            tree = self.repository.get_tree(novel_id)
            chapters = []

            for node in tree.nodes:
                if node.node_type == NodeType.CHAPTER:
                    if current_chapter - limit < node.number <= current_chapter:
                        chapters.append(node)

            chapters.sort(key=lambda x: x.number)

            if not chapters:
                return "暂无章节内容"

            summaries = []
            for chapter in chapters:
                content_preview = chapter.content[:200] if chapter.content else "无内容"
                summaries.append(f"第{chapter.number}章 {chapter.title}: {content_preview}...")

            return "\n".join(summaries)

        except Exception as e:
            logger.error(f"Failed to get recent chapters: {e}", exc_info=True)
            return "无法获取章节内容"

    async def _should_create_new_volume(
        self,
        novel_id: str,
        current_act: StoryNode
    ) -> bool:
        """判断是否需要创建新卷

        Args:
            novel_id: 小说 ID
            current_act: 当前幕节点

        Returns:
            是否需要创建新卷
        """
        # 简单规则：每 3 幕创建一个新卷
        # 可以后续扩展为 AI 判断
        if not current_act.parent_id:
            return False

        parent = self.repository.get_by_id(current_act.parent_id)
        if not parent or parent.node_type != NodeType.VOLUME:
            return False

        # 统计当前卷中的幕数量
        tree = self.repository.get_tree(novel_id)
        acts_in_volume = sum(
            1 for node in tree.nodes
            if node.node_type == NodeType.ACT and node.parent_id == parent.id
        )

        return acts_in_volume >= 3

    async def _should_create_new_part(
        self,
        novel_id: str,
        current_act: StoryNode
    ) -> bool:
        """判断是否需要创建新部

        Args:
            novel_id: 小说 ID
            current_act: 当前幕节点

        Returns:
            是否需要创建新部
        """
        # 简单规则：每 3 卷创建一个新部
        # 可以后续扩展为 AI 判断
        if not current_act.parent_id:
            return False

        parent = self.repository.get_by_id(current_act.parent_id)
        if not parent:
            return False

        if parent.node_type == NodeType.VOLUME and parent.parent_id:
            grandparent = self.repository.get_by_id(parent.parent_id)
            if grandparent and grandparent.node_type == NodeType.PART:
                # 统计当前部中的卷数量
                tree = self.repository.get_tree(novel_id)
                volumes_in_part = sum(
                    1 for node in tree.nodes
                    if node.node_type == NodeType.VOLUME and node.parent_id == grandparent.id
                )
                return volumes_in_part >= 3

        return False

    async def _create_next_volume(
        self,
        novel_id: str,
        parent_id: Optional[str]
    ) -> str:
        """创建下一卷

        Args:
            novel_id: 小说 ID
            parent_id: 父节点 ID（部）

        Returns:
            新卷的 ID
        """
        # 获取当前最大卷号
        tree = self.repository.get_tree(novel_id)
        max_volume_number = max(
            (node.number for node in tree.nodes if node.node_type == NodeType.VOLUME),
            default=0
        )

        next_number = max_volume_number + 1

        # 使用 AI 生成卷标题和描述（可选）
        volume_title = f"第{next_number}卷"
        volume_description = f"第{next_number}卷的内容"

        volume_node = StoryNode(
            id=f"volume-{novel_id}-{next_number}",
            novel_id=novel_id,
            node_type=NodeType.VOLUME,
            number=next_number,
            title=volume_title,
            description=volume_description,
            parent_id=parent_id,
            order_index=next_number,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.repository.save(volume_node)
        logger.info(f"Created new volume: {volume_node.id}")

        return volume_node.id

    async def _create_next_part(
        self,
        novel_id: str,
        parent_id: Optional[str]
    ) -> str:
        """创建下一部

        Args:
            novel_id: 小说 ID
            parent_id: 父节点 ID（通常为 None）

        Returns:
            新部的 ID
        """
        # 获取当前最大部号
        tree = self.repository.get_tree(novel_id)
        max_part_number = max(
            (node.number for node in tree.nodes if node.node_type == NodeType.PART),
            default=0
        )

        next_number = max_part_number + 1

        # 使用 AI 生成部标题和描述（可选）
        part_title = f"第{next_number}部"
        part_description = f"第{next_number}部的内容"

        part_node = StoryNode(
            id=f"part-{novel_id}-{next_number}",
            novel_id=novel_id,
            node_type=NodeType.PART,
            number=next_number,
            title=part_title,
            description=part_description,
            parent_id=parent_id,
            order_index=next_number,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        self.repository.save(part_node)
        logger.info(f"Created new part: {part_node.id}")

        return part_node.id

