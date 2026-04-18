## Why

当前章节融合能力已经上线，但它依赖的 `StateLocks` 仍然缺少正式的生成与版本化流程，导致“先融合、后补边界”的顺序倒置。继续沿用当前链路会让 `FusionDraft` 在缺少稳定事实边界的情况下产出结果，并把本应前置约束的问题推迟到校验或人工修补阶段。

## What Changes

- 新增章节状态锁生成能力：在章节生成前，基于上章终态、`ChapterPlan`、`FactStore` 和 `StoryBible` 自动产出首版 `StateLocks`
- 允许在必要且难以稳定规则化判断的环节引入 LLM，辅助生成锁候选、归并别名或判断模糊终态，但最终仍需产出可版本化的结构化锁结果
- 新增状态锁版本管理与人工微调能力，要求所有后续阶段共享同一 `state_lock_version`
- 新增章节当前状态锁查询与编辑接口，支持修改原因、版本快照与回溯
- 新增章节工作台的 State Locks 展示、编辑与冲突提示界面
- 修改章节融合要求：`FusionDraft` 只能在已有状态锁版本的前提下创建，并且必须记录其消费的锁版本
- 明确与 P0 阻断式校验的衔接：校验阶段必须校验草稿是否违反同一版本状态锁，但完整 P0 规则与守门细节继续由 `add-p0-blocking-validation` 承载
- **BREAKING** 章节融合入口不再允许“缺少状态锁直接融合”的隐式兜底行为

## Capabilities

### New Capabilities
- `chapter-state-locks`: 章节状态锁生成、版本化保存、人工微调、查询展示，以及向后续草稿阶段提供统一事实边界

### Modified Capabilities
- `chapter-fusion`: 融合前必须存在可用状态锁版本，融合任务必须消费并记录同一份锁约束

## Impact

- Affected code: 章节生成预处理、融合任务创建逻辑、章节工作台右栏、锁编辑弹窗、状态冲突提示
- APIs: `POST /api/chapters/{chapterId}/state-locks`、`PATCH /api/state-locks/{stateLockId}`、`GET /api/chapters/{chapterId}/state-locks/current`，以及融合创建接口的前置校验
- Data: 新增 `state_locks`、`state_lock_versions` 表，并要求融合记录显式保存 `state_lock_version`
- Dependencies: 需要读取 `ChapterPlan`、上章终态、`FactStore`、`StoryBible`，并与现有融合能力及进行中的 `add-p0-blocking-validation` change 对齐输入契约
