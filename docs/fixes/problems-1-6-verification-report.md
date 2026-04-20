# 问题 1-6 验证报告

## 验证日期
2026-04-19

---

## ✅ 问题 1：一键规划与全托管模式互相覆盖

### 状态：**已完全解决**

### 验证结果

**代码位置：** `application/blueprint/services/continuous_planning_service.py:894-936`

**实现内容：**
1. ✅ 添加了 `force_overwrite` 参数（默认 False）
2. ✅ 添加了 `append_mode` 参数（默认 False）
3. ✅ 实现了三种模式：
   - **保护模式**（force_overwrite=False, append_mode=False）：有已有规划时跳过，返回已有规划
   - **覆盖模式**（force_overwrite=True, append_mode=False）：删除已有规划，写入新规划
   - **追加模式**（force_overwrite=False, append_mode=True）：保留已有规划，追加新章节

**调用点验证：**
- ✅ `autopilot_daemon.py:596,612,828` - 全托管模式使用 `force_overwrite=False`
- ✅ `continuous_planning_routes.py:196` - 前端一键规划使用 `force_overwrite=True`

**结论：** 问题已完全解决，三种模式都已实现并正确集成。

---

## ✅ 问题 2：全托管模式需要判断是否已有规划

### 状态：**已完全解决**

### 验证结果

**代码位置：** `application/engine/services/autopilot_daemon.py:756-829`

**实现内容：**
1. ✅ 添加了 `_get_expected_chapter_count` 方法（行511-522）
   - 优先级1：幕节点自己的配置
   - 优先级2：小说全局配置（planning_config.chapters_per_act）
   - 优先级3：默认值5

2. ✅ 重写了 `_handle_act_planning` 方法，实现智能规划复用：
   - 检查已有章节数量
   - 数量充足（≥期望值）：直接进入写作阶段
   - 数量不足（>0 但 <期望值）：调用补齐功能
   - 无章节（=0）：执行完整规划

**结论：** 问题已完全解决，全托管模式会智能复用已有规划。

---

## ✅ 问题 3：章节数量判断和补齐

### 状态：**已完全解决**

### 验证结果

**代码位置：** `application/engine/services/autopilot_daemon.py:524-649`

**实现内容：**
1. ✅ 添加了 `_supplement_act_chapters` 方法（行524-618）
   - 获取最后一章信息作为续写起点
   - 获取 Bible 上下文
   - 构建补齐规划提示词
   - 调用 LLM 生成补充章节
   - 使用 `append_mode=True` 确认补充规划

2. ✅ 添加了 `_build_supplement_chapters_prompt` 方法（行620-649）
   - 构建专门的补齐提示词
   - 包含幕信息、最后一章摘要、可用人物等上下文

3. ✅ 添加了 `_fallback_supplement_chapters` 方法（行651-666）
   - 降级方案：生成占位补充章节
   - 确保系统在 LLM 失败时仍能继续运行

**结论：** 问题已完全解决，章节数量不足时会自动补齐。

---

## ❌ 问题 4：参数统一性

### 状态：**未实施**

### 验证结果

**预期实现：** Novel 实体增加 `PlanningConfig` 类

**实际情况：**
```bash
$ python -c "from domain.novel.entities.novel import Novel; import inspect; print('planning_config' in inspect.signature(Novel.__init__).parameters)"
False
```

**缺失内容：**
1. ❌ Novel 实体没有 `planning_config` 字段
2. ❌ 没有 `PlanningConfig` 数据类
3. ❌ 数据库没有 `planning_config` 字段

**当前状态：**
- `_get_expected_chapter_count` 方法已经预留了对 `planning_config` 的支持（行518-519）
- 但由于 Novel 实体没有这个字段，这部分代码永远不会执行
- 目前只能依赖 act 节点的 `suggested_chapter_count` 或默认值5

**影响：**
- 无法在小说级别统一配置章节数量
- 手动规划和全托管模式可能生成不同数量的章节
- 部/卷/幕的章节数量配置不统一

**结论：** 问题未解决，需要实施 part2 方案。

---

## ✅ 问题 5：续写规划功能（携带小说背景设定）

### 状态：**已完全解决**

### 验证结果

**代码位置：** `application/blueprint/services/continuous_planning_service.py:2251-2400`

**实现内容：**
1. ✅ 添加了 `continue_planning` 方法（行2251-2326）
   - 获取小说实体（包含 premise）
   - 获取小说完整背景设定
   - 获取已写章节摘要
   - 获取 Bible 上下文
   - 获取待回收伏笔
   - 构建携带完整背景的续写规划提示词
   - 调用 LLM 生成续写规划

2. ✅ 添加了 `_get_novel_background` 方法（行2328-2400）
   - 从 StoryKnowledge 提取背景信息
   - 提取 premise_lock（梗概锁定）
   - 提取世界观设定
   - 提取核心冲突
   - 提取角色关系

3. ✅ 添加了 `_summarize_recent_chapters` 方法（行2402+）
   - 总结最近章节的内容和趋势

4. ✅ 添加了 `_get_pending_foreshadowings` 方法
   - 获取待回收伏笔

5. ✅ 添加了 `_build_continue_planning_prompt` 方法
   - 构建携带完整背景的续写规划提示词

**结论：** 问题已完全解决，续写规划功能已实现并携带小说背景设定。

---

## ✅ 问题 6：节拍数量调整

### 状态：**已完全解决**

### 验证结果

**代码位置：** `application/blueprint/services/beat_calculator.py`

**实现内容：**
1. ✅ 创建了 `BeatCalculator` 类（完整实现）
   - `calculate_beat_count()` - 根据章节字数计算节拍数量（3-7个）
   - `calculate_words_per_beat()` - 计算每个节拍的目标字数
   - `validate_beat_count()` - 验证节拍数量是否合理

2. ✅ 集成到 `BeatSheetService`（行57-99）
   - 添加了 `target_beat_count` 参数
   - 使用 `BeatCalculator.calculate_beat_count()` 动态计算节拍数
   - 使用 `BeatCalculator.calculate_words_per_beat()` 分配字数

3. ✅ 集成到 `ChapterAftermathPipeline`（行352-360）
   - 使用 `BeatCalculator.calculate_beat_count()` 计算节拍数

**验证使用情况：**
```bash
$ grep -r "BeatCalculator" --include="*.py" application/
application/blueprint/services/beat_sheet_service.py:92:        from application.blueprint.services.beat_calculator import BeatCalculator
application/blueprint/services/beat_sheet_service.py:94:            target_beat_count = BeatCalculator.calculate_beat_count(target_words_per_chapter)
application/blueprint/services/beat_sheet_service.py:97:        words_per_beat = BeatCalculator.calculate_words_per_beat(
application/engine/services/chapter_aftermath_pipeline.py:352:                    from application.blueprint.services.beat_calculator import BeatCalculator
application/engine/services/chapter_aftermath_pipeline.py:360:                    target_beat_count = BeatCalculator.calculate_beat_count(target_words_per_chapter)
```

**结论：** 问题已完全解决，节拍数量会根据章节字数动态调整。

---

## 📊 总体评估

| 问题 | 状态 | 完成度 | 备注 |
|------|------|--------|------|
| 问题 1：规划覆盖冲突 | ✅ 已解决 | 100% | 三种模式都已实现 |
| 问题 2：判断已有规划 | ✅ 已解决 | 100% | 智能复用逻辑已实现 |
| 问题 3：数量判断和补齐 | ✅ 已解决 | 100% | 补齐功能已实现 |
| 问题 4：参数统一性 | ❌ 未解决 | 0% | Novel 实体缺少 PlanningConfig |
| 问题 5：续写规划功能 | ✅ 已解决 | 100% | 携带背景设定已实现 |
| 问题 6：节拍数量调整 | ✅ 已解决 | 100% | BeatCalculator 已实现并集成 |

**总体完成度：5/6 = 83.3%**

---

## ⚠️ 关键发现

### 1. 问题 4 未实施的影响

虽然 `_get_expected_chapter_count` 方法已经预留了对 `planning_config` 的支持，但由于 Novel 实体没有这个字段，导致：

- 无法在小说级别统一配置章节数量
- 目前只能依赖 act 节点的 `suggested_chapter_count` 或默认值5
- 这可能导致手动规划和全托管模式生成不同数量的章节

### 2. 问题 1-3 的实施质量

问题 1-3 的实施质量很高：
- 代码逻辑清晰
- 错误处理完善
- 有降级方案
- 日志记录详细
- 已通过语法检查和单元测试

### 3. 问题 5-6 的实施质量

问题 5-6 的实施也很完整：
- `continue_planning` 功能完整实现
- `BeatCalculator` 已创建并集成到多个服务
- 代码已在实际使用中

---

## 🎯 后续工作建议

### 立即需要做的（问题 4）

1. **创建 PlanningConfig 数据类**
   ```python
   @dataclass
   class PlanningConfig:
       chapters_per_act: int = 5
       acts_per_volume: int = 3
       volumes_per_part: int = 2
   ```

2. **修改 Novel 实体**
   - 添加 `planning_config: Optional[PlanningConfig]` 字段
   - 更新 `__init__` 方法

3. **数据库迁移**
   - 添加 `planning_config` 字段（TEXT 类型，存储 JSON）
   - 为现有小说添加默认配置

4. **更新仓储层**
   - 修改 `SqliteNovelRepository` 的序列化/反序列化逻辑

### 预计工作量

- 问题 4 实施：约 2-3 小时
- 测试验证：约 1 小时
- **总计：3-4 小时**

---

## ✅ 结论

**问题 1-3：已完全解决，实施质量高**
- 规划覆盖冲突已解决
- 智能复用已实现
- 章节补齐已实现

**问题 5-6：已完全解决，功能完整**
- 续写规划携带背景设定已实现
- 动态节拍调整已实现并集成

**问题 4：未实施，需要补充**
- Novel 实体缺少 PlanningConfig
- 这是唯一未完成的问题
- 预计 3-4 小时可以完成

**总体评价：5/6 问题已解决，完成度 83.3%。问题 4 需要补充实施。**
