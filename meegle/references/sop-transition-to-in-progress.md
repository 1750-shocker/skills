# 将名下问题改为处理中

> **CRITICAL** — 开始前 MUST 先用 Read 工具读取 `../SKILL.md`，其中包含授权流程、命令参数参考、通用规范和错误处理。

本 SOP 用于把状态流工作项（常见为缺陷 / issue）流转到 `处理中`。适用于用户说：

- “改成今天处理”
- “改成处理中”
- “我来处理”
- “接手处理”
- “转处理中”

目标状态语义固定为：`state_name == "处理中"` 或 `state_key == "IN PROGRESS"`。

---

## 执行流程

### STEP 0 — Auth Guard

所有业务命令前 MUST 执行：

```bash
meegle auth status --format json
```

未登录时按 `auth-guard.md` 完成登录后再继续。

### STEP 1 — 获取当前用户

```bash
meegle user me --format json
```

保存：

- `$user_key` = `user_key`
- `$user_name` = `name_cn` 或 `name_en`

### STEP 2 — 定位并确认工作项

若用户只给工作项 ID，优先从最近上下文复用 `project_key`；没有可靠 `project_key` 时先用 `mywork`、URL decode 或 `project search` 找到权威空间 key。禁止凭 URL 路径或标题猜 project_key。

查询工作项：

```bash
meegle workitem get --work-item-id "$work_item_id" --project-key "$project_key" --format json
```

保存：

- `$work_item_type` = `work_item_attribute.work_item_type.key`
- `$current_state_key` = `work_item_attribute.work_item_status.key`
- `$current_state_name` = `work_item_attribute.work_item_status.name`

若当前已是 `处理中` / `IN PROGRESS`，直接返回“已是处理中”，无需重复流转。

### STEP 3 — 查询可流转状态

```bash
meegle workflow list-state-transitions \
  --work-item-id "$work_item_id" \
  --project-key "$project_key" \
  --work-item-type "$work_item_type" \
  --user-key "$user_key" \
  --format json
```

从 `transition[]` 中查找：

1. 优先匹配 `state_key == "IN PROGRESS"`
2. 否则匹配 `state_name == "处理中"`

保存：

- `$transition_id` = 命中的 `id`
- `$target_state_key` = 命中的 `state_key`
- `$target_state_name` = 命中的 `state_name`

若没有匹配项，返回当前状态和可选流转状态，说明当前用户无可用“处理中”流转，不要猜其他状态。

### STEP 4 — 检查未完成必填项

```bash
meegle workflow list-state-required \
  --work-item-id "$work_item_id" \
  --project-key "$project_key" \
  --state-key "$target_state_key" \
  --mode unfinished \
  --format json
```

- 返回 `{}` 或空列表：继续 STEP 5。
- 存在必填项：按 `sop-transition-state.md` 的必填字段处理规则处理；业务决策类、人员、日期、枚举字段必须询问用户，禁止编造。

### STEP 5 — 执行状态流转

```bash
meegle workflow transition-state \
  --work-item-id "$work_item_id" \
  --project-key "$project_key" \
  --transition-id "$transition_id" \
  --format json
```

成功返回通常为 `"success"`。

### STEP 6 — 验证结果

必须重新查询工作项状态：

```bash
meegle workitem get \
  --work-item-id "$work_item_id" \
  --project-key "$project_key" \
  --select work_item_attribute.work_item_status,work_item_attribute.update_time,work_item_attribute.updated_by \
  --format json
```

只有验证到：

- `work_item_attribute.work_item_status.key == "IN PROGRESS"`，或
- `work_item_attribute.work_item_status.name == "处理中"`

才可向用户报告成功。报告中包含工作项 ID、最终状态、更新时间和更新人。

---

## 注意事项

- “今天处理”是团队口径，映射为 Meegle 状态 `处理中`，不是修改日期字段。
- `transition_id` 每次都必须实时查询，不能硬编码。
- `work_item_id` 传参使用字符串。
- 修改状态属于有副作用操作；执行前必须确保用户明确指定了目标工作项。
- 成功后如果 `mywork this_week` 列表发生变化，以工作项详情状态为准。
