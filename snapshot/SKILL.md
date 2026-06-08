---
name: snapshot
description: 将当前对话分析结果保存为 Jira 上下文快照和日志证据链文档。
compatibility: opencode
metadata:
  source: migrated-from-claude
---

# 分析快照

将当前对话中的分析结果整理并保存到目标目录。若用户未明确给出目标目录，默认使用 `D:\logAnalyseForRag`。

## 票号识别规则

1. 优先从目标目录名提取 Jira 票号。
2. 若目录名不含票号，则从当前对话上下文推断。
3. 若仍无法确定，向用户追问一次。

## 输出文件

生成以下两份 Markdown 文档：

1. `{票号}_context_snapshot.md`
2. `{票号}_evidence_chain.md`

### 上下文快照文档内容

1. 问题概述
2. 复现条件
3. 根因定位
4. 修复思路
5. 待确认项
6. 关键文件

### 日志证据链文档内容

按时间或逻辑顺序列出证据节点，每个节点包含：

```text
【证据 N】
日志原文：
<直接引用真实日志>

说明：
<这段日志反映了什么，与 Bug 的关系>
```

## 要求

1. 只使用当前对话中真实出现过的日志和结论，不编造。
2. 信息不足的位置写 `待补充`。
3. 将文件写入目标目录，并在完成后告知绝对路径。

## 收尾

如果保存路径位于 `D:\logAnalyseForRag` 或其子目录，文档写入成功后执行知识库更新脚本：

```text
cmd.exe //c "D:\aboutMCP\rag-mcp-server\update_knowledge_base.bat"
```

并将脚本结果一并告知用户。
