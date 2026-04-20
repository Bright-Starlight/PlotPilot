## Why

`_calculate_chapter_distribution` 和 `_build_precise_macro_prompt` 的 pacing_guide 使用**题材无关的统一比例**（黄金分割：25/50/25 或均匀分配），导致：

1. **玄幻小说**：5部倒V形才是正确节奏，但被压成中间两部几乎等长，中段爽感完全撑不起来
2. **历史小说**：正确节奏是 25/50/25（25%起源/50%深渊/25%决战），中间部承担几乎所有重量，但 4 部以上全部均匀化
3. **都市小说**：正确节奏是波浪起伏（15/20/25/20/20%），但被压成单调递减
4. **pacing_guide 标签单调**：只有"起源/深渊/决战"三种标签，6部结构也用同一套标签

结果：1000 章超长篇的结构规划，L LM 收到的 pacing_guide 描述完全不符合该题材的正确节奏。

## What Changes

- 修改 `_calculate_chapter_distribution` 支持 `genre` 参数，按题材返回不同比例曲线
- 修改 `_build_precise_macro_prompt` 的 pacing_guide 注入**题材叙事特点描述**
- 新增 `pacing_guide` 动态生成逻辑，每部使用该题材特有的叙事阶段标签

## Capabilities

### New Capabilities

- `genre-specific-distribution`: 根据题材类型返回该题材特有的章节比例曲线
- `genre-specific-pacing-guide`: pacing_guide 注入该题材的叙事节奏特点描述

### Modified Capabilities

- `_calculate_chapter_distribution`: 增加 `genre` 参数，按题材返回不同比例
- `_build_precise_macro_prompt`: pacing_guide 根据 genre 动态生成，使用题材特有标签

## Impact

- `application/blueprint/services/continuous_planning_service.py` — `_calculate_chapter_distribution` 和 `_build_precise_macro_prompt`
