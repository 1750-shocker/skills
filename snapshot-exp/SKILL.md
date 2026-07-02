---
name: snapshot-exp
description: 将当前对话中的开发经验、踩坑记录和设计决策沉淀为经验文档。
compatibility: opencode
metadata:
  source: migrated-from-claude
  original-name: snapshotExp
---

# 开发经验快照

将当前对话中的开发经验、踩坑记录和设计决策整理并保存到：

`D:\logAnalyseForRag\kp31ximalaya开发`

## 文件名规则

1. 若用户给出了前缀，例如页面名或模块名，则生成 `{前缀}_experience.md`。
2. 若未提供前缀，则使用当前日期，格式为 `{YYYY-MM-DD}_experience.md`。
3. 若文件已存在，则在末尾追加内容，并用 `---` 分隔，不覆盖原内容。

## 文档重点

优先整理以下内容：

1. 踩过的坑：现象、原因、解决方式、教训
2. 为什么这么写：方案对比、最终选择、理由、代价
3. 关键代码片段：保留真实代码和说明
4. 后续注意事项：需要复查、重构或确认的点

## 填写要求

1. 只使用当前对话中真实讨论或修改过的内容。
2. 信息不足的章节可以省略，不要强行补全。
3. 代码片段保留原始格式并标注语言。
4. 文档面向未来维护者，应说明上下文和决策原因。


## 收尾

文档写入成功后，执行知识库更新脚本：

```text
cmd.exe //c "D:\aboutMCP\rag-mcp-server\update_knowledge_base.bat"
```

并将执行结果告诉用户。
