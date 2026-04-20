## Context

**现状**:
- ThemeAgent 框架已实现（ThemeAgentRegistry, XuanhuanThemeAgent, HistoryThemeAgent），每个 Agent 有专属 beat templates、context directives、buffer chapter templates
- BeatSheetService.generate_beat_sheet() 用通用逻辑生成节拍表，未使用 ThemeAgent
- ContinuousPlanningService 生成章节 outline 时未注入题材专属上下文
- Novel.genre 字段已存在，ThemeAgentRegistry.auto_discover() 可按 genre_key 加载对应 Agent

**约束**:
- 必须向后兼容：genre 为空或未注册题材时回退通用逻辑
- ThemeAgent 在 BeatSheetService 中已通过 `bible_service` 间接可用，但未直接调用 beat templates
- 章节规划是高频操作，需控制 Agent 加载开销

## Goals / Non-Goals

**Goals:**
- BeatSheetService 生成节拍表时根据 novel.genre 选用对应 ThemeAgent 的 beat templates
- **章节规划时注入上层情节设计**：追溯 Act → Volume → Part 的 description，拼入 LLM prompt
- ContinuousPlanningService 生成 outline 时注入 ThemeAgent 的 world_rules/atmosphere/taboos/tropes
- 玄幻、历史题材的章节规划结果明显优于通用规划

**Non-Goals:**
- 不实现都市题材的专属规划（用户明确本次不做）
- 不修改 ThemeAgent 本身（xuanhuan_agent, history_agent 已完成）
- 不改变 API 契约（参数/返回值结构不变）
- 不修改宏观规划流程本身，只在章节生成时读取已有宏观设定

## Decisions

### Decision 1: 在 BeatSheetService 中集成 ThemeAgent 而非新建服务

**选择**: 直接在 BeatSheetService 中注入 ThemeAgentRegistry，根据 novel.genre 获取 Agent 并合并 beat templates。

**理由**:
- BeatSheetService 是节拍表生成的唯一入口，集中在此修改改动最小
- 避免引入新的服务增加复杂度
- ThemeAgentRegistry.get_or_default() 支持 genre 为空时返回 None，直接走通用逻辑

**替代方案**:
- 新建 GenreAwareBeatSheetService：过度工程化，只有在逻辑复杂时才拆
- 在 ContinuousPlanningService 统一处理：职责不清，规划服务不应直接处理节拍表

### Decision 2: 通过 LLM prompt 注入题材上下文

**选择**: 在 ContinuousPlanningService 的 outline 生成 prompt 中拼接 ThemeAgent.get_context_directives() 的内容。

**理由**:
- 不改变 API 契约，只修改 prompt 模板
- ThemeAgent.get_context_directives() 返回 ThemeDirectives(world_rules, atmosphere, taboos, tropes_to_use, tropes_to_avoid)，已结构化可直接拼接
- LLM 能自然地将题材约束融入生成的 outline

**替代方案**:
- 改造 StoryNodeRepository 存储题材元数据：过度设计，题材上下文是运行时 prompt 变量

### Decision 3: beat template 合并策略

**选择**:
- 如果 ThemeAgent 有 matching keywords 的 template，优先使用题材专属 template 的 beats
- 如果没有匹配，fallback 到通用 beat 计算逻辑
- 每个 beat 的字数分配按 template 指定的 priority 和 beats 比例调整

**理由**:
- 关键词匹配是最直接有效的题材感知方式
- 保留通用逻辑作为 fallback 保证鲁棒性

### Decision 4: buffer chapter 注入方式

**选择**: 当章节类型为"缓冲章"时，调用 ThemeAgent.get_buffer_chapter_template(outline) 覆盖默认模板。

**理由**:
- 缓冲章是特殊的章节类型，需要题材专属的节奏和场景描写
- 模板方法模式在 ThemeAgent 中已定义，调用简单

### Decision 5: 上层情节追溯方式

**选择**: 在 `_retrieve_relevant_context()` 中新增 `_get_macro_context(chapter)` 方法，通过 `StoryNodeRepository` 追溯 chapter → Act → Volume → Part 的祖先链，取出各层 `description`。

**理由**:
- `StoryNode.parent_id` 字段已支持层级追溯，实现简单
- 上层情节设定是只读上下文，不修改 story_nodes
- 注入位置在 `_build_beat_sheet_prompt()` 之前，确保 prompt 构建时可用

**实现细节**:
```python
def _get_macro_context(self, chapter_node, repo):
    # 向上追溯三层：chapter → act → volume → part
    ancestors = {"act": None, "volume": None, "part": None}
    current = repo.get_by_id(chapter_node.parent_id)
    if current and current.node_type == NodeType.ACT:
        ancestors["act"] = current
        volume = repo.get_by_id(current.parent_id)
        if volume and volume.node_type == NodeType.VOLUME:
            ancestors["volume"] = volume
            part = repo.get_by_id(volume.parent_id)
            if part and part.node_type == NodeType.PART:
                ancestors["part"] = part
    return ancestors
```

## Risks / Trade-offs

[Risk] ThemeAgent 加载开销 → Mitigation: ThemeAgentRegistry 是单例，get() 操作 O(1)，Agent 实例已缓存，无额外加载开销

[Risk] 题材专属 beat templates 不匹配关键词导致 fallback 过多 → Mitigation: XuanhuanThemeAgent 和 HistoryThemeAgent 的 beat templates keywords 覆盖常见场景词（修炼、突破、朝堂、战争等），覆盖率预期 >80%

[Risk] LLM prompt 过长导致质量下降 → Mitigation: ThemeDirectives 拼接时按需裁剪，控制在 500 tokens 以内；使用摘要而非完整内容

[Risk] 破坏现有 urban (都市) 小说规划流程 → Mitigation: 明确 Non-Goals，不对 dushi_agent 做任何修改；测试时覆盖 genre="" 和 genre="xuanhuan"/"history" 三种情况

## Open Questions

1. ContinuousPlanningService 的 outline 生成 prompt 模板在哪个文件？需要确认如何注入 ThemeDirectives
2. BeatSheetService 中 vector_store 和 bible_service 已注入，是否需要额外依赖 ThemeAgentRegistry？
3. 题材专属的字数分配策略（不同题材每 beat 字数不同）是否需要在本次实现？
