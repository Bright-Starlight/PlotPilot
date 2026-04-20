## Why

现有结构规划提示词使用通用风格，无法满足网络小说（历史/玄幻）的差异化需求。历史小说强调考据感和权谋逻辑，玄幻小说强调修炼体系和爽感节奏。需要根据类型组合选择专业化提示词。

## What Changes

- 新增**历史小说结构规划提示词**：支持后宫/职场/宫斗/穿越/轻松等多种子类型自适应
- 新增**玄幻小说结构规划提示词**：支持凡人流/系统流/无敌流/无限流等子类型自适应
- 新增**历史+玄幻混合提示词**：融合两者特点
- 重构现有规划提示词，支持类型+子类型参数注入
- 新增**前端类型选择器**：小说创建时选择类型和子类型
- 建立提示词选择逻辑：根据小说类型组合自动选用对应提示词模板

## Capabilities

### New Capabilities

- `genre-specific-planning`: 根据小说类型（历史/玄幻/混合）选择差异化结构规划提示词
- `historical-planning-template`: 历史小说专用规划提示词（支持后宫/职场/权谋等子类型自适应）
- `xuanhuan-planning-template`: 玄幻小说专用规划提示词（支持凡人流/系统流/无敌流等子类型自适应）
- `hybrid-planning-template`: 历史+玄幻混合模式提示词
- `genre-selector-ui`: 前端类型/子类型选择器组件

### Modified Capabilities

- `planning-prompts`: 现有规划提示词增加类型参数支持，从通用改为可配置

## Impact

- `infrastructure/ai/prompts/prompts_defaults.json` — 新增提示词模板
- `application/blueprint/services/continuous_planning_service.py` — 类型参数注入逻辑
- `application/blueprint/services/story_structure_service.py` — 提示词选择逻辑
- `frontend/src/views/Home.vue` — 新增类型/子类型选择器
- `frontend/src/components/workbench/MacroPlanModal.vue` — 展示类型信息
