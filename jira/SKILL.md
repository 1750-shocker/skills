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
- 用户说“待处理票”或“待处理状态票”时，按 Jira 状态 `待分配` 查询；这是用户口语映射，不要查询 `status = 待处理`。
- `status != Closed AND assignee = wangzihao` — 我名下未关闭的票
- `assignee = wangzihao ORDER BY created DESC` — 我名下所有票按创建时间排序

"名下" 在 Jira 语境中**唯一**指代 `assignee` 字段，不是 `reporter` 或 `creator`。

# Jira 状态流转规范

当用户要求把“我名下”的单个 Jira 票从 `待分配` 改为 `处理中`，并设置 `计划修改完成日` 时，优先调用 Jira MCP 写操作工具 `start_my_jira_issue`。

触发示例：
- “把我名下这个 D01-123 待分配的票改成处理中”
- “计划修改完成日写成后天日期”
- “只改这一个”

执行规则：
1. 必须只操作用户明确指定的单个票号或 Jira 链接，不批量匹配其它票。
2. “我名下”必须校验 `assignee = wangzihao`；经办人不是 `wangzihao` 时拒绝修改。
3. 只允许从 `待分配` 流转到 `处理中`；当前状态不是 `待分配` 时拒绝修改。
4. `后天`、`明天` 等相对日期必须按当前系统日期计算成 `YYYY-MM-DD` 后再提交。
5. 修改后必须回查 Jira，确认状态、经办人和 `计划修改完成日` 已生效。
6. 回复用户时只报告本票修改结果，不分析 Bug，不下载附件，不改 `jira tickets.md`。

# Jira 集成备注规范

当用户要求把单个 Jira 票“走到集成中”“提交集成”或类似集成流转时，优先调用 Jira MCP 写操作工具 `submit_jira_issue_for_integration`。

执行规则：
1. 必须只操作用户明确指定的单个票号或 Jira 链接，不批量匹配其它票。
2. 如果当前对话已经生成过本票 commit msg，`Comment/备注` 必须填写完整 commit msg 原文。
3. 禁止用简短处理说明替代已有 commit msg；简短说明只适合没有 commit msg 可复用时。
4. `Root Cause` 和 `Solution` 按工具字段简洁填写，`Resolver` 默认使用 `wangzihao`。
5. 工具执行后回复用户时报告状态、Root Cause、Solution、问题解决者和备注是否已添加。
