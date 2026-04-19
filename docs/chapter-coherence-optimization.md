# 章节连贯性优化方案

> 基于《大明改命人》第六幕（第26-30章）连贯性分析
> 
> 分析日期：2026-04-19
> 分析对象：novel-1776499481673

## 📋 目录

- [问题诊断](#问题诊断)
- [优化方案](#优化方案)
- [LLM验证方案](#llm验证方案)
- [实施指南](#实施指南)

---

## 问题诊断

### 第六幕章节状态

| 章节 | 标题 | 字数 | 大纲执行度 | 状态 |
|------|------|------|-----------|------|
| 26 | 密报惊变 | 440字 | 100% ✅ | 场景完整但过于简略 |
| 27 | 南行前夕 | 908字 | 100% ✅ | 场景完整但过于简略 |
| 28 | 土木堡残影 | 932字 | 100% ✅ | 场景完整但过于简略 |
| 29 | 海禁迷渊 | 1016字 | 100% ✅ | 场景完整但过于简略 |
| 30 | 追踪者降临 | 686字 | 70% ⚠️ | 缺少最后一个场景 |

**核心发现：**
- 大纲执行度高（平均94%）
- 字数完成度低（平均21%）
- 所有关键场景都有呈现，但缺乏充分展开

---

## 五大类连贯性问题

### 🔴 优先级1：章节间过渡缺失

**问题描述：**
章节之间缺少自然过渡，导致阅读体验断裂。

**具体表现：**

1. **第27→28章**
   - 第27章结尾：沈墨白问"她是谁？"
   - 第28章开头：直接跳到环境描写
   - **缺失**：顾玄音和郑奉安为什么不回答？

2. **第28→29章**
   - 第28章结尾：神秘存在说"该叫你土木？"
   - 第29章开头：直接描写手攥紧的动作
   - **缺失**：沈墨白对"土木"身份质疑的反应

3. **第29→30章**
   - 第29章结尾：女鬼说"而我——"（中断）
   - 第30章开头：直接跳到烙印反应
   - **缺失**：女鬼为何中断？话说完了吗？

**影响：**
- 读者困惑：为什么问题没人回答？
- 叙事断裂：像是换了一个场景
- 情感不连续：角色反应缺失

**修复建议：**
每章开头加1-2句过渡，承接上章结尾的问题或动作。

---

### 🟠 优先级2：人物反应链断裂

**问题描述：**
关键人物在重要时刻缺少反应或行动。

**具体表现：**

1. **郑奉安的存在感消失**
   - 第26-27章：有明确反应和台词
   - 第28章：知道"土木"内情，但话说一半
   - 第29-30章：变成背景板，只有生理反应（咳嗽、脸色惨白）
   - **问题**：他的诅咒在加重，但没有利用这个设定推动剧情

2. **顾玄音的反应不连贯**
   - 第29-30章：重复相同的台词和动作（"她不是土木，你是——"）
   - **问题**：她知道多少真相？她的立场是什么？不清楚

3. **沈墨白的被动**
   - 第29章：几乎没有主动反应，只是被动承受
   - **问题**：作为主角，缺少内心挣扎和主动思考

**影响：**
- 人物扁平化
- 剧情推进依赖单一角色（女鬼朱璃）
- 缺少多角度的情感张力

**修复建议：**
- 让郑奉安在关键时刻发挥作用（诅咒反噬、透露信息）
- 明确顾玄音的知情程度和情感立场
- 增加沈墨白的主动反应和内心戏

---

### 🟡 优先级3：信息释放节奏问题

**问题描述：**
悬念反复提出但解答不足，读者疲劳。

**具体表现：**

1. **"她是谁"被反复提问**
   - 第27章：问"她是谁？"
   - 第28章：答了一半（女医官身份）
   - 第29章：又提出新问题（"不该救的人"）
   - 第30章：又答一半（"她是我妹妹"）
   - **问题**：每次只给一点信息，像是刻意拖延

2. **身份关系混乱**
   - 沈墨白 = 女医官转世？
   - 沈墨白 = "土木"？
   - "土木" = 被女医官救的人？
   - 女鬼 = 朱璃 = 土木堡公主？
   - 顾玄音 = 朱璃的妹妹 = 土木堡公主？
   - "不该救的人" = 顾玄音？
   - **问题**：7-8个身份关系交叉出现，没有明确梳理

**影响：**
- 读者需要自己理清关系
- 信息过载导致困惑
- 悬念保留过度，失去吸引力

**修复建议：**
- 调整信息释放节奏：每章给出完整的信息增量
- 在第30章加沈墨白内心独白，梳理身份关系
- 避免"她是谁"被反复提问

---

### 🟢 优先级4：场景空间连续性

**问题描述：**
场景空间感模糊，人物位置不清晰。

**具体表现：**

1. **地点模糊**
   - 五章都在"残魂关废墟"
   - 但具体在哪里？裂缝在哪？
   - 读者无法建立空间画面

2. **人物站位不明**
   - 沈墨白、顾玄音、郑奉安的相对位置？
   - 女鬼从哪里出来？
   - 三人距离多远？

3. **时间流逝不清**
   - 五章事件是连续发生的吗？
   - 中间有时间间隔吗？
   - 从第26章到第30章，过了多久？

**影响：**
- 缺少画面感
- 动作描写不够具体
- 读者难以想象场景

**修复建议：**
- 每章开头简单交代空间位置
- 描述人物相对站位
- 标注时间流逝（"片刻后"、"就在这时"）

---

### 🔵 优先级5：情感张力断裂

**问题描述：**
人物情感转变缺乏过渡，张力不连续。

**具体表现：**

1. **沈墨白的情感跳跃**
   - 第26章：痛苦、悔恨（"三百年的重量"）
   - 第27章：突然镇定、质问（"三百年前那道裂缝，不是意外"）
   - **问题**：情感转变太快，缺乏过渡

2. **顾玄音的立场模糊**
   - 她对沈墨白是什么感情？
   - 她知道自己是"不该救的人"吗？
   - 她对朱璃是什么态度？
   - **问题**：情感立场不清晰

3. **朱璃的情感单一**
   - 只有怨恨和控诉
   - 缺少怨恨与眷恋交织的复杂情感
   - **问题**：人物情感层次不够丰富

**影响：**
- 情感张力不足
- 人物情感不够立体
- 读者共情困难

**修复建议：**
- 补充沈墨白情感转变的过渡
- 展现顾玄音的内心挣扎
- 深化朱璃的复杂情感

---

## 优化方案

### 方案1：增强章节接缝信息提取 ⭐⭐⭐⭐⭐

**目标：** 解决80%的过渡缺失问题

**修改文件：** `application/engine/services/autopilot_daemon.py`

**修改位置：** `_derive_seam_snapshot_from_content` 方法（1293行）

**当前问题：**
```python
# 只取最后2段，最多160字符
tail_paragraphs = paragraphs[-2:] if paragraphs else []
ending_state = "\n".join(tail_paragraphs)[-160:].strip()

# 只取最后一个问句
question_candidates = re.findall(r"[^。！？!?]{4,40}[？?]", content or "")
if question_candidates:
    carry_over_question = question_candidates[-1].strip()
```

**优化后：**
```python
# 取最后3段，最多300字符
tail_paragraphs = paragraphs[-3:] if paragraphs else []
ending_state = "\n".join(tail_paragraphs)[-300:].strip()

# 检测未完成的话（以"——"、"……"、"..."结尾）
unfinished_speech = ""
if tail_paragraphs:
    last_para = tail_paragraphs[-1]
    if re.search(r'["""][^""]*[——…\.]{2,}["""]?\s*$', last_para):
        match = re.search(r'(["""][^""]*[——…\.]{2,}["""]?)\s*$', last_para)
        if match:
            unfinished_speech = match.group(1)

# 提取最后2个问句，不只是最后1个
question_candidates = re.findall(r"[^。！？!?]{4,40}[？?]", content or "")
carry_over_question = "\n".join(question_candidates[-2:]) if len(question_candidates) >= 2 else (question_candidates[-1] if question_candidates else "")

# 如果有未完成的话，加入到 next_opening_hint
next_opening_hint = ""
if unfinished_speech:
    next_opening_hint = f"承接未完成的话：{unfinished_speech}"

return {
    "ending_state": ending_state,
    "ending_emotion": ending_emotion,
    "carry_over_question": carry_over_question,
    "next_opening_hint": next_opening_hint,
    "unfinished_speech": unfinished_speech,  # 新增字段
}
```

**效果：**
- 捕获未完成的对话（如"而我——"）
- 捕获多个悬念问题
- 提供更完整的接缝信息

---

### 方案2：融合生成提示词优化 ⭐⭐⭐⭐

**目标：** 直接影响正文生成质量

**修改文件：** `application/core/services/chapter_fusion_service.py`

**修改位置：** `_build_fusion_prompt` 方法（571行）

**当前问题：**
- 提示词中没有"承接上章"的明确指令
- 只有"现有正文"，没有"上一章结尾"
- AI不知道需要回应未完成的话

**优化后：**
在 `user_prompt` 中加入：

```python
user_prompt = (
    "任务代号:fusion_generation_v1\n\n"
    f"章节标题:{chapter_title or '未命名章节'}\n"
    f"目标字数:{target_words}\n"
    f"悬念预算:主悬念 {int(suspense_budget.get('primary') or 0)},支悬念 {int(suspense_budget.get('secondary') or 0)}\n"
    f"预期终态:{expected_end_state or {}}\n\n"
    
    # ✅ 新增：上一章接缝信息
    f"【承接约束】\n"
    f"上一章结尾状态：{previous_chapter_ending_state}\n"
    f"上一章未完成的话：{previous_unfinished_speech}\n"
    f"必须回应的问题：{previous_carry_over_question}\n"
    f"要求：本章开头必须直接承接以上内容，不得跳到新场景或新时间。\n\n"
    
    f"章节大纲:\n{chapter_outline or '无'}\n\n"
    # ... 其余保持不变
)
```

**需要传入的参数：**
- `previous_chapter_ending_state`
- `previous_unfinished_speech`
- `previous_carry_over_question`

这些参数从 `knowledge_repository` 或上一章内容中提取。

**效果：**
- AI明确知道需要承接什么
- 减少过渡缺失问题
- 提高章节连贯性

---

### 方案3：节拍生成时加入过渡节拍 ⭐⭐⭐

**目标：** 从源头解决过渡问题

**修改文件：** `application/engine/services/context_builder.py`

**修改位置：** 节拍放大器部分

**当前问题：**
- 节拍直接从大纲第一个场景开始
- 没有"承接上章"的过渡节拍

**优化后：**
```python
def amplify_beats(self, outline: str, previous_chapter_seam: Dict[str, str]) -> List[Beat]:
    """将大纲拆分为节拍，并在开头加入过渡节拍"""
    beats = []
    
    # ✅ 如果上一章有未完成的话或悬念，加入过渡节拍
    if previous_chapter_seam.get("unfinished_speech") or previous_chapter_seam.get("carry_over_question"):
        beats.append(Beat(
            description=f"承接上一章：{previous_chapter_seam.get('unfinished_speech', '')} {previous_chapter_seam.get('carry_over_question', '')}",
            target_words=200,
            focus="dialogue"  # 聚焦对话，完成未完成的话
        ))
    
    # 然后拆分正常的大纲节拍
    # ... 原有逻辑
    
    return beats
```

**效果：**
- 自动生成过渡节拍
- 确保每章开头都有承接
- 减少人工干预

---

### 方案4：大纲重写提示词优化 ⭐⭐⭐

**目标：** 预防性措施，减少后续修复成本

**修改文件：** `application/engine/services/autopilot_daemon.py`

**修改位置：** `_build_next_chapter_outline_replan_prompt` 方法

**优化后：**
在 `system` 提示词中强调：

```python
system = """你是长篇小说续写规划编辑。你的任务是只重写"下一章大纲"，让它严格承接上一章已写成的剧情事实。

必须遵守：
1. 以上一章已发生的事实为最高优先级，不得推翻。
2. 只重写下一章相关信息，不要重写正文，不要解释原因。
3. 开头必须直接承接上一章结尾，特别注意：
   - 如果上一章有未完成的对话（以"——"或"……"结尾），下一章必须先完成这句话
   - 如果上一章有未回答的问题，下一章必须先回答
   - 不得跳到"次日/清晨/突然收到新线索"式新开局，除非上一章结尾本身明确切到了那里
4. 尽量保留原下一章大纲里仍然兼容的主线目标，但可以调整入口场景、推进顺序和信息揭露时机。
...
"""
```

在 `user` 提示词中加入：

```python
user = f"""上一章：第 {current_chapter_number} 章
上一章原大纲：
{current_outline}

原章节标题：
{next_chapter_node.title}

上一章接缝信息：
- 章末状态：{seam.get("ending_state", "") or "无"}
- 章末情绪：{seam.get("ending_emotion", "") or "无"}
- 未完成的话：{seam.get("unfinished_speech", "") or "无"}  # ✅ 新增
- 必须回应：{seam.get("carry_over_question", "") or "无"}
- 开场提示：{seam.get("next_opening_hint", "") or "无"}
...
"""
```

**效果：**
- 大纲重写时考虑接缝信息
- 减少后续正文生成的连贯性问题

---

## LLM验证方案

### 为什么需要LLM验证？

**代码判断 vs LLM验证对比：**

| 维度 | 代码判断 | LLM验证 |
|------|---------|---------|
| **准确性** | 60-70% | 85-95% |
| **误报率** | 高（30-40%） | 低（5-10%） |
| **成本** | 免费 | 需要API调用 |
| **速度** | 极快（毫秒级） | 较慢（秒级） |
| **可解释性** | 差 | 好（有具体建议） |
| **维护成本** | 高（需要不断调整规则） | 低（提示词调整） |

**推荐方案：混合验证**
- 代码快速预筛选（排除明显正常的）
- LLM精确验证（只对可疑的进行）
- 兼顾速度和准确性

---

### 验证器1：章节连贯性验证

**新增文件：** `application/core/services/chapter_coherence_validator.py`

**功能：** 验证当前章节是否连贯承接上一章

**检查项：**
1. 场景转换是否自然（时间、地点、人物）
2. 未完成的对话是否得到延续
3. 未回答的问题是否得到回应
4. 关键人物是否有合理反应
5. 情绪张力是否连续

**输出格式：**
```json
{
  "is_coherent": true/false,
  "issues": [
    {
      "type": "missing_transition|unfinished_dialogue|missing_reaction|...",
      "severity": "critical|high|medium|low",
      "description": "具体问题描述"
    }
  ],
  "suggestions": ["修复建议1", "修复建议2"]
}
```

**使用场景：**
- 融合生成后自动调用
- 发现严重问题时触发重试或人工审核

---

### 验证器2：人物反应完整性验证

**新增文件：** `application/core/services/character_reaction_validator.py`

**功能：** 验证关键人物对关键事件是否有合理反应

**合理反应包括：**
1. 语言反应（台词、对话）
2. 动作反应（肢体动作、表情）
3. 心理反应（内心独白、情绪变化）
4. 生理反应（呼吸、心跳、冷汗等）

**输出格式：**
```json
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
```

**使用场景：**
- 检测郑奉安、顾玄音等关键人物是否失声
- 确保主角有足够的主动反应

---

### 验证器3：悬念解答验证

**新增文件：** `application/core/services/suspense_resolution_validator.py`

**功能：** 验证上一章的悬念是否得到合理处理

**合理处理包括：**
1. 直接解答（给出答案）
2. 部分解答（给出线索）
3. 合理延续（有意保留，但有新进展）
4. 转移焦点（用更大悬念覆盖）

**不合理处理：**
1. 完全忽略（没有任何提及）
2. 突兀跳过（没有过渡就换话题）

**输出格式：**
```json
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
```

**使用场景：**
- 检测"她是谁"等问题是否被反复提出但不解答
- 确保信息释放节奏合理

---

## 实施指南

### 实施优先级

| 优先级 | 方案 | 预期效果 | 实施难度 | 预计时间 |
|--------|------|---------|---------|---------|
| ⭐⭐⭐⭐⭐ | 方案1：增强接缝信息提取 | 解决80%过渡问题 | 低 | 2小时 |
| ⭐⭐⭐⭐ | 方案2：融合生成提示词优化 | 提高生成质量 | 中 | 4小时 |
| ⭐⭐⭐ | 方案3：节拍生成优化 | 从源头解决 | 中 | 6小时 |
| ⭐⭐⭐ | 方案4：大纲重写优化 | 预防性措施 | 低 | 2小时 |
| ⭐⭐⭐⭐ | LLM验证器 | 质量保障 | 高 | 8小时 |

### 实施步骤

**第一阶段（立即实施）：**
1. 实施方案1：增强接缝信息提取
2. 测试第26-30章，验证效果
3. 如果效果显著，继续下一阶段

**第二阶段（短期实施）：**
1. 实施方案2：融合生成提示词优化
2. 实施方案4：大纲重写优化
3. 测试新生成的章节

**第三阶段（中期实施）：**
1. 实施方案3：节拍生成优化
2. 实施LLM验证器（连贯性验证）
3. 集成到自动化流程

**第四阶段（长期优化）：**
1. 实施其他LLM验证器（人物反应、悬念解答）
2. 建立质量监控仪表板
3. 持续优化提示词

### 测试方案

**测试用例：**
使用第26-30章作为测试用例，对比优化前后的效果。

**评估指标：**
1. 过渡缺失次数（目标：从3次降到0次）
2. 人物反应完整性（目标：从68分提升到80分）
3. 悬念处理合理性（目标：从55分提升到70分）
4. 整体连贯性评分（目标：从72分提升到85分）

**验收标准：**
- 章节间过渡自然，无突兀跳跃
- 关键人物都有合理反应
- 悬念得到合理处理（解答或延续）
- 整体阅读体验流畅

---

## 附录

### 附录A：第六幕连贯性问题清单

详见前文"五大类连贯性问题"章节。

### 附录B：代码修改清单

1. `application/engine/services/autopilot_daemon.py`
   - `_derive_seam_snapshot_from_content` 方法（1293行）
   - `_build_next_chapter_outline_replan_prompt` 方法（约1350行）

2. `application/core/services/chapter_fusion_service.py`
   - `_build_fusion_prompt` 方法（571行）

3. `application/engine/services/context_builder.py`
   - 节拍放大器部分（需要定位具体位置）

4. 新增文件：
   - `application/core/services/chapter_coherence_validator.py`
   - `application/core/services/character_reaction_validator.py`
   - `application/core/services/suspense_resolution_validator.py`

### 附录C：提示词模板

详见各方案的具体代码示例。

---

**文档版本：** v1.0  
**最后更新：** 2026-04-19  
**维护者：** PlotPilot开发团队
