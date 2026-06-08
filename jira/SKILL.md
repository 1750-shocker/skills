---
name: jira
description: 处理 Jira 链接并下载附件到 D:\logAnalyseForRag，不做问题分析。
compatibility: opencode
metadata:
  source: migrated-from-claude
---

# Jira 附件下载

当用户要求处理 Jira 链接但不要求分析问题时，遵循以下规则：

1. 仅调用 Jira 下载相关 MCP 工具。
2. 下载根目录固定为 `D:\logAnalyseForRag`。
3. 如果工具执行失败，只回复失败原因，不尝试其他替代方案。
4. 不分析 Jira 描述中的问题。
5. 不提出代码修复建议。
6. 默认只返回工具结果和下载位置。

# Jira 票查询规范

当用户查询 "我名下"、"分配给我" 的 Jira 票时，JQL 必须明确使用：

```
assignee = wangzihao
```

**禁止使用**：
- `assignee is empty`（未分配）
- `assignee = currentUser()`（可能解析错误）
- `assignee = wangzihao OR assignee is empty`（歧义）

**正确示例**：
- `status = "待分配" AND assignee = wangzihao` — 我名下待分配的票
- `status != Closed AND assignee = wangzihao` — 我名下未关闭的票
- `assignee = wangzihao ORDER BY created DESC` — 我名下所有票按创建时间排序

"名下" 在 Jira 语境中**唯一**指代 `assignee` 字段，不是 `reporter` 或 `creator`。
