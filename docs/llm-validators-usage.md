# LLM 验证器使用指南

## 概述

LLM 验证器已成功实现，包含三个核心验证器：

1. **ChapterCoherenceValidator** - 章节连贯性验证
2. **CharacterReactionValidator** - 人物反应验证
3. **SuspenseResolutionValidator** - 悬念解答验证

## 文件结构

```
application/core/services/validators/
├── __init__.py                          # 导出所有验证器
├── base_validator.py                    # 基类
├── chapter_coherence_validator.py       # 连贯性验证器
├── character_reaction_validator.py      # 人物反应验证器
└── suspense_resolution_validator.py     # 悬念解答验证器
```

## 集成到 ChapterFusionService

验证器已集成到 `ChapterFusionService` 中，可以在融合生成后自动调用。

### 初始化

```python
from application.core.services.validators import (
    ChapterCoherenceValidator,
    CharacterReactionValidator,
    SuspenseResolutionValidator,
)

# 创建验证器实例
coherence_validator = ChapterCoherenceValidator(llm_service)
reaction_validator = CharacterReactionValidator(llm_service)
suspense_validator = SuspenseResolutionValidator(llm_service)

# 初始化 ChapterFusionService
fusion_service = ChapterFusionService(
    chapter_repository=chapter_repository,
    beat_sheet_repository=beat_sheet_repository,
    fusion_repository=fusion_repository,
    state_lock_repository=state_lock_repository,
    llm_service=llm_service,
    validation_service=validation_service,
    coherence_validator=coherence_validator,
    reaction_validator=reaction_validator,
    suspense_validator=suspense_validator,
)
```

### 使用验证器

验证器可以在融合生成后自动调用：

```python
# 在 _compose_fusion 方法中，融合生成完成后
validation_results = await self._validate_fusion_draft(
    fusion_result=result,
    previous_chapter_content=previous_chapter_content,
    previous_chapter_seam=previous_chapter_seam,
    key_characters=["沈墨白", "顾玄音", "郑奉安"],
    key_events=["女鬼朱璃现身", "朱璃控诉沈墨白"],
    previous_suspense=["她是谁？", "不该救的人是谁？"],
)

# 检查是否有严重问题
if self._has_critical_issues(validation_results):
    logger.warning("融合草稿存在严重问题")
    # 可以触发重试或人工审核
```

## 验证器详细说明

### 1. ChapterCoherenceValidator（章节连贯性验证）

**功能：** 验证当前章节是否连贯承接上一章

**检查项：**
- 场景转换是否自然（时间、地点、人物）
- 未完成的对话是否得到延续
- 未回答的问题是否得到回应
- 关键人物是否有合理反应
- 情绪张力是否连续

**使用示例：**

```python
validator = ChapterCoherenceValidator(llm_service)

result = await validator.validate(
    previous_chapter_content=chapter_26_content,
    current_chapter_content=chapter_27_content,
    previous_chapter_seam={
        "ending_state": "沈墨白闭目承受命簿重压...",
        "unfinished_speech": "而我——",
        "carry_over_question": "她是谁？",
        "ending_emotion": "沉重、悔恨",
    },
)

if not result.is_valid:
    for issue in result.issues:
        if issue.severity in ["critical", "high"]:
            print(f"严重问题: {issue.description}")
```

### 2. CharacterReactionValidator（人物反应验证）

**功能：** 验证关键人物对关键事件是否有合理反应

**合理反应包括：**
- 语言反应（台词、对话）
- 动作反应（肢体动作、表情）
- 心理反应（内心独白、情绪变化）
- 生理反应（呼吸、心跳、冷汗等）

**使用示例：**

```python
validator = CharacterReactionValidator(llm_service)

result = await validator.validate(
    chapter_content=chapter_29_content,
    key_characters=["沈墨白", "顾玄音", "郑奉安", "朱璃"],
    key_events=[
        "女鬼朱璃现身",
        "朱璃控诉沈墨白抛弃她",
        "朱璃揭示自己是土木堡公主",
    ],
)

if not result.is_valid:
    for issue in result.issues:
        print(f"人物反应缺失: {issue.description}")
```

### 3. SuspenseResolutionValidator（悬念解答验证）

**功能：** 验证上一章的悬念是否得到合理处理

**合理处理包括：**
- 直接解答（给出答案）
- 部分解答（给出线索）
- 合理延续（有意保留，但有新进展）
- 转移焦点（用更大悬念覆盖）

**使用示例：**

```python
validator = SuspenseResolutionValidator(llm_service)

result = await validator.validate(
    previous_suspense=[
        "她是谁？",
        "女鬼说'而我——'后中断",
        "不该救的人是谁？",
    ],
    current_chapter_content=chapter_30_content,
)

if not result.is_valid:
    for issue in result.issues:
        print(f"悬念未处理: {issue.description}")
```

## 验证结果结构

```python
@dataclass
class ValidationIssue:
    type: str          # 问题类型
    severity: str      # 严重程度：critical|high|medium|low
    description: str   # 问题描述
    location: str      # 问题位置（可选）

@dataclass
class ValidationResult:
    is_valid: bool                    # 是否通过验证
    issues: List[ValidationIssue]     # 问题列表
    suggestions: List[str]            # 修复建议
    metadata: Dict[str, Any]          # 额外元数据
```

## 严重程度定义

| 级别 | 含义 | 建议 |
|------|------|------|
| **critical** | 严重破坏阅读体验，必须修复 | 阻止发布，必须修复 |
| **high** | 明显的问题，应该修复 | 强烈建议修复 |
| **medium** | 可以改进的地方 | 建议修复 |
| **low** | 小瑕疵，可选修复 | 可选修复 |

## 配置选项

验证器支持配置：

```python
validator = ChapterCoherenceValidator(
    llm_service,
    config={
        "max_tokens": 800,      # LLM 最大输出 token 数
        "temperature": 0.3,     # 温度参数（0-1，越低越确定）
    }
)
```

## 错误处理

验证器在 LLM 调用失败时会默认通过验证，避免阻塞正常流程：

```python
try:
    result = await validator.validate(...)
except Exception as e:
    # 验证失败时返回默认通过的结果
    return ValidationResult(
        is_valid=True,
        issues=[],
        suggestions=[],
        metadata={"error": str(e)},
    )
```

## 测试

运行测试：

```bash
python -m pytest tests/unit/application/services/test_llm_validators.py -v
```

所有测试已通过：
- ✅ test_coherence_validator_success
- ✅ test_coherence_validator_with_issues
- ✅ test_character_reaction_validator_success
- ✅ test_character_reaction_validator_with_missing_reactions
- ✅ test_suspense_validator_no_suspense
- ✅ test_suspense_validator_with_unhandled_suspense
- ✅ test_validator_handles_llm_error

## 下一步

根据 `docs/chapter-coherence-optimization.md` 的实施计划：

**已完成：**
- ✅ 方案1：增强章节接缝信息提取
- ✅ 方案2：融合生成提示词优化
- ✅ 方案3：节拍生成时加入过渡节拍
- ✅ 方案4：大纲重写提示词优化
- ✅ LLM验证器实现

**待完成：**
- 在实际章节生成中验证效果
- 收集用户反馈
- 根据反馈优化提示词
- 建立质量监控仪表板

## 参考文档

- `docs/chapter-coherence-optimization.md` - 章节连贯性优化方案
- `docs/implementation-summary.md` - 实施总结
- `docs/llm-validation-implementation.md` - LLM验证器实现指南
