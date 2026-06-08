---
name: jira-bug-log-analysis
description: >-
  Fetches Jira Server issue details by BUG key, analyzes Android logs without
  downloading full attachments, and outputs a structured root-cause analysis
  report. Supports smart android log matching, segmented archives,
  auto-traceback, and download-only mode for user manual analysis.
  Use when the user gives a Jira key (e.g. BAIC-12345), asks to pull a BUG
  from Jira, download Jira attachments, analyze Jira-attached logs, or
  analyze Android logs on Jira Server 8.x.
---

# Jira BUG：智能分析 Android 日志

面向 **Jira Server 8.5.x**（REST API v2）。用户给出 BUG 编号后，**自动完成**拉取、下载、分析。

**核心理念**：只下载匹配发生时间的 android 日志，不下载全量附件。提供分析结果 + 下载文件供用户手动查看。

---

## 认证（环境变量）

**禁止**把密码写入技能文件、仓库、聊天记录或命令行参数。

| 变量 | 说明 |
|------|------|
| `JIRA_URL` | 站点根 URL，无尾部斜杠 |
| `JIRA_USER` | 登录用户名 |
| `JIRA_PASS` | 密码或 API Token |

构建 **Basic Auth**：`Authorization: Basic base64("${JIRA_USER}:${JIRA_PASS}")`。

若变量未设置：简短说明「需在本机配置 JIRA_URL / JIRA_USER / JIRA_PASS」。

---

## BAIC 项目自定义字段

| 字段 ID | 名称 | 取值 |
|---------|------|------|
| `customfield_11002` | **Severity** | **A**（最严重）→ B → C → D |
| `customfield_12810` | BAIC_PROJECT | N51AS / N50AS / N58 等 |
| `customfield_12812` | 故障发生时间 | ISO 时间戳 |
| `customfield_12902` | 原因分析状态 | 未开始 / 进行中 / 已完成 |
| `customfield_12903` | 对策实施状态 | 未开始 / 进行中 / 已完成 |
| `customfield_12904` | 效果验证状态 | 未开始 / 进行中 / 已完成 |

**关键规则**：
- 以 **Severity A/B/C/D** 标注级别，**不要**使用 `priority` 字段
- HMI3.0 清零票 JQL：`resolution = Unresolved AND assignee in membersOf("BAIC_Android_APP") AND issuetype = "BAIC_BUG" AND "BAIC_PROJECT" = N51AS`

---

## 工具脚本

脚本位于本 SKILL.md 同级 `scripts/` 目录下：

```
{SKILL_DIR} = 本 SKILL.md 所在目录
{SCRIPT_DIR} = {SKILL_DIR}/scripts
```

### 1. fetch_issue_context.py — 轻量上下文拉取

快速获取 issue 描述、评论、附件清单，不下载任何文件。用于 AI 判断分析策略。

```bash
python {SCRIPT_DIR}/fetch_issue_context.py BAIC-12345
python {SCRIPT_DIR}/fetch_issue_context.py BAIC-12345 --json
```

输出包含：描述全文、全部评论、附件分类清单（android_log / small_log / large_archive / image / video）、是否已有完整分析链。

### 2. smart_jira_log.py — 智能 Android 日志分析

```bash
# 自动匹配发生时间 → 下载 → 解压 → 分析 → 报告
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345

# 手动指定发生时间
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 -t "2026-03-28 11:24:28"

# 仅列出 android 日志附件
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --list

# 指定附件索引
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --index 2

# 追溯更早日志 / 自动追溯
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --earlier
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --auto-earlier

# 扩大时间窗口 + 全量错误扫描
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --all-errors -w 30

# 仅下载解压，不分析（供用户手动查看）
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --download-only -o ./downloads/BAIC-12345

# JSON 格式输出（供 AI 结构化消费）
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 --json

# 指定输出目录
python {SCRIPT_DIR}/smart_jira_log.py BAIC-12345 -o ./output
```

**核心能力**：
- 从描述/评论中提取发生时间，自动选择最近的 android 日志
- 支持 `.zip.001/.002` 分段压缩包自动拼接
- 断点续传（最多 12 次）+ 嵌套解压（zip in zip, .gz）
- 错误模式匹配：Fatal signal / Exception / ANR / SIGSEGV / OOM / Crash 等 16 种
- 时间窗口过滤：只输出发生时间前后 N 分钟内的异常

---

## 日志下载规则

### 规则 1：默认按描述中的发生时间下载

- 从描述 / `customfield_12812` 提取故障发生时间
- 只下载**采集时间 ≥ 发生时间**且最近的那一个 `android_YYYYMMDD-HHMMSS.zip`
- 禁止下载全量日志；最大下载单位为单个 `android_*.zip`

### 规则 2：ANR / 卡顿 / 性能类问题可扩大范围

当描述或标题含以下关键词时，自行判断是否需要扩大日志分析范围：
- **关键词**：ANR、卡顿、慢、冻屏、黑屏重启、watchdog、性能、OOM、内存泄漏

扩大范围的手段（按需组合，不必全用）：

| 手段 | 适用场景 | 说明 |
|------|----------|------|
| 多下载一个相邻时间的 `android_*.zip` | 崩溃循环 / 需要对比 | `--earlier` 或指定 `--index` |
| 扩大时间窗口 | 故障前有长时间劣化 | `-w 30` 甚至 `-w 60` |
| 分析 **dropbox 文件** | watchdog / crash / ANR | 解压后查看 `exception/dropbox/` 下的 `system_server_watchdog@*.txt`、`system_app_crash@*.txt`、`system_server_pre_watchdog@*.txt` 等，这些文件自带完整线程堆栈 |
| 分析 **kernel 日志** | vold / FUSE / 存储 / 驱动 | 解压后的 `kernel/002_kernel_*.log`，搜索 vold / fuse / fat / mount / umount / storage |
| 分析 **tombstone 文件** | native crash / SIGABRT / SIGSEGV | 解压后的 tombstone 目录 |
| 分析 **内存/性能日志** | OOM / 内存泄漏 / 卡顿 | `resource/002_mem_*.log`、`002_top_*.log`、`002_pidstat_*.log` |

### 规则 3：分段压缩包的 Range 提取（无独立 android_*.zip 时）

当附件中没有独立 `android_*.zip`、日志被打包在分段压缩中时，**禁止下载全量**，统一使用 `LazySegmentFile` + HTTP Range 按需提取。

#### 通用基础：LazySegmentFile

继承 `io.RawIOBase`，将多个 Jira 附件段映射为一个虚拟连续文件。核心特征：
- 按 512KB 块缓存 HTTP Range 响应，只下载实际被 read/seek 触达的区域
- `readinto()` / `read()` / `seek()` / `tell()` 完整实现，可直接传给 `zipfile.ZipFile` 或 `py7zr.SevenZipFile`

#### 3A：Split ZIP（`.zip.001~NNN`）

适用于 Jira 附件为 `Logs_xxx.zip.001 ~ .zip.NNN` 的场景。

提取步骤：
1. **HEAD 请求**获取每个段的 `Content-Length`（约 1s）
2. **Range 读取最后 64KB** 定位 EOCD（End of Central Directory）；若发现 ZIP64 Locator，再读 ZIP64 EOCD
3. **Range 读取 Central Directory**（通常 < 100 KB），解析出所有文件名、偏移、大小
4. **从 CD 自动匹配 logcat 文件**（见下方匹配规则）
5. 用 `LazySegmentFile` 包装为 `io.BufferedReader` → `zipfile.ZipFile(buf)`，调用 `zf.read(target_name)` 按需提取

**logcat 文件自动时间匹配**：

CD 中的 logcat 文件名格式为 `000_logcat_YYYYMMDD-HHMMSS.log.gz`，文件名中的时间是**转储/轮转时间**（dump time），而非日志内容起始时间。每个文件包含从上一个文件的转储时间到本文件转储时间之间的日志。

匹配规则：**取第一个转储时间 > 故障发生时间的文件**。

```python
# 文件名时间 = 转储时间，日志内容 = [上个文件转储时间, 本文件转储时间]
# 故障 20:20:50 → 取 000_logcat_20260327-202139.log.gz（转储 20:21:39 > 20:20:50）
for lf in sorted_logcat_files:
    if lf.dump_time > fault_time:
        matched = lf
        break
```

典型性能（实测 BAIC-55859，2.1 GB / 11 段）：
- 28 次 HTTP 请求，下载 6.8 MB，耗时 17.3s
- 节省 99.7%

需要注意的 ZIP64 处理：
- 当 `comp_size` / `uncomp_size` / `local_offset` 为 `0xFFFFFFFF` 时，从 Extra Field (ID=0x0001) 中读取 8 字节 uint64 真实值
- EOCD signature: `\x50\x4b\x05\x06`，ZIP64 EOCD: `\x50\x4b\x06\x06`，ZIP64 Locator: `\x50\x4b\x06\x07`

#### 3B：Split 7z（`.7z.001~NNN`）

适用于 Jira 附件为 `xxx.7z.001 ~ .7z.NNN` 的场景。

提取步骤：
1. **HEAD 请求**获取每个段大小
2. 用 `LazySegmentFile` + `py7zr.SevenZipFile` 列出内容（仅读文件索引，通常 < 2 MB）
3. 定位内部的 `android_*.zip`，按发生时间匹配
4. 用 `py7zr` 的 `targets` 参数只提取匹配文件

典型性能（实测 BAIC-54543，847 MB / 5 段）：
- 下载 56.7 MB，节省 93.3%

---

## 执行流程

用户给出 BUG 号后，**按此顺序执行**：

### 第 0 步 — 记录开始时间

```powershell
Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
```

### 第 1 步 — 拉取上下文

运行 `fetch_issue_context.py` 获取：
1. 描述全文（提取发生时间）
2. 全部评论（寻找已有分析结论）
3. 附件清单（按类型分类）

### 第 2 步 — 评论优先：提取已有分析

**先看评论，再决定是否下载。** 评论中的分析可作为参考摘要，但**不能作为解票依据**——任何评论中的分析都可能有方向偏差。在评论中寻找：
- **异常关键字**：Exception、ANR、Crash、Fatal、watchdog、SIGSEGV、OOM
- **根因描述**：「原因」「导致」「Caused by」「root cause」
- **修复链接**：Gerrit URL、commit hash、「已修复」「已合入」
- **关联票**：其它 BAIC-XXXXX 引用

### 第 3 步 — 智能下载与分析

根据附件形态和问题类型选择路径：

**路径 A：附件中有独立 `android_*.zip`**
- 按日志下载规则 1/2，用 `smart_jira_log.py` 下载匹配时间的 android 日志
- 若无发现：`--auto-earlier` 追溯
- ANR/卡顿/性能类：参照规则 2 扩大分析范围

**路径 B：日志打包在分段压缩中（zip 或 7z）**
- `.zip.001~NNN`：按规则 3A，Range 读 Central Directory → `zipfile.ZipFile` 提取目标 logcat
- `.7z.001~NNN`：按规则 3B，`LazySegmentFile` + `py7zr` 列出内容 → 提取目标 `android_*.zip`
- 两种格式均通过 `LazySegmentFile` 实现按需 Range 下载，不下载全量
- 解压后同路径 A 分析

**路径 C：同时为用户下载日志**
- 将提取的 `android_*.zip` 保存到 `{workspace}/downloads/{KEY}/`
- 告知用户文件保存路径

### 第 4 步 — 日志分析

解压 `android_*.zip` 后，按问题类型选择分析目标：

| 问题类型 | 优先分析 | 次要分析 |
|----------|----------|----------|
| Crash / 闪退 | logcat + `exception/dropbox/system_app_crash@*.txt` | tombstone |
| 黑屏重启 / watchdog | `exception/dropbox/system_server_watchdog@*.txt` + `pre_watchdog` | logcat 中 StorageManager / vold |
| ANR / 卡顿 | `exception/dropbox/*_anr@*.txt` + logcat | `resource/002_top_*.log`、`002_pidstat_*.log` |
| OOM / 内存 | logcat + `resource/002_mem_*.log` | `002_top_*.log` |
| 存储 / TF卡 | kernel 日志 + logcat 中 vold/fuse/mount | dropbox watchdog 文件 |

### 第 5 步 — 输出报告

记录结束时间，计算耗时，输出最终分析报告。

---

## 附件分级策略

| 优先级 | 类型 | 策略 |
|--------|------|------|
| **P0** | 小日志 (< 50 MB) `.log`/`.txt` | 直接下载分析 |
| **P1** | Android 日志 zip `android_YYYYMMDD*.zip` | 只下载匹配发生时间的 |
| **P1.5** | 分段压缩中的 logcat / android_*.zip | LazySegmentFile Range 提取（zip 用 Central Directory 定位，7z 用 py7zr） |
| **P2** | 中型分段压缩 (< 1 GB) | 仅在 P0/P1 + 评论不足时 |
| **P3** | 大型分段压缩 (> 1 GB) | 最后手段 |
| **跳过** | 图片/视频 `.png`/`.jpg`/`.mp4` | 不下载 |

---

## 输出格式（必须严格遵循）

使用 **中文** 输出。**不要**输出凭据。

```markdown
## BUG 分析：{KEY}

- **BUG 号**：{key}
- **标题**：{summary}
- **Severity**：{A/B/C/D，取自 customfield_11002}
- **状态**：{status}
- **故障时间**：{从描述/评论提取，优先取 customfield_12812}

### 附件策略

| 类别 | 数量 | 大小 | 是否下载 |
|------|------|------|----------|
| {按分级列出} | | | 是/否（附原因）|

### 日志关键报错
- （分点列出，每点含 **来源** + 摘录）

### 根因链（标注已证实 / 推测）
- （用 → 箭头串联因果链）

### 责任方与进展

| 问题 | 责任方 | 状态 |
|------|--------|------|
| ... | ... | 已修复/待处理 |

### 建议解决方案
- （可执行检查步骤、修复方向）

### 下载文件位置
- Android 日志已下载到：`{output_dir}`
- 用户可直接查看解压后的 logcat/main/system/crash 等文件

### 分析耗时

| 阶段 | 时间 |
|------|------|
| 开始 | {HH:MM:SS} |
| 结束 | {HH:MM:SS} |
| **总耗时** | **{X 分 Y 秒}** |
| 实际下载 | {下载量} MB（vs 全量 {总量} GB，节省 {百分比}%）|
```

---

## 硬性规则

1. **永不**在回复、代码块中写出密码或 Base64 密文
2. **不**询问「要不要下载」「请提供密码」；凭据问题只指向环境变量
3. 用户已给出 BUG 号则**直接执行**；未给出时才询问
4. 默认**只输出最终分析结果**；不粘贴完整 JSON 或整文件日志
5. **每次分析必须包含耗时统计**
6. **评论参考但不依赖**：先读评论作为参考，但不能仅凭评论结论解票
7. **最小下载**：默认只下载发生时间匹配的 `android_*.zip`，严格按 P0 → P1 → P1.5 → P2 → P3 递进
8. **ANR/卡顿/性能可扩大**：遇到 ANR、卡顿、性能类问题时可自行扩大日志范围（多时间点、dropbox、kernel、内存日志等）
9. **同时下载日志给用户**：将描述对应的 android 日志下载到 workspace，告知路径
10. **禁止全量下载**：最大下载单位为单个 `android_*.zip`；分段压缩包（zip/7z）必须用 LazySegmentFile + Range 请求按需提取

## 实现提示（Windows / PowerShell）

- 用 Python 脚本（`requests` 库）发请求，避免 PowerShell 中文编码问题
- 设置 `$env:PYTHONIOENCODING = "utf-8"`
