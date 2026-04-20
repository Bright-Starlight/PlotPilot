# 规划系统改进方案

## 📋 问题分析

### 问题 1：一键规划与全托管模式互相覆盖

**现状问题：**
- `confirm_act_planning` 第887行会调用 `_remove_chapter_children_of_act` 无条件删除已有章节
- 导致手动规划和全托管模式规划互相覆盖

### 问题 2：全托管模式需要判断是否已有规划

**现状问题：**
- 全托管模式每次都重新规划，不会复用已有的手动规划
- 缺少对已有规划的检查机制

### 问题 3：章节数量判断和补齐

**现状问题：**
- 当幕下已有章节时，不会判断数量是否符合全局设置
- 如果章节数量小于期望值，不会自动补齐

### 问题 4：参数统一性

**现状问题：**
- 部/卷/幕的章节数量配置不统一
- 手动规划和全托管模式可能生成不同数量的章节

### 问题 5：续写规划功能

**现状问题：**
- 手动规划和全托管模式都不会生成整部小说的大纲
- 缺少基于已写章节的续写规划功能
- 续写规划没有携带小说背景设定（新书设置向导中的故事设定）

### 问题 6：节拍数量调整

**现状问题：**
- 节拍数量固定（默认3或5）
- 不会根据单章字数动态调整
- 1000字的章节使用5个节拍显然不合适

---

## 🔧 解决方案

### 方案 1：规划覆盖冲突解决

**修改 `confirm_act_planning` 方法，增加 `force_overwrite` 参数：**

```python
# application/blueprint/services/continuous_planning_service.py

async def confirm_act_planning(
    self, 
    act_id: str, 
    chapters: List[Dict],
    force_overwrite: bool = False  # 新增参数
) -> Dict:
    """确认幕级规划
    
    Args:
        act_id: 幕ID
        chapters: 章节列表
        force_overwrite: 是否强制覆盖已有规划（默认False，保留已有规划）
    """
    act_node = await self.story_node_repo.get_by_id(act_id)
    if not act_node:
        raise ValueError(f"幕节点不存在: {act_id}")
    
    # 检查是否已有章节规划
    existing_chapters = self.story_node_repo.get_children_sync(act_id)
    chapter_nodes = [n for n in existing_chapters if n.node_type == NodeType.CHAPTER]
    
    if chapter_nodes and not force_overwrite:
        # 已有规划且不强制覆盖，直接返回已有规划
        logger.info(f"幕 {act_id} 已有 {len(chapter_nodes)} 个章节规划，跳过覆盖")
        return {
            "success": True,
            "act_id": act_id,
            "chapters": [self._chapter_node_to_dict(n) for n in chapter_nodes],
            "skipped": True,
            "reason": "已有规划，未覆盖"
        }
    
    # 仅在 force_overwrite=True 时删除已有章节
    if chapter_nodes and force_overwrite:
        await self._remove_chapter_children_of_act(act_id)
    
    # 继续原有的创建逻辑...
    # ... (保持原有代码)
```

**调用方调整：**

```python
# autopilot_daemon.py 中的调用
await self.planning_service.confirm_act_planning(
    act_id=target_act.id,
    chapters=chapters_data,
    force_overwrite=False  # 全托管模式不覆盖已有规划
)

# 前端一键规划的调用
await self.planning_service.confirm_act_planning(
    act_id=act_id,
    chapters=chapters,
    force_overwrite=True  # 用户主动规划时可以覆盖
)
```

---

### 方案 2：全托管模式判断已有规划 + 数量补齐

**修改 `_handle_act_planning` 方法：**

```python
# application/engine/services/autopilot_daemon.py

async def _handle_act_planning(self, novel: Novel) -> None:
    """幕级规划阶段（智能复用 + 数量补齐）"""
    target_act = self._find_target_act(novel)
    if not target_act:
        logger.warning(f"[{novel.novel_id}] 未找到目标幕，跳过规划")
        novel.current_stage = NovelStage.COMPLETED
        self._flush_novel(novel)
        return
    
    # 1. 获取全局配置的章节数量
    expected_chapter_count = self._get_expected_chapter_count(novel, target_act)
    
    # 2. 检查该幕下已有章节数量
    existing_chapters = self.story_node_repo.get_children_sync(target_act.id)
    chapter_nodes = [n for n in existing_chapters if n.node_type == NodeType.CHAPTER]
    current_count = len(chapter_nodes)
    
    logger.info(
        f"[{novel.novel_id}] 幕 {target_act.number} 章节数量检查: "
        f"已有 {current_count} 章, 期望 {expected_chapter_count} 章"
    )
    
    # 3. 根据数量判断操作
    if current_count >= expected_chapter_count:
        # 数量充足或超出，直接进入写作阶段
        logger.info(
            f"[{novel.novel_id}] 幕 {target_act.number} 章节数量充足 "
            f"({current_count} >= {expected_chapter_count})，直接进入写作阶段"
        )
        novel.current_stage = NovelStage.CHAPTER_WRITING
        novel.current_act_id = target_act.id
        novel.current_beat_index = 0
        self._flush_novel(novel)
        return
    
    elif current_count > 0:
        # 数量不足，需要补齐
        shortage = expected_chapter_count - current_count
        logger.info(
            f"[{novel.novel_id}] 幕 {target_act.number} 章节数量不足，"
            f"需要补齐 {shortage} 章"
        )
        
        # 调用补齐规划
        await self._supplement_act_chapters(
            novel=novel,
            target_act=target_act,
            existing_chapters=chapter_nodes,
            shortage_count=shortage
        )
        
        # 补齐后进入写作阶段
        novel.current_stage = NovelStage.CHAPTER_WRITING
        novel.current_act_id = target_act.id
        novel.current_beat_index = 0
        self._flush_novel(novel)
        return
    
    else:
        # 无章节，执行完整规划
        logger.info(f"[{novel.novel_id}] 幕 {target_act.number} 无规划，开始自动规划")
        
        try:
            plan_result = await self.planning_service.plan_act_chapters(
                act_id=target_act.id,
                custom_chapter_count=expected_chapter_count
            )
        except Exception as e:
            logger.warning(f"[{novel.novel_id}] 幕级规划失败: {e}", exc_info=True)
            plan_result = {}
        
        if not self._is_still_running(novel):
            logger.info(f"[{novel.novel_id}] 规划返回后检测到停止")
            return
        
        chapters_data = plan_result.get("chapters", [])
        if not chapters_data:
            logger.warning(f"[{novel.novel_id}] 未得到有效章节规划，使用占位章节")
            chapters_data = self._fallback_act_chapters_plan(target_act, expected_chapter_count)
        
        await self.planning_service.confirm_act_planning(
            act_id=target_act.id,
            chapters=chapters_data,
            force_overwrite=False
        )
        
        novel.current_stage = NovelStage.CHAPTER_WRITING
        novel.current_act_id = target_act.id
        novel.current_beat_index = 0
        self._flush_novel(novel)
```

**新增辅助方法：**

```python
def _get_expected_chapter_count(self, novel: Novel, act_node) -> int:
    """获取期望的章节数量（优先级：act配置 > novel全局配置 > 默认值）"""
    # 优先级1：幕节点自己的配置
    if act_node.suggested_chapter_count and act_node.suggested_chapter_count > 0:
        return act_node.suggested_chapter_count
    
    # 优先级2：小说全局配置
    if hasattr(novel, 'planning_config') and novel.planning_config:
        return novel.planning_config.chapters_per_act
    
    # 优先级3：默认值
    return 5
```

