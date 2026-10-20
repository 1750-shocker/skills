---
name: feishu-bug-intake
description: >-
  接收飞书项目（Meego/Meegle）工作项详情链接，按票据标题创建 D:\bugs\today
  下的现象目录，完整下载工作项附件并创建现象.md；当用户说“开始分析”时，
  读取该文件中的日志地址、Bug 现象和补充说明后开始定位。适用于“飞书链接”“下载飞书票附件”
  “创建现象文件”“开始分析”等请求。
---

# 飞书 Bug 收集与分析

## 目标

将一个飞书项目工作项整理为可分析的本地 Bug 工作目录：

```text
D:\bugs\today\<标题摘要>\
  现象.md
  <工作项中的全部附件>
```

用户自行填写 `现象.md` 后，说“开始分析”即可进入日志与源码分析，不需要再次粘贴链接。

## 触发

- 用户发送飞书项目/Meego 工作项详情链接。
- 用户说“下载飞书票”“准备分析飞书 Bug”“创建现象文件”。
- 用户说“开始分析”。

只接受 `url decode` 识别为 `workitem_detail` 的链接。视图、空间首页、工作项类型首页和未知链接没有唯一票据，要求用户提供工作项详情页链接；禁止从原始 URL 手工截取 ID。

## 阶段一：收集飞书票

收到链接后，直接执行以下流程；不分析根因，也不擅自修改票据。

### 1. 解析并读取工作项

1. 执行：

   ```powershell
   meegle url decode --url '<飞书链接>' --format json
   ```

2. 执行 Meegle Auth Guard：先检查 `meegle auth status --format json`。未登录时使用链接解析得到的 host 执行 `meegle auth login --host <host>`；登录成功后继续流程。
3. 用 `simple_name` 执行 `meegle project search`，得到权威 `project_key`。如果匹配多个空间，要求用户选择，禁止猜测。
4. 读取完整工作项：

   ```powershell
   meegle workitem get --project-key '<project_key>' --work-item-id '<work_item_id>' --fields _all --format json
   ```

   有 `next_page_token` 时持续翻页，直到所有字段读取完成。标题以工作项的 `name` 为准。
5. 获取工作项全部评论及其富文本/附件引用：

   ```powershell
   meegle comment list --project-key '<project_key>' --work-item-id '<work_item_id>' --auto-paginate --format json
   ```

### 2. 生成目录名

从标题生成 `<标题摘要>`，规则严格如下：

1. 删除所有中文方括号 `【...】`、英文方括号 `[...]` 内的完整内容及括号本身；支持多个片段。
2. 将剩余文字中的空白压成一个空格，再去掉首尾空白和 Windows 非法字符 `< > : " / \\ | ? *`。
3. 取工作项详情链接末尾的 4 个阿拉伯数字作为 `<标题摘要>`，例如 `https://project.feishu.cn/sb69eb/issue/detail/7074106608` 取 `6608`；链接末尾不足 4 位数字时，回退为取剩余标题最前面的约 6 个可见字符（中文、英文、数字均各算一个字符，不足 6 个则保留全部）。
4. 若结果为空，使用 `飞书票-<work_item_id>`。
5. 首选目录为 `D:\bugs\today\<标题摘要>`。仅当目录内的 `现象.md` 已记录同一个 `work_item_id` 或同一个飞书工作项链接时，才复用该目录；绝不清空、重命名或覆盖其中已有文件。
6. 同名目录属于不同票据时，从 `D:\bugs\today\<标题摘要> (1)` 开始按递增整数查找第一个不存在的目录（随后是 `(2)`、`(3)`）；创建该目录。

例：链接 `https://project.feishu.cn/sb69eb/issue/detail/7074106608` -> `6608`；若链接末尾无数字，标题 `【KP31】【APP】打开喜马拉雅后无声音` -> `打开喜马拉雅后`。

### 3. 下载全部附件

1. 创建目标目录，保留已有内容。
2. 附件读取必须覆盖工作项的全部字段、描述富文本和所有评论。先从每个字段的结构化值递归提取附件对象及 `file_url`；再从富文本的链接、图片、文件卡片和 JSON 嵌入对象提取附件引用。不要只检查字段名或顶层 `file_url`。
   - 必须先通过 `meegle workitem meta-fields` 识别 `file` / `multi-file` 类型字段，再逐个以 `meegle workitem get --fields <field_key>` 显式读取；未返回该字段即视为空，不能把 `_all` 响应中缺失字段误判为已下载。
   - 无论 Meegle API 是否返回附件，都必须调用页面附件列表接口：`GET https://mg-jira.auto-link.com.cn/api/files/list?project_key=<project_key>&work_item_type_key=<work_item_type>&work_item_id=<work_item_id>`。响应 `data` 的每项包含 `id`、`name`、`size` 和 `type`，是该工作项的完整页面附件清单，也是下载工作的权威来源。
   - 对列表中的每个附件，以 `id` 组成下载链接：`https://mg-jira.auto-link.com.cn/api/files/download/<id>?project_key=<project_key>&work_item_type_key=<work_item_type>&work_item_id=<work_item_id>&download=1`；通过 `curl.exe -fL --retry 2 -o '<目录>\<name>' '<下载链接>'` 下载。下载 URL 由列表接口生成，禁止凭空猜测 ID。
   - 每项响应必须是 2xx、目标文件非空且大小等于列表中的 `size`；否则最多重试两次并报告失败。
   - Meegle 返回的 `file_url` 仅用于补充发现描述/评论内嵌资源；与页面附件列表按 `name + size` 去重，避免重复下载。
3. `现象.md` 必须在“已下载附件”小节记录页面附件列表的每个成功文件名；不记录完整下载 URL、Cookie 或 Token。若列表为空，明确报告“页面附件列表为空”，而不是根据 Meegle 字段推断。

新建文件的固定内容：

```markdown
# 现象

## 飞书链接

<用户提供的飞书工作项详情链接>

## 日志地址


## Bug现象


## 补充说明


```

### 4. 收集完成的回复

只报告：

- 本地绝对目录；
- 成功下载附件数、未发现附件引用或失败附件名（如有）；
- `现象.md` 是否新建或保留；
- 提示用户填写完后说“开始分析”。

## 阶段二：开始分析

当用户说“开始分析”时：

1. 找到本次对话最近一次成功收集的目录，并读取 `<目录>\现象.md`；若本对话未收集过票据，询问用户提供本地工作目录或飞书工作项详情链接。
2. 从文件中读取并原样理解：
   - `日志地址`：本地文件/目录、网络地址或压缩包位置；
   - `Bug现象`：用户观察到的失败行为；
   - `补充说明`：时间点、复现步骤、机型、版本、对比样本及其它约束。
3. 若三项都为空，要求用户先填写 `现象.md`，不进行猜测性分析。
4. 日志地址指向网络文件时，先下载到当前 Bug 目录；指向本地文件或目录时，先确认其可读取。引用附件目录内日志时，优先使用已下载文件。
5. 从 `Bug现象` 和 `补充说明` 提取可验证的时间点、动作、预期/实际结果；没有时间点时，按现象从全量日志反查，并明确时间由日志反查得到。
6. 按 `android-archive-log-analysis`、`deepseek-log-analysis` 或当前可用的日志分析能力，基于日志证据还原调用链并映射到项目源码。不要仅凭票据标题或现象猜测根因。
7. 输出必须区分：已证实日志证据、源码佐证、尚未证实的推测、缺失的证据。必要时继续追溯更早日志，而不是把直接异常当根因。


## 阶段三：提交与跨分支合入

当用户说“提交”“提交当前修改”或等效表达时，执行本阶段。此阶段提交的是本次飞书问题处理所作的源码修改；不要把仅用于分析的附件、日志、`现象.md` 或用户已有的无关改动一起提交。

### 1. 提交前检查

1. 读取当前项目的 `AGENTS.md`，遵守其中的提交信息格式、分支和验证要求。
2. 执行 `git status --short --branch`，确认当前分支和改动范围。仅暂存本次问题实际修改的文件；禁止使用 `git add -A`、`git add .` 或任何会吞入无关改动的命令。
3. 若无法从当前会话、改动内容和飞书票明确区分本次修改与已有改动，先询问用户要提交哪些文件；不得猜测或提交全部工作区。
4. 对本次改动运行适用的定向验证。验证失败时不得提交或推送；报告失败并完成可达的修复。
5. 按项目 `AGENTS.md` 生成提交信息。当前会话已处理飞书票时，使用该票链接；提交信息首行是后续项目识别的唯一依据。

### 2. 创建 Gerrit 主变更

1. 只提交已暂存的本次修改，记录新提交 SHA。
2. 获取当前本地分支名 `<source_branch>`，推送到 Gerrit 审核引用，而不是直接更新远程分支：

   ```bash
   git push origin HEAD:refs/for/<source_branch>
   ```

3. 记录 Gerrit 返回的主 CL 链接。若推送被拒绝，先读取拒绝原因；不得强推、覆盖远程分支或改写用户已有提交。

### 3. 按项目创建远程分支 Cherry-pick CL

以新创建的本地提交 SHA 的首行提交标题判断项目，大小写不敏感：

- 首行包含 `【KP31】`：依次为 `al_chery-kp31_dev2`、`al_chery-kp31_release` 创建 Cherry-pick CL。
- 首行包含 `【D01FL1】`、`【D01_FL1】` 或 `【D01FL1`：依次为 `al_chery-d01_release`、`al_chery-d01_dev2`、`al_chery-d01_sop_FL1` 创建 Cherry-pick CL；这三条完成后，询问用户是否还要创建到 `al_chery-d01_FL1_int` 的 Cherry-pick CL，未获明确同意不得创建。
- 未匹配上述项目：不做自动 Cherry-pick；仅保留主 CL。用户明确指定额外目标分支时，按其明确列表创建 Cherry-pick CL。

对每个自动或用户明确指定的 `<target_branch>`，严格按下面流程执行：

1. `git fetch origin <target_branch>`，以 `origin/<target_branch>` 为基线；不得使用当前本地目标分支，因为它可能落后远程。
2. 在项目目录之外创建唯一的临时 detached worktree，基于 `origin/<target_branch>`；不得切换、重置或污染用户当前工作区和本地分支。
3. 在临时 worktree 中执行 `git cherry-pick <new_commit_sha>`。遇到冲突时停止，保留冲突证据并询问用户；不得自行选择冲突内容或强制合入。
4. 成功后执行：

   ```bash
   git push origin HEAD:refs/for/<target_branch>
   ```

   这会为目标远程分支创建独立 Gerrit CL，不会直接修改已受保护的远程分支。
5. 记录每个返回的 Gerrit CL 链接。若提示 `no new changes`，报告该目标分支不存在可创建的新变更，不重试或强推。
6. 无论成功、拒绝还是冲突，均在确认不再需要后移除临时 worktree。不得删除用户原有 worktree。

### 4. 提交结果

回复必须列出主 CL、每个成功创建的目标分支 Cherry-pick CL、未创建的分支及原因、验证结果，以及保留的无关工作区改动。不要声称 Cherry-pick 已提交入库；Gerrit 新 CL 仍需审核和提交。


## 边界

- 不在 `D:\bugs\today` 之外保存此流程下载的附件。
- 不删除已有文件，不覆盖用户填写的 `现象.md`。
- 不在附件尚未完成下载时宣称“完整下载”。
- 不泄露 OAuth token、签名下载 URL 或其它凭据。
- 收集阶段只整理文件，不给根因、修改建议或代码改动。
- 提交阶段禁止直接 `git push origin <sha>:<branch>`、`git push --force`、`git reset --hard` 或 `git checkout --`。
- 默认只为 KP31 和 D01FL1 执行自动分支规则；其它项目一律仅推送当前分支，除非用户明确指定目标远程分支。
- 远程分支的 Cherry-pick 必须在主 CL 创建成功后执行。

