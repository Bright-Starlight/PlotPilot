# LLM验证器实现指南

> 基于章节连贯性优化方案的LLM验证器详细实现
> 
> 文档日期：2026-04-19

## 📋 目录

- [验证器架构](#验证器架构)
- [验证器1：章节连贯性验证](#验证器1章节连贯性验证)
- [验证器2：人物反应验证](#验证器2人物反应验证)
- [验证器3：悬念解答验证](#验证器3悬念解答验证)
- [集成方案](#集成方案)
- [混合验证策略](#混合验证策略)

---

## 验证器架构

### 设计原则

1. **单一职责**：每个验证器只负责一类问题
2. **可组合**：验证器可以独立使用或组合使用
3. **可配置**：验证严格度可调整
4. **可扩展**：易于添加新的验证器

### 通用接口

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class ValidationIssue:
    """验证问题"""
    type: str  # 问题类型
    severity: str  # 严重程度：critical|high|medium|low
    description: str  # 问题描述
    location: str = ""  # 问题位置（可选）

@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool  # 是否通过验证
    issues: List[ValidationIssue]  # 问题列表
    suggestions: List[str]  # 修复建议
    metadata: Dict[str, Any] = None  # 额外元数据

class BaseValidator(ABC):
    """验证器基类"""
    
    def __init__(self, llm_service, config: Dict[str, Any] = None):
        self.llm_service = llm_service
        self.config = config or {}
    
    @abstractmethod
    async def validate(self, **kwargs) -> ValidationResult:
        """执行验证"""
        pass
    
    @abstractmethod
    def _build_prompt(self, **kwargs) -> Prompt:
        """构建验证提示词"""
        pass
    
    async def _call_llm(self, prompt: Prompt) -> Dict[str, Any]:
        """调用LLM"""
        config = GenerationConfig(
            max_tokens=self.config.get("max_tokens", 800),
            temperature=self.config.get("temperature", 0.3),
        )
        result = await self.llm_service.generate(prompt, config)
        return self._parse_llm_response(result)
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取JSON
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return {}
```

---

## 验证器1：章节连贯性验证

### 功能说明

验证当前章节是否连贯承接上一章，检查：
- 场景转换是否自然
- 未完成的对话是否延续
- 未回答的问题是否回应
- 关键人物是否有反应
- 情绪张力是否连续

### 实现代码

**文件：** `application/core/services/chapter_coherence_validator.py`

```python
from typing import Dict, Any, List
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.generation_config import GenerationConfig
from .base_validator import BaseValidator, ValidationResult, ValidationIssue
import logging

logger = logging.getLogger(__name__)

class ChapterCoherenceValidator(BaseValidator):
    """章节连贯性验证器"""
    
    async def validate(
        self,
        previous_chapter_content: str,
        current_chapter_content: str,
        previous_chapter_seam: Dict[str, str],
    ) -> ValidationResult:
        """验证章节连贯性"""
        
        prompt = self._build_prompt(
            previous_chapter_content,
            current_chapter_content,
            previous_chapter_seam,
        )
        
        try:
            result = await self._call_llm(prompt)
            
            issues = [
                ValidationIssue(
                    type=issue.get("type", "unknown"),
                    severity=issue.get("severity", "medium"),
                    description=issue.get("description", ""),
                )
                for issue in result.get("issues", [])
            ]
            
            return ValidationResult(
                is_valid=result.get("is_coherent", False),
                issues=issues,
                suggestions=result.get("suggestions", []),
                metadata={"validator": "coherence"},
            )
        
        except Exception as e:
            logger.error(f"章节连贯性验证失败: {e}")
            return ValidationResult(
                is_valid=True,  # 验证失败时默认通过
                issues=[],
                suggestions=[],
                metadata={"error": str(e)},
            )
    
    def _build_prompt(
        self,
        previous_content: str,
        current_content: str,
        seam: Dict[str, str],
    ) -> Prompt:
        """构建验证提示词"""
        
        system = """你是小说连贯性审查专家。你的任务是检查两章之间的连贯性。

重点检查：
1. 场景转换是否自然（时间、地点、人物）
2. 未完成的对话是否得到延续
3. 未回答的问题是否得到回应
4. 关键人物是否有合理反应
5. 情绪张力是否连续

输出JSON格式：
{
  "is_coherent": true/false,
  "issues": [
    {
      "type": "missing_transition|unfinished_dialogue|missing_reaction|emotion_break|...",
      "severity": "critical|high|medium|low",
      "description": "具体问题描述"
    }
  ],
  "suggestions": ["修复建议1", "修复建议2"]
}

严重程度定义：
- critical: 严重破坏阅读体验，必须修复
- high: 明显的连贯性问题，应该修复
- medium: 可以改进的地方
- low: 小瑕疵，可选修复"""

        # 提取上一章最后3段
        prev_paragraphs = [p.strip() for p in previous_content.split("\n") if p.strip()]
        prev_tail = "\n".join(prev_paragraphs[-3:]) if prev_paragraphs else ""
        
        # 提取当前章开头3段
        curr_paragraphs = [p.strip() for p in current_content.split("\n") if p.strip()]
        curr_head = "\n".join(curr_paragraphs[:3]) if curr_paragraphs else ""
        
        user = f"""上一章结尾（最后3段）：
{prev_tail}

上一章接缝信息：
- 章末状态：{seam.get("ending_state", "无")}
- 未完成的话：{seam.get("unfinished_speech", "无")}
- 必须回应的问题：{seam.get("carry_over_question", "无")}
- 章末情绪：{seam.get("ending_emotion", "无")}

当前章开头（前3段）：
{curr_head}

请检查连贯性并输出JSON。"""

        return Prompt(system=system, user=user)
```

### 使用示例

```python
# 初始化验证器
validator = ChapterCoherenceValidator(llm_service)

# 执行验证
result = await validator.validate(
    previous_chapter_content=chapter_26_content,
    current_chapter_content=chapter_27_content,
    previous_chapter_seam={
        "ending_state": "沈墨白闭目承受命簿重压...",
        "unfinished_speech": "",
        "carry_over_question": "",
        "ending_emotion": "沉重、悔恨",
    },
)

# 处理结果
if not result.is_valid:
    critical_issues = [i for i in result.issues if i.severity == "critical"]
    if critical_issues:
        logger.warning(f"发现{len(critical_issues)}个严重连贯性问题")
        for issue in critical_issues:
            logger.warning(f"  - {issue.description}")
```

---

## 验证器2：人物反应验证

### 功能说明

验证关键人物对关键事件是否有合理反应，包括：
- 语言反应（台词、对话）
- 动作反应（肢体动作、表情）
- 心理反应（内心独白、情绪变化）
- 生理反应（呼吸、心跳、冷汗等）

### 实现代码

**文件：** `application/core/services/character_reaction_validator.py`

```python
from typing import Dict, Any, List
from domain.ai.value_objects.prompt import Prompt
from .base_validator import BaseValidator, ValidationResult, ValidationIssue
import logging

logger = logging.getLogger(__name__)

class CharacterReactionValidator(BaseValidator):
    """人物反应验证器"""
    
    async def validate(
        self,
        chapter_content: str,
        key_characters: List[str],
        key_events: List[str],
    ) -> ValidationResult:
        """验证人物反应完整性"""
        
        prompt = self._build_prompt(
            chapter_content,
            key_characters,
            key_events,
        )
        
        try:
            result = await self._call_llm(prompt)
            
            missing_reactions = result.get("missing_reactions", [])
            issues = [
                ValidationIssue(
                    type="missing_reaction",
                    severity=reaction.get("severity", "medium"),
                    description=f"{reaction.get('character')}对"{reaction.get('event')}"缺少反应：{reaction.get('reason')}",
                )
                for reaction in missing_reactions
            ]
            
            return ValidationResult(
                is_valid=result.get("all_reacted", False),
                issues=issues,
                suggestions=result.get("suggestions", []),
                metadata={"validator": "character_reaction"},
            )
        
        except Exception as e:
            logger.error(f"人物反应验证失败: {e}")
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"error": str(e)},
            )
    
    def _build_prompt(
        self,
        content: str,
        characters: List[str],
        events: List[str],
    ) -> Prompt:
        """构建验证提示词"""
        
        system = """你是小说人物反应审查专家。你的任务是检查关键人物对关键事件是否有合理反应。

合理反应包括：
1. 语言反应（台词、对话）
2. 动作反应（肢体动作、表情）
3. 心理反应（内心独白、情绪变化）
4. 生理反应（呼吸、心跳、冷汗等）

特别注意：
- 在场的关键人物必须有反应
- 反应应该符合人物性格和当前情境
- 不是所有人物都需要对所有事件反应，但重要人物对重要事件必须有反应

输出JSON格式：
{
  "all_reacted": true/false,
  "missing_reactions": [
    {
      "character": "人物名",
      "event": "事件描述",
      "severity": "critical|high|medium",
      "reason": "为什么这个人物应该有反应"
    }
  ],
  "suggestions": ["建议在XX处增加XX的反应", ...]
}

严重程度定义：
- critical: 关键人物对核心事件完全没有反应
- high: 重要人物对重要事件缺少反应
- medium: 次要人物或次要事件的反应缺失"""

        char_list = "、".join(characters)
        event_list = "\n".join(f"- {e}" for e in events)
        
        user = f"""章节正文：
{content}

关键人物：{char_list}

关键事件：
{event_list}

请检查每个关键人物对每个关键事件是否有合理反应，输出JSON。"""

        return Prompt(system=system, user=user)
```

### 使用示例

```python
# 初始化验证器
validator = CharacterReactionValidator(llm_service)

# 执行验证
result = await validator.validate(
    chapter_content=chapter_29_content,
    key_characters=["沈墨白", "顾玄音", "郑奉安", "朱璃"],
    key_events=[
        "女鬼朱璃现身",
        "朱璃控诉沈墨白抛弃她",
        "朱璃揭示自己是土木堡公主",
    ],
)

# 处理结果
if not result.is_valid:
    for issue in result.issues:
        if issue.severity in ["critical", "high"]:
            logger.warning(f"人物反应缺失: {issue.description}")
```

---

## 验证器3：悬念解答验证

### 功能说明

验证上一章的悬念是否得到合理处理：
- 直接解答（给出答案）
- 部分解答（给出线索）
- 合理延续（有意保留，但有新进展）
- 转移焦点（用更大悬念覆盖）

### 实现代码

**文件：** `application/core/services/suspense_resolution_validator.py`

```python
from typing import Dict, Any, List
from domain.ai.value_objects.prompt import Prompt
from .base_validator import BaseValidator, ValidationResult, ValidationIssue
import logging

logger = logging.getLogger(__name__)

class SuspenseResolutionValidator(BaseValidator):
    """悬念解答验证器"""
    
    async def validate(
        self,
        previous_suspense: List[str],
        current_chapter_content: str,
    ) -> ValidationResult:
        """验证悬念解答"""
        
        if not previous_suspense:
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"validator": "suspense_resolution", "note": "无悬念需要验证"},
            )
        
        prompt = self._build_prompt(
            previous_suspense,
            current_chapter_content,
        )
        
        try:
            result = await self._call_llm(prompt)
            
            unhandled = result.get("unhandled_suspense", [])
            issues = [
                ValidationIssue(
                    type=f"suspense_{item.get('status', 'unhandled')}",
                    severity=item.get("severity", "medium"),
                    description=f"悬念"{item.get('suspense')}"未处理：{item.get('reason')}",
                )
                for item in unhandled
            ]
            
            return ValidationResult(
                is_valid=result.get("all_handled", False),
                issues=issues,
                suggestions=result.get("suggestions", []),
                metadata={"validator": "suspense_resolution"},
            )
        
        except Exception as e:
            logger.error(f"悬念解答验证失败: {e}")
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"error": str(e)},
            )
    
    def _build_prompt(
        self,
        suspense_list: List[str],
        content: str,
    ) -> Prompt:
        """构建验证提示词"""
        
        system = """你是小说悬念处理审查专家。你的任务是检查上一章的悬念在本章是否得到合理处理。

合理处理包括：
1. 直接解答（给出答案）
2. 部分解答（给出线索）
3. 合理延续（有意保留，但有新进展）
4. 转移焦点（用更大悬念覆盖）

不合理处理：
1. 完全忽略（没有任何提及）
2. 突兀跳过（没有过渡就换话题）

输出JSON格式：
{
  "all_handled": true/false,
  "unhandled_suspense": [
    {
      "suspense": "悬念内容",
      "status": "ignored|abruptly_skipped",
      "severity": "critical|high|medium",
      "reason": "为什么这个悬念应该被处理"
    }
  ],
  "suggestions": ["建议在XX处回应XX悬念", ...]
}

严重程度定义：
- critical: 核心悬念被完全忽略
- high: 重要悬念被突兀跳过
- medium: 次要悬念处理不够充分"""

        suspense_text = "\n".join(f"- {s}" for s in suspense_list)
        
        user = f"""上一章留下的悬念：
{suspense_text}

本章正文：
{content}

请检查每个悬念是否得到合理处理，输出JSON。"""

        return Prompt(system=system, user=user)
```

### 使用示例

```python
# 初始化验证器
validator = SuspenseResolutionValidator(llm_service)

# 执行验证
result = await validator.validate(
    previous_suspense=[
        "她是谁？",
        "女鬼说'而我——'后中断",
        "不该救的人是谁？",
    ],
    current_chapter_content=chapter_30_content,
)

# 处理结果
if not result.is_valid:
    for issue in result.issues:
        logger.warning(f"悬念未处理: {issue.description}")
```

---

## 集成方案

### 在融合生成后自动调用

**修改文件：** `application/core/services/chapter_fusion_service.py`

```python
class ChapterFusionService:
    
    def __init__(
        self,
        # ... 原有参数
        coherence_validator: Optional[ChapterCoherenceValidator] = None,
        reaction_validator: Optional[CharacterReactionValidator] = None,
        suspense_validator: Optional[SuspenseResolutionValidator] = None,
    ):
        # ... 原有初始化
        self.coherence_validator = coherence_validator
        self.reaction_validator = reaction_validator
        self.suspense_validator = suspense_validator
    
    async def generate_fusion_draft(self, ...):
        # ... 原有融合生成逻辑
        
        fusion_result = await self._call_llm_fusion(...)
        
        # ✅ 新增：自动验证
        validation_results = await self._validate_fusion_draft(
            fusion_result=fusion_result,
            previous_chapter_content=previous_chapter_content,
            previous_chapter_seam=previous_chapter_seam,
            key_characters=key_characters,
            key_events=key_events,
            previous_suspense=previous_suspense,
        )
        
        # 记录验证结果
        fusion_result["validation_results"] = validation_results
        
        # 如果有严重问题，可以选择重试
        if self._has_critical_issues(validation_results):
            logger.warning("融合草稿存在严重问题，考虑重试")
            # 可以触发重试逻辑
        
        return fusion_result
    
    async def _validate_fusion_draft(
        self,
        fusion_result: Dict[str, Any],
        previous_chapter_content: str,
        previous_chapter_seam: Dict[str, str],
        key_characters: List[str],
        key_events: List[str],
        previous_suspense: List[str],
    ) -> Dict[str, ValidationResult]:
        """验证融合草稿"""
        
        results = {}
        
        # 1. 连贯性验证
        if self.coherence_validator and previous_chapter_content:
            results["coherence"] = await self.coherence_validator.validate(
                previous_chapter_content=previous_chapter_content,
                current_chapter_content=fusion_result["text"],
                previous_chapter_seam=previous_chapter_seam,
            )
        
        # 2. 人物反应验证
        if self.reaction_validator and key_characters and key_events:
            results["reaction"] = await self.reaction_validator.validate(
                chapter_content=fusion_result["text"],
                key_characters=key_characters,
                key_events=key_events,
            )
        
        # 3. 悬念解答验证
        if self.suspense_validator and previous_suspense:
            results["suspense"] = await self.suspense_validator.validate(
                previous_suspense=previous_suspense,
                current_chapter_content=fusion_result["text"],
            )
        
        return results
    
    def _has_critical_issues(self, validation_results: Dict[str, ValidationResult]) -> bool:
        """检查是否有严重问题"""
        for result in validation_results.values():
            critical_issues = [
                issue for issue in result.issues
                if issue.severity == "critical"
            ]
            if critical_issues:
                return True
        return False
```

---

## 混合验证策略

### 代码预筛选 + LLM精确验证

**目标：** 90%的正常情况用代码快速通过，10%的可疑情况用LLM精确判断

```python
class HybridValidator:
    """混合验证器：代码预筛选 + LLM精确验证"""
    
    def __init__(self, llm_validator: BaseValidator):
        self.llm_validator = llm_validator
    
    async def validate(self, **kwargs) -> ValidationResult:
        """混合验证"""
        
        # 第一步：代码快速预筛选
        quick_result = self._quick_code_check(**kwargs)
        
        if quick_result["definitely_ok"]:
            # 明显正常，直接通过
            return ValidationResult(
                is_valid=True,
                issues=[],
                suggestions=[],
                metadata={"method": "code_check", "fast_pass": True},
            )
        
        if quick_result["definitely_bad"]:
            # 明显有问题，直接返回
            return ValidationResult(
                is_valid=False,
                issues=quick_result["issues"],
                suggestions=quick_result["suggestions"],
                metadata={"method": "code_check", "fast_fail": True},
            )
        
        # 第二步：LLM精确验证（只对可疑的进行）
        return await self.llm_validator.validate(**kwargs)
    
    def _quick_code_check(self, **kwargs) -> Dict[str, Any]:
        """代码快速预筛选"""
        # 实现简单的规则检查
        # 例如：检查是否有明显的过渡词、人物名出现等
        pass
```

### 成本优化

**预估：**
- 代码预筛选：0成本，<10ms
- LLM验证：约0.001-0.002美元/次，1-3秒

**优化策略：**
- 90%的章节通过代码预筛选（节省90%成本）
- 10%的可疑章节用LLM验证（保证质量）
- 总成本：约原LLM全验证的10%

---

**文档版本：** v1.0  
**最后更新：** 2026-04-19  
**维护者：** PlotPilot开发团队
