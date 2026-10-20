---
name: add-gerrit-reviewers
description: Use when the user says "加reviewer", "加 reviewer", "给提交加审核人", or asks to add the default reviewers to their Gerrit changes.
compatibility: omp
---

# Add Gerrit Reviewers

当用户说“加 reviewer”、“给提交加审核人”或表达同等意图，且没有另外指定范围或审核人时，执行本流程。

## 固定环境

- Gerrit 地址：`https://gerrit.auto-link.com.cn/`
- 当前用户：`wangzihao`
- 使用 OMP 的 Gerrit MCP 工具操作。

## 默认审核人

默认添加以下四名 Reviewer：

- `cenxingcan`
- `wangdesheng`（王德升）
- `heweiwei`
- `jinchu1`

如果用户明确指定其他审核人，以用户本次指令为准，不额外添加默认审核人。

## 默认筛选范围

查询：

```text
owner:self status:open -is:wip
```

只处理同时满足以下条件的 CL：

- Owner 是当前 Gerrit 用户。
- 状态为 Open。
- 不是 WIP。
- CA 已变绿：`Verified` 标签上有机器人账号给出 +1（CA 未绿的 CL 跳过，等绿了再处理）。
- 尚未添加人工 Reviewer。

`scm`、`scm_verify`、`static_code_verify` 等机器人或自动账号不算人工 Reviewer。只有这类自动账号时，仍属于“未加 Reviewer”。

如果 CL 已有任意人工 Reviewer，默认整条跳过，不补齐四人。只有用户明确要求“补齐默认 reviewer”时，才为已有人工 Reviewer 的 CL 添加缺少的默认审核人。

## FL1 分支额外审核人

当目标 CL 的分支名包含 `FL1`（如 `al_chery-d01_sop_FL1`、`al_chery-d01_FL1_int`）时，在四名默认审核人之外额外添加：

- `konglihan`

非 FL1 分支不添加 konglihan。

## KP31 项目额外审核人

当目标 CL 的分支名包含 `kp31`（不区分大小写，如 `al_chery-kp31_dev2`、`al_chery-kp31_release`、`al_chery-kp31_cpaa`）时，在四名默认审核人之外额外添加：

- `zengjie`

非 KP31 分支不添加 zengjie。FL1 与 KP31 可叠加：分支同时命中则两人都加。

## 执行步骤

1. 使用 `query_changes` 查询 `owner:self status:open -is:wip`，上限设为 `100`。
2. 逐个获取 CL 详情（`change/detail?o=DETAILED_LABELS`），检查分支名、`Verified` 标签和 Reviewer 列表。注意：批量查询可能丢失 labels/username 字段，以逐条 detail 为准。
3. 排除 WIP、非 Open、非本人提交、CA 未绿（Verified 无机器人 +1）以及已有人工 Reviewer 的 CL。
4. 对每个剩余 CL，添加四名默认 Reviewer（`state=REVIEWER`）；分支名含 `FL1` 的额外添加 `konglihan`；分支名含 `kp31`（不区分大小写）的额外添加 `zengjie`。
5. 添加后重新获取每个目标 CL 的 Reviewer 列表，确认所有目标 reviewer 均已存在。
6. 回复时说明：查询到的非 WIP 开放 CL 数、CA 未绿跳过数、因已有人工 Reviewer 跳过数、实际处理 CL 数、成功添加次数、失败项。

## 安全约束

- 不修改 WIP CL。
- 不修改已合入、已废弃或已关闭的 CL。
- 不移除任何已有 Reviewer 或 CC。
- 不投票、不发布评论、不提交或废弃 CL。
- 不把 `scm`、`scm_verify`、`static_code_verify` 当作人工 Reviewer。
- 添加失败时保留已成功结果，准确列出失败的 CL 和账号，不重复盲目提交。
