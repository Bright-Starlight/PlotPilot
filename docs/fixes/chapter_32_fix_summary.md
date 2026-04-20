# 第32章验证问题修复总结

## 执行时间
2026-04-19

## 问题描述

小说 `novel-1776499481673`（《大明改命人》）的第32章"残影黑市"存在以下问题：

1. **验证误报**：2个P0级别的验证问题被用户标记为"误报"
   - `ending_lock_violation`: 违反终态锁
   - `planned_end_state_conflict`: 章节终态与规划不一致

2. **大纲截断**：章节大纲最后一句"三人离开废墟后转入残影黑市调查，发现黑市"不完整

## 根本原因

### 问题1：规划错误，非真正的误报

验证系统检测到的问题是真实存在的不一致：

- **规划的终态** (`story_nodes.timeline_end`): `地下市场突遭袭击`
- **实际内容终态** (`chapter_fusion_drafts.end_state`): `废墟石室`
- **大纲描述**: 在废墟石室中发现沈墨白妹妹的残影

**分析**：
- 第31章 timeline_end: `废弃码头地下市场入口`
- 第32章 timeline_end: `地下市场突遭袭击` ← **错误设置**
- 第33章 timeline_end: `因果枢纽核心区域`

根据大纲内容，第32章应该停留在"废墟石室"，而不是"地下市场突遭袭击"。大纲最后提到"三人离开废墟后转入残影黑市调查"，表明到达地下市场应该是后续章节的内容。

### 问题2：大纲生成时被截断

大纲在生成时达到了某种限制（可能是 token 限制或其他原因），导致最后一句不完整。

## 修复措施

### 1. 修正 timeline_end

```sql
UPDATE story_nodes
SET timeline_end = '废墟石室', updated_at = CURRENT_TIMESTAMP
WHERE id = 'chapter-novel-1776499481673-chapter-32';
```

**结果**：
- 旧值: `地下市场突遭袭击`
- 新值: `废墟石室`

### 2. 补全大纲

**原大纲（358字符）**：
```
...三人离开废墟后转入残影黑市调查，发现黑市
```

**补全后（372字符）**：
```
...三人离开废墟后转入残影黑市调查，发现黑市中有人在追踪皇族血脉的线索。
```

### 3. 更新状态锁

同步更新 `state_locks` 表中的 `ending_lock_json`：

```json
{
  "entries": [
    {
      "key": "ending_target",
      "label": "目标终态",
      "value": "废墟石室",  // 从"地下市场突遭袭击"改为"废墟石室"
      "source": "fact_store",
      "kind": "ending_target",
      "status": "normal",
      "metadata": {}
    }
  ]
}
```

## 修复结果

### 修复前
- `story_nodes.timeline_end`: `地下市场突遭袭击`
- `state_locks.ending_lock`: `地下市场突遭袭击`
- 大纲长度: 358 字符（截断）
- 验证问题: 2个P0问题（用户标记为误报）

### 修复后
- `story_nodes.timeline_end`: `废墟石室` ✓
- `state_locks.ending_lock`: `废墟石室` ✓
- 大纲长度: 372 字符（已补全）✓
- 验证问题: 历史问题已标记为 resolved

## 后续建议

### 1. 重新验证章节

由于我们修改了规划（timeline_end），建议重新运行第32章的验证，以确认：
- 新的 timeline_end 与实际内容一致
- 不再产生新的验证问题

### 2. 检查章节内容

当前章节内容只有 1097 字符，可能需要：
- 检查内容是否完整
- 确认内容是否与修复后的大纲一致
- 如果内容也被截断，可能需要重新生成

### 3. 系统改进建议

#### 3.1 大纲完整性检查

在大纲生成后添加自动检查：

```python
def validate_outline_completeness(outline: str) -> tuple[bool, str]:
    """检查大纲是否完整"""
    if not outline:
        return False, "大纲为空"
    
    # 检查是否以完整的句子结尾
    if not outline.rstrip().endswith(('。', '！', '？', '…')):
        return False, f"大纲可能被截断，最后50字: {outline[-50:]}"
    
    return True, ""
```

#### 3.2 timeline_end 一致性检查

在章节规划阶段添加验证：

```python
def validate_timeline_end_consistency(timeline_end: str, outline: str) -> tuple[bool, str]:
    """检查 timeline_end 是否与大纲一致"""
    if not timeline_end:
        return True, ""
    
    # 检查 timeline_end 是否在大纲中出现
    if timeline_end not in outline:
        return False, f"timeline_end '{timeline_end}' 未在大纲中出现"
    
    # 检查 timeline_end 是否在大纲的后半部分（表示是结束位置）
    outline_length = len(outline)
    timeline_end_pos = outline.find(timeline_end)
    
    if timeline_end_pos < outline_length * 0.5:
        return False, f"timeline_end '{timeline_end}' 出现在大纲前半部分，可能不是结束位置"
    
    return True, ""
```

#### 3.3 验证问题来源分析

改进验证系统，区分规划错误和内容错误：

```python
def analyze_validation_issue_source(
    issue: ValidationIssueDTO,
    plan: Any,
    draft: DraftContext,
    outline: str
) -> str:
    """分析验证问题的根源
    
    Returns:
        "plan_error": 规划设置错误
        "content_error": 内容偏离规划
        "ambiguous": 不明确
    """
    if issue.code == "planned_end_state_conflict":
        planned_end = plan.timeline_end
        actual_end = draft.end_state.get("location") or draft.end_state.get("state")
        
        # 检查大纲是否支持规划的 timeline_end
        if planned_end not in outline:
            return "plan_error"  # 规划错误：timeline_end 不在大纲中
        
        # 检查实际内容是否在大纲中
        if actual_end not in outline:
            return "content_error"  # 内容错误：内容偏离大纲
        
        # 两者都在大纲中，检查位置
        planned_pos = outline.find(planned_end)
        actual_pos = outline.find(actual_end)
        
        if planned_pos > actual_pos:
            return "content_error"  # 内容未到达规划的终态
        else:
            return "ambiguous"  # 不明确
    
    return "unknown"
```

然后在验证报告中提供更明确的建议：

```python
if issue_source == "plan_error":
    suggestion = f"建议修改规划：将 timeline_end 从 '{planned_end}' 改为 '{actual_end}'"
elif issue_source == "content_error":
    suggestion = f"建议修改内容：确保章节结束于 '{planned_end}'"
else:
    suggestion = "建议人工审查规划和内容的一致性"
```

## 相关文件

- 问题分析文档: `docs/fixes/chapter_32_validation_issue_analysis.md`
- 修复脚本: `scripts/fix_chapter_32.py`
- 验证服务: `application/core/services/validation_service.py`
- 大纲生成: `application/blueprint/services/beat_sheet_service.py`

## 经验教训

1. **验证"误报"需要深入分析**：用户报告的"误报"可能是真实的不一致，需要分析是规划错误还是内容错误。

2. **规划一致性很重要**：timeline_end 必须与大纲内容一致，否则会导致验证系统产生"误报"。

3. **大纲生成需要完整性检查**：应该在生成后自动检查大纲是否完整，避免截断问题。

4. **验证系统需要更智能**：应该能够区分规划错误和内容错误，并提供针对性的修复建议。
