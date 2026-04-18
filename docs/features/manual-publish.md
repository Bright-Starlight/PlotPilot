# 手动发布功能

## 概述

手动发布功能允许用户在 Validation 阶段 LLM 误判时，通过人工审阅后手动触发发布流程，将融合草稿内容写入章节正文。

## 使用场景

- **LLM 误判**：Validation 检测到阻塞性问题（blocking issues），但人工审阅后认为这些问题可以接受
- **人工介入**：需要人工决策是否发布章节内容
- **绕过自动门禁**：在确认内容质量后，手动触发发布而不依赖自动质量门禁

## API 端点

### POST /api/v1/chapters/{chapter_id}/manual-publish

手动发布融合草稿到章节正文。

#### 请求参数

- `chapter_id` (路径参数): 章节 ID

#### 响应

```json
{
  "chapter_id": "chapter-novel-123-chapter-1",
  "fusion_id": "fusion_abc123",
  "plan_version": 1,
  "state_lock_version": 2,
  "text_length": 3500,
  "published": true
}
```

#### 错误响应

- `400 Bad Request`: 章节不存在、没有融合草稿或融合草稿文本为空

## 工作流程

1. **Validation 检测**：系统运行 Validation 检测到阻塞性问题
2. **人工审阅**：用户查看 Validation 报告，判断问题是否可接受
3. **手动发布**：用户点击"发布"按钮，调用手动发布 API
4. **内容替换**：系统获取最新融合草稿并替换章节正文
5. **发布完成**：章节正文更新为融合草稿内容

## 与自动发布的关系

手动发布执行与自动发布**完全相同**的逻辑：

```python
# 自动发布（autopilot_daemon.py）
draft = fusion_repository.get_latest_draft_for_chapter(chapter_id)
chapter.update_content(draft.text)
chapter_repository.save(chapter)

# 手动发布（validation_service.py）
draft = fusion_repository.get_latest_draft_for_chapter(chapter_id)
chapter.update_content(draft.text)
chapter_repository.save(chapter)
```

唯一区别：
- **自动发布**：在质量门禁通过后自动触发
- **手动发布**：由用户主动触发，绕过质量门禁

## 前端集成建议

### 按钮位置

建议在 Validation 报告页面添加"发布"按钮：

```
┌─────────────────────────────────────┐
│ Validation 报告                      │
├─────────────────────────────────────┤
│ 状态: 未通过                         │
│ 阻塞性问题: 2 个                     │
│                                     │
│ [查看详情] [忽略问题] [发布章节]     │
└─────────────────────────────────────┘
```

### 按钮文案建议

- **"发布章节"** - 直接明确
- **"强制发布"** - 强调绕过门禁
- **"人工发布"** - 强调人工决策
- **"确认发布"** - 强调确认动作

### 确认对话框

建议添加二次确认：

```
确认发布章节？

当前章节存在 2 个阻塞性问题：
• 检测到互斥数值事实
• 章节终态与规划不一致

发布后，融合草稿内容将替换章节正文。
此操作不可撤销。

[取消] [确认发布]
```

## 实现细节

### 服务层

`ValidationService.manual_publish_fusion_draft(chapter_id: str) -> dict`

1. 验证章节存在
2. 获取最新融合草稿
3. 验证融合草稿文本非空
4. 更新章节内容
5. 保存章节实体
6. 返回发布结果

### API 层

`POST /api/v1/chapters/{chapter_id}/manual-publish`

- 调用服务层方法
- 处理异常并返回适当的 HTTP 状态码
- 返回发布结果

## 测试覆盖

- ✅ 成功发布融合草稿
- ✅ 章节不存在时抛出异常
- ✅ 没有融合草稿时抛出异常
- ✅ 融合草稿文本为空时抛出异常

## 安全考虑

1. **权限控制**：建议添加权限检查，只有特定角色可以手动发布
2. **审计日志**：记录手动发布操作，包括操作人、时间、章节 ID
3. **二次确认**：前端应添加确认对话框，防止误操作

## 未来改进

- [ ] 添加权限控制
- [ ] 添加审计日志
- [ ] 支持发布时附加备注说明
- [ ] 支持发布后自动触发信息同步
