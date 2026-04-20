## Why

当前章节生成链路已经能产出 `FusionDraft`，但在进入发布态前缺少一层强制一致性校验，导致互斥事实、终态冲突、人物身份漂移等问题只能靠人工发现。随着章节工作台和发布流程逐步成型，需要把这类高风险错误前置为阻断式校验，并为后续自动修补预留入口。

## What Changes

- 新增章节草稿校验能力，支持对 `FusionDraft` 或 `MergedDraft` 发起一致性校验并生成结构化 `ValidationReport`
- 引入三级校验流程：规则检测、状态比对、语义判定，其中 P0 问题默认阻断发布
- 新增校验相关 API，包括发起校验和查询校验报告详情
- 新增校验报告与问题明细持久化模型，支持严重级别、定位片段、处理状态和补丁建议标记
- 在章节工作台增加 Validation 面板，在发布确认弹窗中接入未解决 P0 阻断逻辑
- 新增校验中心页面，支持按章节、严重级别和状态筛选问题
- 为需要语义理解的校验环节预留 LLM 判定与修补建议生成能力

## Capabilities

### New Capabilities
- `chapter-validation`: 对章节草稿执行 P0/P1/P2 一致性校验，生成报告，并将 P0 问题接入发布阻断与修补入口

### Modified Capabilities
- `chapter-fusion`: 发布前工作流需要接入章节校验结果，确保融合草稿在存在未解决 P0 时不能进入发布态

## Impact

- Affected code: 章节工作台、发布流程、章节草稿校验服务、报告查询接口、问题持久化层
- APIs: `POST /api/chapters/{chapterId}/validate`、`GET /api/validation-reports/{reportId}`，以及发布前状态检查
- Data: 新增 `validation_reports`、`validation_issues` 表，可能需要为草稿与章节关联增加查询索引
- Dependencies: 需要接入规则引擎、状态数据读取器，以及可选的 LLM 语义判定与补丁生成组件
