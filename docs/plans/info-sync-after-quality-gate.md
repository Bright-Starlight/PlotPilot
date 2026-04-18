# 质量门禁通过后信息同步方案

## 背景

当 `quality_gate_passed = True` (可发布) 后，需要进行完整的信息同步，包括：
1. 向量存储
2. 伏笔提取
3. 知识图谱更新
4. 文风检测
5. 一致性检查

**关键约束**：
- 不使用小说正文进行信息同步，而是使用**融合草稿生成的文本**
- 需要检查是否还有其他地方进行了信息同步
- 需要确定是进行一次还是多次同步

## 当前实现分析

### 1. 现有信息同步位置

#### 1.1 ChapterAftermathPipeline (主要同步点)
**文件**: `application/engine/services/chapter_aftermath_pipeline.py`

**执行时机**: 章节保存后立即执行

**同步内容**:
```python
async def run_after_chapter_saved(
    novel_id: str,
    chapter_number: int,
    content: str,  # ← 使用的是正文
    *,
    run_quality_gate: bool = False,
    quality_gate_mode: str = "full",
) -> Dict[str, Any]:
    # 1. 质量门禁 (可选)
    if run_quality_gate:
        gate_result = await self._run_quality_gate(...)
        if not gate_result.get("quality_gate_passed", True):
            return out  # ← 门禁失败，提前返回，不执行后续同步
    
    # 2. 叙事同步 + 向量索引 (使用正文)
    await sync_chapter_narrative_after_save(
        novel_id, chapter_number, content,  # ← 使用正文
        ...
    )
    
    # 3. 文风评分 (使用正文)
    if self._voice:
        vr = await self._voice.score_chapter_async(
            novel_id, chapter_number, content  # ← 使用正文
        )
    
    # 4. 结构树 KG 推断
    await infer_kg_from_chapter(novel_id, chapter_number)
```

#### 1.2 sync_chapter_narrative_after_save (叙事同步)
**文件**: `application/world/services/chapter_narrative_sync.py`

**同步内容**:
- LLM 提取: summary, key_events, open_threads, ending_state, ending_emotion
- 三元组 (relation_triples)
- 伏笔 (foreshadow_hints + consumed_foreshadows)
- 故事线进展 (storyline_progress)
- 张力值 (tension_score + tension_dimensions)
- 对话提取 (dialogues)
- 时间轴事件 (timeline_events)
- **向量索引** (使用 summary 或 beat_sections 或正文前 800 字)

#### 1.3 AutopilotDaemon (自动驾驶)
**文件**: `application/engine/services/autopilot_daemon.py:1600-1650`

**执行流程**:
```python
# 1. 首次执行章后管线 (带质量门禁)
drift_result = await self.aftermath_pipeline.run_after_chapter_saved(
    novel.novel_id.value,
    chapter_num,
    content,  # ← 使用正文
    run_quality_gate=True,
)

quality_gate_passed = bool(drift_result.get("quality_gate_passed", True))

# 2. 如果门禁失败，重试 (retry 模式)
if not quality_gate_passed:
    retry_result = await self.aftermath_pipeline._run_quality_gate(
        novel.novel_id.value,
        chapter_num,
        content,
        quality_gate_mode="retry",
    )
    
    # 3. 如果重试通过，再次执行章后管线 (不带质量门禁)
    if retry_result.get("quality_gate_passed", True):
        drift_result = await self.aftermath_pipeline.run_after_chapter_saved(
            novel.novel_id.value,
            chapter_num,
            content,  # ← 仍然使用正文
        )
```

### 2. 问题识别

#### 问题 1: 使用正文而非融合草稿
当前所有信息同步都使用 `content` (正文)，而非融合草稿生成的文本。

**融合草稿位置**:
- 存储在 `chapter_fusion_drafts` 表
- 通过 `SqliteChapterFusionRepository.get_latest_draft_for_chapter(chapter_id)` 获取
- 字段: `draft.text` (融合后的文本)

#### 问题 2: 重复同步
在自动驾驶场景下，如果门禁失败后重试成功，会执行**两次**信息同步：
1. 第一次: `run_quality_gate=True` 时，门禁失败前已执行部分同步
2. 第二次: 重试成功后，再次调用 `run_after_chapter_saved` (不带质量门禁)

#### 问题 3: 缺少一致性检查
当前没有显式的一致性检查步骤。

### 3. 融合草稿文本获取

**融合草稿结构**:
```python
@dataclass
class FusionDraft:
    fusion_id: str
    chapter_id: str
    novel_id: str
    plan_version: int
    state_lock_version: int
    text: str  # ← 融合后的文本
    end_state: Dict[str, Any]
    created_at: str
    latest_validation_report_id: str | None
```

**获取方式**:
```python
# 方式 1: 通过 chapter_id 获取最新草稿
draft = fusion_repository.get_latest_draft_for_chapter(chapter_id)

# 方式 2: 通过 fusion_id 获取特定草稿
draft = fusion_repository.get_draft(fusion_id)
```

## 关键发现：Validation 已包含一致性检查

### Validation 检查内容

**文件**: `application/core/services/validation_service.py`

**检查层次** (三层检查):
1. **规则检测层** (Rule Detection): 确定性事实冲突检测
   - 数值冲突 (`_detect_numeric_conflicts`): 同一物品不同价格等
   - 示例: 玉佩当了三两 vs 五十两

2. **状态比较层** (State Comparison): 终态偏差检测
   - State Locks 违规 (`evaluate_text_violations`): 检查是否违反状态锁
   - 计划终态不匹配 (`_detect_plan_end_state_mismatch`): 检查是否偏离规划终态

3. **语义判断层** (Semantic Judgment): LLM 语义一致性
   - 语义检查 (`_run_semantic_checks`): 人物身份漂移、世界观冲突等
   - 使用 Bible (人物设定、世界观) 作为上下文

**检查结果**:
- P0 (阻断): 必须修复才能发布
- P1 (警告): 建议修复
- P2 (提示): 可选修复

**质量门禁流程**:
```
State Locks 生成 → 融合草稿生成 → Validation 检查
                                    ↓
                            blocking_issue_count > 0?
                                    ↓
                            Yes → 门禁失败 (quality_gate_passed = False)
                            No  → 门禁通过 (quality_gate_passed = True)
```

**结论**: **不需要额外的一致性检查**，Validation 已经覆盖了：
- ✅ 人物设定一致性 (通过 Bible + 语义判断)
- ✅ 世界观一致性 (通过 Bible + 语义判断)
- ✅ 前后衔接一致性 (通过 State Locks + 计划终态)
- ✅ 伏笔一致性 (通过语义判断)
- ✅ 事实一致性 (通过规则检测)

## 解决方案

### 方案 A: 单次同步 (推荐)

**核心思路**: 质量门禁通过后，使用融合草稿文本进行**一次完整同步**，**无需额外一致性检查**。

#### A.1 修改 ChapterAftermathPipeline

```python
async def run_after_chapter_saved(
    self,
    novel_id: str,
    chapter_number: int,
    content: str,
    *,
    run_quality_gate: bool = False,
    quality_gate_mode: str = "full",
    use_fusion_draft: bool = False,  # ← 新增参数
) -> Dict[str, Any]:
    """保存正文后执行完整管线。
    
    Args:
        use_fusion_draft: 如果为 True，使用融合草稿文本而非正文进行信息同步
    """
    out: Dict[str, Any] = {
        "drift_alert": False,
        "similarity_score": None,
        "narrative_sync_ok": False,
        "quality_gate_passed": True,
    }

    if not content or not str(content).strip():
        logger.debug("aftermath 跳过：正文为空 novel=%s ch=%s", novel_id, chapter_number)
        return out

    # 1. 质量门禁
    if run_quality_gate:
        gate_result = await self._run_quality_gate(
            novel_id,
            chapter_number,
            content,
            quality_gate_mode=quality_gate_mode,
        )
        out.update(gate_result)
        
        # ← 关键修改：门禁失败时，直接返回，不执行任何信息同步
        if not gate_result.get("quality_gate_passed", True):
            logger.warning(
                "aftercare gate blocked novel=%s ch=%s step=%s reason=%s",
                novel_id,
                chapter_number,
                gate_result.get("quality_gate_step", "unknown"),
                gate_result.get("quality_gate_reason", "quality gate failed"),
            )
            return out
        
        # ← 新增：门禁通过后，如果有融合草稿，使用融合草稿文本
        if use_fusion_draft and self._chapter_fusion_service is not None:
            chapter = self._resolve_chapter(novel_id, chapter_number)
            if chapter:
                draft = self._chapter_fusion_service.fusion_repository.get_latest_draft_for_chapter(chapter.id)
                if draft and draft.text:
                    content = draft.text
                    logger.info(
                        "使用融合草稿文本进行信息同步 novel=%s ch=%s fusion_id=%s",
                        novel_id, chapter_number, draft.fusion_id
                    )

    # 2. 叙事同步 + 向量索引 (使用 content，可能是融合草稿)
    try:
        from application.world.services.chapter_narrative_sync import (
            sync_chapter_narrative_after_save,
        )

        await sync_chapter_narrative_after_save(
            novel_id,
            chapter_number,
            content,  # ← 可能是融合草稿文本
            self._knowledge,
            self._indexing,
            self._llm,
            triple_repository=self._triple_repository,
            foreshadowing_repo=self._foreshadowing_repository,
            storyline_repository=self._storyline_repository,
            chapter_repository=self._chapter_repository,
            plot_arc_repository=self._plot_arc_repository,
            narrative_event_repository=self._narrative_event_repository,
        )
        out["narrative_sync_ok"] = True
    except Exception as e:
        logger.warning(
            "叙事同步/向量失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
        )

    # 3. 文风评分 (使用 content，可能是融合草稿)
    if self._voice:
        try:
            if getattr(self._voice, "use_llm_mode", False):
                vr = await self._voice.score_chapter_async(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    content=content,  # ← 可能是融合草稿文本
                )
            else:
                vr = self._voice.score_chapter(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    content=content,  # ← 可能是融合草稿文本
                )
            out["drift_alert"] = bool(vr.get("drift_alert", False))
            out["similarity_score"] = vr.get("similarity_score")
            out["voice_mode"] = vr.get("mode", "statistics")
            logger.debug(
                "文风评分完成 novel=%s ch=%s mode=%s drift=%s",
                novel_id,
                chapter_number,
                out.get("voice_mode"),
                out["drift_alert"],
            )
        except Exception as e:
            logger.warning("文风评分失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    # 4. 结构树 KG 推断
    await infer_kg_from_chapter(novel_id, chapter_number)

    return out
```

#### A.2 修改 AutopilotDaemon

```python
# 在 autopilot_daemon.py 中修改

# 1. 首次执行章后管线 (带质量门禁，但不执行信息同步)
drift_result = await self.aftermath_pipeline._run_quality_gate(
    novel.novel_id.value,
    chapter_num,
    content,
    quality_gate_mode="full",
)

quality_gate_passed = bool(drift_result.get("quality_gate_passed", True))

# 2. 如果门禁失败，重试
if not quality_gate_passed:
    logger.warning(
        f"[{novel.novel_id}] 章节 {chapter_num} 审计门禁未通过，开始重试（跳过 State Locks）"
    )
    retry_result = await self.aftermath_pipeline._run_quality_gate(
        novel.novel_id.value,
        chapter_num,
        content,
        quality_gate_mode="retry",
    )
    drift_result.update(retry_result)
    quality_gate_passed = bool(retry_result.get("quality_gate_passed", True))
    
    if not quality_gate_passed:
        logger.warning(
            f"[{novel.novel_id}] 章节 {chapter_num} 审计重试仍未通过，退出自动驾驶"
        )
        novel.autopilot_status = AutopilotStatus.STOPPED
        novel.current_stage = NovelStage.AUDITING
        self._save_novel_state(novel)
        return

# 3. 门禁通过后，执行完整信息同步 (使用融合草稿)
logger.info(
    f"[{novel.novel_id}] 章节 {chapter_num} 审计通过，执行信息同步（使用融合草稿）"
)
drift_result = await self.aftermath_pipeline.run_after_chapter_saved(
    novel.novel_id.value,
    chapter_num,
    content,
    run_quality_gate=False,  # ← 不再执行质量门禁
    use_fusion_draft=True,   # ← 使用融合草稿
)
logger.info(
    f"[{novel.novel_id}] 信息同步完成: 相似度={drift_result.get('similarity_score')}, "
    f"drift_alert={drift_result.get('drift_alert')}, "
    f"consistency_ok={drift_result.get('consistency_check_ok')}"
)
```

### 方案 B: 分阶段同步 (备选)

**核心思路**: 将信息同步分为两个阶段：
1. **质量门禁阶段**: 仅执行质量门禁，不执行任何信息同步
2. **信息同步阶段**: 门禁通过后，使用融合草稿进行完整信息同步

**优点**:
- 职责更清晰
- 避免重复同步

**缺点**:
- 需要更多代码重构
- 调用链更复杂

## 推荐方案

**推荐方案 A (单次同步)**，理由：
1. **最小改动**: 只需修改 `ChapterAftermathPipeline` 和 `AutopilotDaemon`
2. **避免重复**: 门禁失败时不执行信息同步，门禁通过后只执行一次
3. **使用融合草稿**: 通过 `use_fusion_draft` 参数控制
4. **完整性**: 包含向量存储、伏笔提取、知识图谱、文风检测、一致性检查

## 实施步骤

### 第 1 步: 修改 ChapterAftermathPipeline
- [x] 添加 `use_fusion_draft` 参数
- [x] 门禁失败时提前返回，不执行信息同步（已存在）
- [x] 门禁通过且 `use_fusion_draft=True` 时，获取融合草稿文本

### 第 2 步: 修改 AutopilotDaemon
- [x] 首次只执行质量门禁 (`_run_quality_gate`)
- [x] 门禁通过后，调用 `run_after_chapter_saved(use_fusion_draft=True)`
- [x] 移除重复的信息同步调用

### 第 3 步: 测试
- [x] 单元测试: `test_chapter_aftermath_pipeline.py` (3/3 通过)
- [x] 集成测试: `test_autopilot_daemon.py` (3/3 通过)
- [ ] E2E 测试: 完整自动驾驶流程

### 第 4 步: 文档更新
- [ ] 更新 `ARCHITECTURE.md`
- [ ] 更新 API 文档

## 信息同步清单

门禁通过后，使用融合草稿文本进行以下同步：

| 序号 | 同步项 | 实现位置 | 数据源 | 目标存储 |
|------|--------|----------|--------|----------|
| 1 | 叙事摘要 | `sync_chapter_narrative_after_save` | 融合草稿 | `story_knowledge.chapters` |
| 2 | 向量索引 | `ChapterIndexingService.index_chapter_summary` | 融合草稿 summary | Qdrant |
| 3 | 三元组 | `persist_bundle_triples_and_foreshadows` | LLM 提取 | `bible_triples` |
| 4 | 伏笔注册 | `persist_bundle_triples_and_foreshadows` | LLM 提取 | `foreshadowing_registry` |
| 5 | 伏笔消费 | `persist_bundle_triples_and_foreshadows` | LLM 检测 | `foreshadowing_registry` |
| 6 | 故事线进展 | `persist_bundle_extras` | LLM 提取 | `storylines` |
| 7 | 张力值 | `TensionScoringService.score_chapter` | LLM 评分 | `chapters.tension_score` |
| 8 | 对话提取 | `persist_bundle_extras` | LLM 提取 | `narrative_events` |
| 9 | 时间轴事件 | `persist_bundle_extras` | LLM 提取 | `bible_timeline_notes` |
| 10 | 文风评分 | `VoiceDriftService.score_chapter_async` | 融合草稿 | `chapter_style_scores` |
| 11 | 知识图谱 | `infer_kg_from_chapter` | 结构树 | `bible_triples` |
| ~~12~~ | ~~一致性检查~~ | ~~已由 Validation 完成~~ | ~~融合草稿~~ | ~~validation_reports~~ |

## 注意事项

1. **融合草稿可用性**: 并非所有章节都有融合草稿，需要检查 `draft is not None and draft.text`
2. **向后兼容**: `use_fusion_draft` 默认为 `False`，保持现有行为
3. **一致性检查**: 已由 Validation 完成，无需重复检查
4. **错误处理**: 每个同步步骤都需要独立的异常处理，避免单点失败影响整体
5. **日志记录**: 详细记录使用融合草稿还是正文，便于调试

## 未来优化

1. **并行同步**: 将独立的同步任务并行执行，提升性能
2. **增量同步**: 仅同步变更部分，避免全量同步
3. **同步队列**: 使用消息队列异步处理信息同步
4. **同步状态追踪**: 记录每个同步步骤的状态，支持断点续传
