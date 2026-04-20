## Why

玄幻和历史小说的情节规划与都市小说有本质区别：玄幻需要修仙体系/境界/宗门纷争的专项支持，历史需要朝堂权谋/军事征伐/时代背景的专项支持。当前系统虽有ThemeAgent框架，但情节规划流程（BeatSheetService、ContinuousPlanningService）未根据小说类型选用专属模板，导致生成的节拍表和大纲缺乏题材特色。本次迭代专注玄幻和历史两类，暂不考虑都市类型。

## What Changes

1. **题材感知的情节规划**：BeatSheetService 和 ContinuousPlanningService 根据 Novel.genre 加载对应 ThemeAgent，用专属 beat templates 生成章节大纲
2. **题材专属节拍放大**：玄幻Agent的"修炼/突破/以弱胜强"模板、历史Agent的"朝堂博弈/军事征伐"模板直接参与章节规划
3. **题材感知字数分配**：不同题材的每章字数配置、每个 beat 的字数分配根据题材特性调整
4. **朝堂/宗门专业场景支持**：历史小说的朝堂廷议场景、玄幻小说的秘境宗门场景的专属节拍模板

## Capabilities

### New Capabilities

- `genre-aware-beat-sheet`: 根据小说题材（genre）自动选用对应ThemeAgent的beat templates生成章节节拍表。玄幻题材使用"修炼突破""以弱胜强""宗门大比"等模板；历史题材使用"朝堂交锋""军事征伐""权谋博弈"等模板。
- `genre-aware-outline-generation`: 在生成章节大纲（outline）时，ContinuousPlanningService 调用 ThemeAgent 获取题材专属的上下文指令（world_rules、atmosphere、taboos、tropos），注入 LLM prompt。
- `genre-specific-buffer-chapter`: 题材专属的缓冲章模板。玄幻用"闭关悟道/炼丹采药"套路，历史用"庙堂之余/军旅日常"套路，替代通用缓冲章。
- `macro-context-injection`: **章节规划时注入上层情节设计**。BeatSheetService 在生成节拍表前，从 story_nodes 表追溯当前章节所属的 Act → Volume → Part 节点，取出各层的 `description`/`outline` 拼入 LLM prompt，确保章节设计不偏离宏观设定。

### Modified Capabilities

- `beat-sheet-generation`: 将现有的通用 beat sheet 生成流程改造为题材感知流程，在生成节拍表前根据 novel.genre 加载对应 ThemeAgent，合并通用 beat templates 与题材专属 templates。
- `continuous-planning`: 将现有的规划 prompt 改造为支持注入题材专属上下文指令，在宏观规划和章节规划阶段均应用题材特性约束。

## Impact

- 修改 `application/blueprint/services/beat_sheet_service.py` — 添加题材感知逻辑 + 上层情节追溯（Act→Volume→Part）
- 修改 `application/blueprint/services/continuous_planning_service.py` — 注入 ThemeAgent 上下文指令
- 修改 `application/blueprint/services/story_structure_service.py` — 规划阶段应用题材特性
- `domain.novel.entities.novel` — genre 字段已存在，无需变更
- `ThemeAgent` 框架已存在，xuanhuan_agent 和 history_agent 已实现 beat templates
- `StoryNodeRepository` — 可能需要新增 `get_ancestors()` 方法用于向上追溯
