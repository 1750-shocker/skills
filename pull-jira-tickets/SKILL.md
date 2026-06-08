---
name: pull-jira-tickets
description: Use when the user says "拉一下jira票", "拉 Jira 票", "整理我名下 Jira", or asks to refresh assigned Jira tickets into D:\BaiduSyncdisk\笔记\公司备忘\jira tickets.md.
compatibility: opencode
---

# Pull Jira Tickets

当用户说“拉一下jira票”、“拉 Jira 票”、“整理我名下 Jira 票”、“刷新 jira tickets.md”或表达同等意图时，执行这个固定流程。

## 固定查询

必须查询分配给用户本人的未解决 Jira 票：

```jql
assignee = wangzihao AND resolution = Unresolved AND (labels is EMPTY OR labels not in (重构)) ORDER BY project ASC, created DESC
```

规则：
- “我名下”唯一指 `assignee = wangzihao`。
- 不要使用 `assignee is empty`。
- 不要使用 `assignee = currentUser()`。
- 不要把未分配票混入结果。
- 默认用 `jira-tool_search_jira` 查询，`max_results` 设为 `200`。
- 查询结果还必须按标签二次过滤：任一标签包含 `重构`、`refactor` 或 `Refactor` 的票都排除，不写入 `jira tickets.md`。
- 带多个标签的票只要任一标签命中排除规则，就整票排除；不要只删除标签文本后保留票据。

## 固定输出文件

把整理结果写入：

```text
D:\BaiduSyncdisk\笔记\公司备忘\jira tickets.md
```

如果文件存在，直接替换为本次最新整理结果。不要追加旧内容。

## 一级标题规则

一级标题来自每张票标题里的**首个中文中括号**内容。

示例：
- `【D01】【中控】...` -> `# D01`
- `【D01-国内】【中控】...` -> `# D01-国内`
- `【D01P国内】【中控】...` -> `# D01P国内`
- `【D01P-国内】【中控】...` -> `# D01P国内`
- `【D01华为】【中控】...` -> `# D01HW`
- `【D01-华为】【中控】...` -> `# D01HW`

归一化规则：
- 首个中括号包含 `华为`，且属于 D01 系列时，统一为 `D01HW`。
- `D01P国内` 和 `D01P-国内` 统一为 `D01P国内`。
- 其他首个中括号内容按原文作为一级标题。

## 二级标题规则

每个一级标题下，按票的实际问题相似度创建二级标题。

常用分类名可参考：
- `弹窗、提示与 UI 显示`
- `播放状态、播放响应与高亮`
- `收藏状态与前后排同步`
- `歌单、分类与播放列表`
- `授权弹窗与层级`
- `返回层级与退出逻辑`
- `音频与模式切换`
- `分屏与闪退`
- `前后排、吸顶屏与蓝牙播放`
- `系统时间异常`

分类必须根据本次票标题动态调整，不要硬套固定分类。

## 每票格式

每张票一行，必须使用 Markdown task list：

```markdown
- [ ] [票号](https://jira-shzj.auto-link.com.cn/browse/票号) 【状态】标题摘要
```

要求：
- 票号必须带链接。
- 链接格式固定为 `https://jira-shzj.auto-link.com.cn/browse/<ISSUE_KEY>`。
- 保留 Jira 状态，例如 `【处理中】`、`【待分配】`、`【集成中】`、`【验证中】`。
- 标题摘要保留核心问题，去掉重复的车型、模块、环境前缀即可。
- 每票只能出现一次。

## 执行步骤

1. 调用 `jira-tool_search_jira` 查询固定 JQL。
2. 从返回表格中提取票号、标题、状态、标签。
3. 先排除标签命中 `重构` / `refactor` 规则的票。
4. 根据标题首个中文中括号生成一级标题，并应用归一化规则。
5. 在每个一级标题下按问题相似度生成二级标题。
6. 写入固定输出文件。
7. 读回文件确认内容已写入。
8. 回复用户时只说明查询数量、排除数量、写入路径和分组概况。

## 注意

- 不要分析 bug 根因。
- 不要下载附件。
- 不要修改 Jira 状态或指派人。
- 如果查询失败，直接说明 Jira 查询失败原因，不要编造票据。
