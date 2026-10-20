---
name: blame-log
description: 当用户说甩锅、甩锅日志、日志总结、把日志甩给对方、给对方看的日志证据时，把已核对的日志整理成可直接转发的证据文本。每两三行真实日志后跟一句短说明，不用 Markdown，中文说明不用句号。
---

# Blame Log

用户要的是一份能直接贴给对方的日志证据，不是分析报告，也不是方法链讲解。

触发话术包括：甩锅、甩锅日志、日志总结、把这段甩给对方、给对方看的证据。

## 先核对再写

- 只摘已经从原始日志读到的行，禁止凭记忆改写时间、pid、tag、字段
- 日志行必须原样保留，包括空格、大小写、冒号和标点
- 过长的窗口列表可以在不改变关键字段的前提下用 `...` 截断，截断处必须仍能看出 display、窗口名、目标 Activity
- 说明只解释这几行已经证明的事实，不补未出现的调用链，不写修复建议
- 用户指定的故障时间优先于邻近的另一次同类事件

## 输出格式

最终回复不要使用 Markdown。不要用标题、列表、表格、代码块、加粗、反引号。

结构：

1. 开头一行来源，写清日志文件，以及本段用到的 pid 对应进程
2. 每 2 到 3 行原始日志后空一行，再写一句说明
3. 说明和时间顺序一致，先证明己方动作已发出，再证明对方或系统已接收、已完成或已失败

中文说明规则：

- 句子中间不用句号
- 分隔只用空格或逗号
- 行尾也不要句号
- 日志原文里的句号、英文句点、冒号保持不动

## 证据取舍

优先保留能划清责任的行：

- 己方发出的请求，例如 `showSoftInput`、点击、跳转、接口调用
- 对方进程收到并处理的行，例如输入法、系统服务、对方应用的 tag
- 结果行，例如 `onShown`、`onHidden`、`onCancelled`、错误码、窗口 displayId
- 能反驳“没调用”或“调错屏幕”的行

丢掉心跳、车身信号、重复的同类窗口刷新。同一结论只留最早一条和结果一条。

## 示例形状

来源是 aplog.002, 4769 是 com.autolink.music, 4064 是 KIKA

2026-10-14 10:09:33.057  4769  4769 I ImeTracker: com.autolink.music:cee6ef6d: onRequestShow at ORIGIN_CLIENT_SHOW_SOFT_INPUT reason SHOW_SOFT_INPUT
2026-10-14 10:09:33.057  4769  4769 D InputMethodManager: showSoftInput() view=... edt_search ... flags=1 reason=SHOW_SOFT_INPUT
MediaCenter 已对中控 edt_search 发出 showSoftInput, flags=1 即 SHOW_IMPLICIT

2026-10-14 10:09:33.316  4769  4769 I ImeTracker: com.autolink.music:cee6ef6d: onShown
onShown 表示这次弹出已完成, 不是请求失败
