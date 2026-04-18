# 质量门禁通过后信息同步方案 A 实现总结

## 实施日期
2026-04-18

## 实施内容

按照 `docs/plans/info-sync-after-quality-gate.md` 中的**方案 A**完成实现。

## 核心改动

### 1. ChapterAftermathPipeline.run_after_chapter_saved

**文件**: `application/engine/services/chapter_aftermath_pipeline.py`

**改动**:
- 添加 `use_fusion_draft: bool = False` 参数
- 门禁通过后，如果 `use_fusion_draft=True`，获取融合草稿文本并替换 `content`
- 使用融合草稿文本进行后续的信息同步（叙事、向量、文风、KG）

**关键代码**:
```python
# 门禁通过后，如果有融合草稿，使用融合草稿文本
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
```

### 2. AutopilotDaemon._handle_auditing

**文件**: `application/engine/services/autopilot_daemon.py`

**改动**:
- 首次只执行质量门禁 (`_run_quality_gate`)，不执行信息同步
- 门禁失败时，执行重试 (`quality_gate_mode="retry"`)
- 门禁通过后：
  1. **获取融合草稿并替换章节正文** (`chapter.content = draft.text`)
  2. 调用 `run_after_chapter_saved(use_fusion_draft=True)` 执行一次完整信息同步
- 移除了重复的信息同步调用

**关键流程**:
```
1. 首次质量门禁 (full 模式)
   ↓
2. 门禁失败？
   ├─ 是 → 重试质量门禁 (retry 模式)
   │        ↓
   │     重试失败？
   │     ├─ 是 → 停止自动驾驶，不执行信息同步
   │     └─ 否 → 继续到步骤 3
   └─ 否 → 继续到步骤 3
   ↓
3. 获取融合草稿并替换章节正文 (chapter.content = draft.text)
   ↓
4. 执行信息同步 (使用融合草稿)
```

### 3. 测试更新

**文件**: `tests/unit/application/services/test_autopilot_daemon.py`

**改动**:
- 更新 `test_handle_auditing_retries_quality_gate_before_stopping`：验证门禁重试成功后执行一次信息同步
- 更新 `test_handle_auditing_stops_when_quality_gate_retry_fails`：验证门禁重试失败后不执行信息同步

## 关键优势

### 1. 避免重复同步
- **之前**: 门禁失败后重试成功，会执行两次信息同步
- **现在**: 门禁通过后只执行一次信息同步

### 2. 使用融合草稿
- **之前**: 使用正文 (`content`) 进行信息同步
- **现在**: 使用融合草稿 (`draft.text`) 进行信息同步

### 3. 职责清晰
- **质量门禁**: 只负责验证（State Locks → 融合草稿 → Validation）
- **信息同步**: 只在门禁通过后执行一次

### 4. 向后兼容
- `use_fusion_draft` 默认为 `False`，不影响其他调用点（HTTP API、托管连写）

## 测试结果

### 单元测试
- ✅ `test_chapter_aftermath_pipeline.py`: 3/3 通过
- ✅ `test_autopilot_daemon.py` (auditing 相关): 3/3 通过

### 测试覆盖场景
1. ✅ 门禁首次通过 → 执行信息同步
2. ✅ 门禁首次失败 → 重试成功 → 执行信息同步
3. ✅ 门禁首次失败 → 重试失败 → 不执行信息同步，停止自动驾驶

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

**注意**: 一致性检查已由 Validation 完成，无需重复检查。

## 风险评估

- **风险级别**: LOW
- **影响范围**: 仅影响自动驾驶审计流程
- **向后兼容**: 是（其他调用点不受影响）
- **测试覆盖**: 完整

## 后续工作

- [ ] E2E 测试: 完整自动驾驶流程
- [ ] 更新 `ARCHITECTURE.md`
- [ ] 更新 API 文档

## 参考文档

- 方案设计: `docs/plans/info-sync-after-quality-gate.md`
- 相关代码:
  - `application/engine/services/chapter_aftermath_pipeline.py`
  - `application/engine/services/autopilot_daemon.py`
  - `tests/unit/application/services/test_autopilot_daemon.py`
