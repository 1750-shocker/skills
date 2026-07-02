---
name: perfetto-window-analysis
description: 将 Android `trace.perfetto-trace` 转成可读 Markdown/CSV，并按 logcat 事件窗口对齐主线程、RenderThread、慢帧和运行线程热点。适用于 UI 卡顿、返回重建、RecyclerView/Fragment 导航性能定位。
---

# Perfetto Window Analysis

当用户提供 `trace.perfetto-trace`，并希望把结果变得可读，或希望把 `logcat` 中的点击/返回/进入页面事件和 `perfetto` 时序对齐时，使用这个 skill。

## 适用场景

优先用于以下问题：

- 已抓到 `trace.perfetto-trace`，但当前环境没有现成 `trace_processor_shell`。
- `simpleperf` / `top_thread` 已证明主线程重，但还不清楚是哪一次返回、哪一段 UI 流程最重。
- 需要判断卡顿主要在：
  - `FragmentTransaction`
  - `inflate / layout / measure / draw`
  - `RecyclerView`
  - `RenderThread`
- 需要把多次“返回键点击”“详情页返回”“播放器返回”这样的 `logcat` 事件，对齐到 trace 中逐窗分析。

不适合：

- 第一轮粗筛 CPU 热点。第一轮优先用 `top_thread.txt`、`simpleperf report`、`logcat`。
- 完全替代 Perfetto UI。这个 skill 产出的是稳定的摘要和事件窗口，不是交互式时间轴浏览器。

## 脚本位置

本 skill 脚本目录：`{SKILL_DIR}\scripts`

核心脚本：

```text
{SKILL_DIR}\scripts\perfetto_readable_report.py
```

## 能力说明

脚本会：

1. 自动准备 `perfetto` Python API 所需的 `trace_processor` prebuilt。
2. 读取 `trace.perfetto-trace` 并输出总览 Markdown。
3. 输出全局表：
   - `Trace Bounds`
   - `Top Running Threads`
   - `Main Thread Top Slices`
   - `RenderThread Top Slices`
   - `Slow Main Frames`
   - `UI Hotspots`
4. 如提供 `logcat` 和事件模式：
   - 抽取事件时间
   - 自动换算 trace 时钟
   - 围绕每个事件输出窗口级分析
5. 可额外导出每张表的 CSV，便于对比多轮优化结果。

## 标准用法

### 1. 只看全局摘要

```bash
py {SKILL_DIR}\scripts\perfetto_readable_report.py ^
  D:\path\trace.perfetto-trace ^
  --out D:\path\trace_readable_report.md
```

### 2. 按 `logcat` 事件做窗口分析

这是最常用模式。

```bash
py {SKILL_DIR}\scripts\perfetto_readable_report.py ^
  D:\path\trace.perfetto-trace ^
  --logcat D:\path\logcat.txt ^
  --event-pattern "HimalayaPlayerFragment] ivBack click" ^
  --event-pattern "HimalayaDetailFragment] ivBack click" ^
  --event-limit 6 ^
  --window-ms 800 ^
  --event-tz-offset-hours 8 ^
  --out D:\path\trace_readable_report.md ^
  --csv-dir D:\path\trace_csv
```

### 3. 没有 `logcat`，手工给事件时间

```bash
py {SKILL_DIR}\scripts\perfetto_readable_report.py ^
  D:\path\trace.perfetto-trace ^
  --event-time "back=2026-07-01 15:51:33.207" ^
  --event-tz-offset-hours 8 ^
  --window-ms 800
```

## 参数说明

- `trace`：必填，`trace.perfetto-trace` 路径。
- `--process`：目标进程，默认 `com.autolink.music`。
- `--out`：Markdown 报告输出路径。
- `--csv-dir`：CSV 输出目录。
- `--logcat`：可选，`logcat.txt` 路径。
- `--event-pattern`：可重复传入，用于匹配关键事件。
- `--event-limit`：只保留最近 N 个命中的日志事件，默认 `6`。
- `--window-ms`：事件前后窗口半径，单位毫秒，默认 `1000`。
- `--event-time`：可重复传入，手工指定事件时间，支持 `label=time` 或直接时间字符串。
- `--event-tz-offset-hours`：事件时区偏移，国内日志通常是 `8`。

## 结果解读顺序

推荐按下面顺序读：

1. `Trace Bounds`
   - 确认 trace 覆盖的真实时间范围。
2. `Event Windows`
   - 确认哪些日志事件真的落在 trace 覆盖区间内。
3. `Window xx ... Main Thread Slices`
   - 判断这次点击/返回主要卡在 `inflate/layout/draw/traversal` 哪一段。
4. `Window xx ... RenderThread Slices`
   - 判断是不是主线程重建把渲染线程也拖高。
5. `Window xx ... Running Threads`
   - 看同一时间窗是不是还有其它线程共同抢 CPU。
6. `Main Thread Top Slices` / `UI Hotspots`
   - 看全局模式，而不是只看单次事件。

## 结论模板

输出结论时尽量按这个结构：

1. trace 覆盖时间范围。
2. 事件是否被成功对齐到 trace。
3. 某次关键事件窗口的主线程前 3~5 个热点。
4. 同窗口 RenderThread 是否同步升高。
5. 结合代码路径，判断下一步该改：
   - 导航结构
   - Fragment 复用
   - RecyclerView 重绑/重建
   - 图片/Drawable 解码
   - 还是非 UI 链路

## Android/KP31 提示

- Himalaya / MediaCenter 这类问题里，常用事件模式通常是：
  - `HimalayaPlayerFragment] ivBack click`
  - `HimalayaDetailFragment] ivBack click`
  - 页面进入/列表点击/播放器打开等关键日志
- 若 trace 只覆盖很短时间窗，超出范围的事件会被自动过滤；不要拿空窗口做结论。
- 如果 `simpleperf` 已经表明通知链不是主因，这个 skill 的重点应放在 UI 重建链路，而不是继续抠小热点。

## 失败与兜底

- 若提示缺少 Python 包：
  - 运行 `py -m pip install --user perfetto`
- 若没有 `trace_processor_shell`：
  - 脚本会自动准备 prebuilt；通常无需手动处理。
- 若事件没有命中：
  - 先检查 trace 覆盖时间是否包含该事件。
  - 再检查 `--event-tz-offset-hours` 是否正确。
  - 最后再检查日志模式是否过窄或写错。
