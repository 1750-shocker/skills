---
name: drawio
description: Use when the user wants a draw.io code architecture diagram where files/classes are main swimlane nodes, key variables/state are child nodes inside each class, and method calls/events are labeled arrows between them. Triggers on phrases like "文件为主节点" "变量为子节点" "方法调用流程" "以类为容器" "方法驱动" "file class variable method diagram" or when the user rejects a conventional class-relationship-only diagram and asks for a file-variable-method perspective.
---

# Code Variable Flow Diagram

Use this skill when the user wants to understand code data/event flow through diagrams where:

- Main nodes = **file/class names** (e.g., `CloudMusicRecommendFragment.java`, `CloudMusicHomeRecommendViewModel.java`)
- Child nodes = **key variables and state** owned by each file/class (e.g., `personalWanderLiveData`, `mPlayList`)
- Arrows = **method calls or events** that drive the flow, with method/event names as edge labels (e.g., `getPersonalWanderList(true)`, `postValue(filtered)`, `CLOUD_MUSIC_EVENT_WANDER_CHANGED`)

This skill differs from `code-drawio-blueprint` which focuses on class-to-class relationships. This skill focuses on **file/class as container, variable as child, method as arrow driver**.

## When to Use

- User says "文件为主节点" "以类为容器" "以大框套小框"
- User says "变量作为子节点" "关键变量" "xxLiveData" "xxList"
- User says "箭头标注方法名" "方法为驱动者" "调用xx方法改变xx变量"
- User says "想看懂数据流和变量变化"
- User rejects a previous diagram as "不够细" "没体现变量" "没体现方法调用"

## Diagram Structure Rules

### 0. draw.io 兼容性规则

- 生成 XML 时必须使用纯数字 `mxCell id`：`0`、`1` 为根节点，业务节点从 `2` 开始递增。
- 不要使用语义化字符串 id（如 `svc`、`vm_livedata`、`e8`）。部分 draw.io desktop 版本打开这类文件会报 `d.setId is not a function`。
- `source`、`target`、`parent` 也必须引用这些数字 id；需要可读性时用 XML 注释或 `value` 文本表达语义。
- 除非确实需要容器内相对坐标，否则优先使用根节点 `parent="1"` + 绝对坐标，减少旧版本 draw.io 解析兼容风险。

### 1. Main nodes = swimlane per file/class
Each source file or class is a top-level swimlane:

```xml
<mxCell id="2" value="CloudMusicPlayerService.java" style="swimlane;startSize=34;html=1;rounded=1;whiteSpace=wrap;fillColor=#FFF6F5;strokeColor=#B85450;fontStyle=1;fontSize=16;" vertex="1" parent="1">
  <mxGeometry x="..." y="..." width="420" height="600" as="geometry" />
</mxCell>
```

Color coding by layer:
- UI / Fragment: `#F3F7FF` fill, `#6C8EBF` stroke (blue)
- ViewModel: `#F6FFF3` fill, `#82B366` stroke (green)
- Service / Manager: `#FFF9EC` fill, `#D79B00` stroke (orange)
- Core Service / Player: `#FFF6F5` fill, `#B85450` stroke (red-pink)
- Repository / External: `#F5F5F5` fill, `#666666` stroke (gray)
- EventBus: `#F3F3FF` fill, `#9673A6` stroke (purple)

Layout: left to right. Fragment → ViewModel → Manager → Service → Repository.
Arrows go rightward for forward calls, leftward for callbacks.

### 2. Child nodes = variables, state, key methods inside each swimlane

Each child node uses the numeric id of its swimlane as `parent` with coordinates relative to the swimlane:

```xml
<!-- Inside swimlane id 2: a variable node -->
<mxCell id="3" value="personalWanderLiveData&#xa;推荐页观察的 UI 数据" style="shape=cylinder3;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontSize=13;fontStyle=1;" vertex="1" parent="2">
  <mxGeometry x="70" y="280" width="270" height="72" as="geometry" />
</mxCell>
```

Child node types:
- **State variables**: `shape=cylinder3` — use for LiveData, list, state holder
- **Key methods**: `rounded=1` — methods that are entry points or drivers
- **UI elements**: `rounded=1` with `fillColor=#FFF2CC` — the final UI consumer
- **Event/flag**: `rounded=1` — EventBus events, boolean flags

### 3. Arrows = method calls or events with text labels

Every arrow must carry a label that describes the driving method or event:

```xml
<!-- Solid arrow for direct call -->
<mxCell id="8" value="next() 调用 playNext()" style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;endFill=1;strokeColor=#B85450;exitX=0.5;exitY=1;entryX=0.5;entryY=0;" edge="1" parent="1" source="4" target="5">
  <mxGeometry relative="1" as="geometry" />
</mxCell>

<!-- Dashed arrow for callback / LiveData observation -->
<mxCell id="9" value="observe 回调调用 setImageView" style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;endFill=1;strokeColor=#6C8EBF;dashed=1;exitX=0.5;exitY=1;entryX=0.5;entryY=0;" edge="1" parent="1" source="6" target="7">
  <mxGeometry relative="1" as="geometry" />
</mxCell>

<!-- Thick arrow for critical fix path -->
<mxCell id="17" value="修复后：补齐后统一 trigger(event)" style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;endArrow=block;endFill=1;strokeColor=#82B366;strokeWidth=2;exitX=0;exitY=0.7;entryX=1;entryY=0.5;" edge="1" parent="1" source="10" target="11">
  <mxGeometry relative="1" as="geometry">
    <Array as="points">
      <mxPoint x="1000" y="500" />
    </Array>
  </mxGeometry>
</mxCell>
```

Arrow conventions:
- **Solid** = direct method call, synchronous
- **Dashed** = callback, LiveData observation, async return
- **Dashed + red** = old/bug logic, removed path, bad path
- **Solid + green + thick (strokeWidth=2)** = fix path, correct path, new logic
- Always set `entryX/entryY` and `exitX/exitY` to distribute edges on the shape perimeter

### 4. Legend box at the top

Always include a legend that explains the reading rules:

```xml
<mxCell id="4" value="大框=文件/类  小框=关键变量/状态  箭头文字=驱动流程的方法或事件" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#666666;fontSize=15;fontStyle=1;" vertex="1" parent="1">
  <mxGeometry x="..." y="80" width="800" height="44" as="geometry" />
</mxCell>
```

### 5. Bug explanation boxes at the bottom

When explaining a bug, add two side-by-side boxes:

```xml
<!-- Red box: old/bug behavior -->
<mxCell id="18" value="旧逻辑 bug 点：..." style="rounded=1;whiteSpace=wrap;html=1;fillColor=#F8CECC;strokeColor=#B85450;fontSize=15;fontStyle=1;" vertex="1" parent="1">
  <mxGeometry x="60" y="930" width="800" height="120" as="geometry" />
</mxCell>

<!-- Green box: fix behavior -->
<mxCell id="19" value="修复后：..." style="rounded=1;whiteSpace=wrap;html=1;fillColor=#D5E8D4;strokeColor=#82B366;fontSize=15;fontStyle=1;" vertex="1" parent="1">
  <mxGeometry x="960" y="930" width="800" height="120" as="geometry" />
</mxCell>
```

## Workflow

1. Read the relevant source files first — Fragment, ViewModel, Service/Manager, Repository.
2. Extract file/class names as swimlane candidates.
3. For each class, extract key variables (LiveData, list, state holder) and key methods (entry points, event handlers).
4. Trace the method call chain and identify data flow direction.
5. Propose a layout: classes left to right, variables inside, method-labeled arrows connecting them.
6. Generate a concise text blueprint internally or in the progress update, but do not ask for confirmation.
7. Generate `.drawio` directly.
8. Do not export PNG unless the user explicitly asks for PNG.

## Blueprint Format

Before generating XML, optionally show a concise text blueprint as progress, but continue generating the XML without waiting for confirmation:

```markdown
**主节点（文件/类）：**
- `CloudMusicRecommendFragment.java` (UI)
  - 子节点: observe(personalWanderLiveData), onMessageEvent(), ivPrivateRoaming
- `CloudMusicHomeRecommendViewModel.java` (ViewModel)
  - 子节点: getPersonalWanderList(), filtered List<Song>, personalWanderLiveData
- `CloudMusicPlayerService.java` (Service)
  - 子节点: next(), playNext(), curPlayingMusic/position/mCurType, mPlayList, getWanderData(), getPersonalWanderList(forceUpdate)

**箭头（方法/事件驱动）：**
- `Fragment.onMessageEvent() --CLOUD_MUSIC_EVENT_WANDER_CHANGED--> ViewModel.getPersonalWanderList(true)`
- `ViewModel --postValue(filtered)--> personalWanderLiveData`
- `personalWanderLiveData --observe--> Fragment.setImageView`
- `getWanderData() --补齐列表后 trigger--> EventBus`
```

## Color Palette

| Role | fillColor | strokeColor | example |
|------|-----------|-------------|---------|
| UI Fragment | `#F3F7FF` | `#6C8EBF` | Blue swimlane |
| ViewModel | `#F6FFF3` | `#82B366` | Green swimlane |
| Manager/Bridge | `#FFF9EC` | `#D79B00` | Orange swimlane |
| Core Service | `#FFF6F5` | `#B85450` | Red-pink swimlane |
| Repository/External | `#F5F5F5` | `#666666` | Gray swimlane |
| EventBus | `#F3F3FF` | `#9673A6` | Purple swimlane |
| Variable (cylinder) | `#D5E8D4` | `#82B366` | Green cylinder |
| UI element | `#FFF2CC` | `#D6B656` | Yellow box |
| Key method | `#DAE8FC` | `#6C8EBF` | Blue rounded |
| Bug/fix (red) | `#F8CECC` | `#B85450` | Red box |
| Fix/ok (green) | `#D5E8D4` | `#82B366` | Green box |

## File Path

- Default output dir: current working directory, or user-specified path
- Filename: use descriptive Chinese or English name ending in `.drawio`
- Export PNG only when explicitly requested: `draw.io -x -f png -e -s 2 -b 20 -o output.drawio.png input.drawio`

## Interaction Rules

- **用户必须指定文件保存路径**，否则在一句内询问："请提供保存路径（如 D:\项目笔记\D01）"
- Read source files before proposing the blueprint.
- Do not ask for blueprint confirmation; generate the `.drawio` directly after reading source files.
- Keep the first version focused; prefer 5-8 main nodes over an unreadable 20-node diagram.
- Use explicit Chinese labels for Chinese-speaking users. Use file paths (e.g., `CloudMusicRecommendFragment.java`) as swimlane titles.
- When the user rejects a diagram and asks for a file-variable-method format, switch to this skill's rules.

---

## Code Chain Diagram (代码执行链路图)

用于展示代码调用的完整链路，支持从图直接跳转到源码。

### 触发条件

- 用户说"代码链路"、"执行链路"、"调用链路"
- 用户说"追踪代码"、"理清链路"
- 用户说"画出执行流程"、"代码跳转图"

### 图结构规则

#### 1. 步骤容器 = swimlane

每个执行步骤一个容器：

```xml
<mxCell id="10" value="步骤1: Activity 播放全部按钮点击" style="swimlane;startSize=28;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;fontSize=13;" vertex="1" parent="1">
  <mxGeometry x="40" y="40" width="760" height="110" as="geometry" />
</mxCell>
```

#### 2. 文件信息块 = 黄色等宽字体块

```xml
<mxCell id="11" value="文件: modules/cloud_music/.../activity/CloudMusicPlaylistDetailActivity.java&#xa;&#xa;行号 994:  mBinding.rlIvPlayAll.setOnClickListener(view -&gt; {&#xa;行号 1011:      CloudMusicSkipManager.skip(SkipType.TYPE_PLAYER_SERVICE, ...)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;align=left;spacingLeft=10;fontFamily=Consolas;" vertex="1" parent="10">
  <mxGeometry x="20" y="35" width="720" height="65" as="geometry" />
</mxCell>
```

#### 3. 节点颜色编码

| 类型 | fillColor | strokeColor | 用途 |
|------|-----------|-------------|------|
| 入口节点 | `#dae8fc` | `#6c8ebf` | Activity、Fragment |
| 路由节点 | `#d5e8d4` | `#82b366` | Manager、Router |
| 数据节点 | `#ffe6cc` | `#d79b00` | DataHolder、Repository |
| 服务节点 | `#f8cecc` | `#b85450` | Service、Engine |
| 异常节点 | `#f8cecc` | `#b85450;fontStyle=1` | 问题发生位置（加粗） |
| 修复节点 | `#d5e8d4` | `#82b366` | 修复位置 |

#### 4. 连接箭头规范

```xml
<!-- 正常调用：绿色实线 -->
<mxCell id="20" value="跳转&#xa;1011行" style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;strokeColor=#82b366;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;fontSize=10;" edge="1" parent="1" source="10" target="30">
  <mxGeometry relative="1" as="geometry" />
</mxCell>

<!-- 跳过/未执行：红色虚线 -->
<mxCell id="70" value="跳过！" style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;dashed=1;strokeColor=#b85450;exitX=0.5;exitY=1;exitDx=0;exitDy=0;" edge="1" parent="1" source="160">
  <mxGeometry relative="1" as="geometry">
    <mxPoint x="420" y="610" as="targetPoint" />
  </mxGeometry>
</mxCell>
```

#### 5. 尺寸规范

- 容器宽度：`760`
- 容器高度：`110`（含代码块可增至 `150`）
- 间距：`130px`
- 布局：TB（从上到下）

#### 6. 必须包含的信息

每个步骤块必须包含：

1. **类名或模块名**
2. **文件相对路径**（从模块开始）
3. **关键方法名和行号**
4. **1-3行关键代码**（等宽字体）

#### 7. 禁止跳步（强制）

代码链路图必须让用户能根据图在 IDE 中一步步跳转，不能省略中间调用层。

- 每条箭头必须对应真实代码中的**直接方法调用、回调注册/触发、事件分发、条件分支或异步切换点**。
- 如果 A 最终到达 D，但源码实际是 `A -> B -> C -> D`，必须画出 B 和 C，不能直接画 `A -> D`。
- Router、Manager、ServiceManager、Binder/ServiceConnection、Handler.post、Callback、EventBus、LiveData/Flow 观察者、Repository/API 回调都必须作为独立步骤或在相邻步骤中明确标出行号。
- 遇到 `bindService().setData(...)`、链式调用、lambda、匿名回调、协程/线程切换时，要拆成可跳转的最小节点，至少标出调用发起行和接收方法行。
- 如果某一步是推断而不是已读源码确认，必须在节点中标注“推断”，并优先继续查源码补实。
- 生成前要自检：任意相邻两个节点之间，用户是否能从前一个节点的行号直接跳到后一个节点的入口；如果不能，继续补节点。

### 完整示例

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="drawio" version="26.0.0">
  <diagram name="代码链路">
    <mxGraphModel dx="900" dy="600" grid="1" gridSize="10">
      <root>
        <mxCell id="0" />
        <mxCell id="1" parent="0" />
        
        <!-- 步骤1 -->
        <mxCell id="10" value="步骤1: Activity 播放全部按钮点击" style="swimlane;startSize=28;fillColor=#dae8fc;strokeColor=#6c8ebf;fontStyle=1;fontSize=13;" vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="760" height="110" as="geometry" />
        </mxCell>
        <mxCell id="11" value="文件: modules/cloud_music/.../activity/CloudMusicPlaylistDetailActivity.java&#xa;&#xa;行号 994:  mBinding.rlIvPlayAll.setOnClickListener(view -&gt; {&#xa;行号 1011:      CloudMusicSkipManager.skip(...)" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;align=left;spacingLeft=10;fontFamily=Consolas;" vertex="1" parent="10">
          <mxGeometry x="20" y="35" width="720" height="65" as="geometry" />
        </mxCell>
        
        <!-- 步骤2 -->
        <mxCell id="30" value="步骤2: SkipManager 路由跳转" style="swimlane;startSize=28;fillColor=#d5e8d4;strokeColor=#82b366;fontStyle=1;fontSize=13;" vertex="1" parent="1">
          <mxGeometry x="40" y="170" width="760" height="130" as="geometry" />
        </mxCell>
        <mxCell id="31" value="文件: modules/cloud_music/.../router/CloudMusicSkipManager.java&#xa;&#xa;行号 98:   public static void skip(SkipType type, SkipData data) {&#xa;行号 165:      DataHolder.setData(data.getSongList());  // 写入90首&#xa;行号 189:      skipToPlayerService(...);" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=11;align=left;spacingLeft=10;fontFamily=Consolas;" vertex="1" parent="30">
          <mxGeometry x="20" y="35" width="720" height="85" as="geometry" />
        </mxCell>
        
        <!-- 连接箭头 -->
        <mxCell id="20" value="跳转&#xa;1011行" style="edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=2;strokeColor=#82b366;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;entryDx=0;entryDy=0;fontSize=10;" edge="1" parent="1" source="10" target="30">
          <mxGeometry relative="1" as="geometry" />
        </mxCell>
        
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

### 工作流程

1. **检查路径** — 用户必须指定保存路径，否则询问后停止
2. **读取源码** — 先读取相关文件，确认类名、方法名、行号
3. **提取链路** — 按真实调用顺序提取每个步骤的：文件路径、方法名、行号、关键代码；不得跳过中间 Router/Manager/Service/Callback 层
4. **链路自检** — 检查每条边是否能在源码里找到直接调用或明确回调关系；发现跳步必须补节点后再生成图
5. **生成蓝图** — 内部整理节点列表 + 边列表，可简要输出进度，但不要等待用户确认
6. **生成 XML** — 按规范生成 `.drawio` 文件到用户指定路径
7. **不导出 PNG** — 除非用户明确要求 PNG，否则只生成 `.drawio`

### 蓝图格式

生成 XML 前可整理以下文本蓝图，但不要向用户请求确认，直接继续生成 XML：

```markdown
**执行链路：**

| 步骤 | 文件 | 关键行号 | 操作 |
|------|------|----------|------|
| 1 | CloudMusicPlaylistDetailActivity.java | 994, 1011 | 按钮点击，调用SkipManager |
| 2 | CloudMusicSkipManager.java | 98, 165, 189 | 写入DataHolder，跳转服务 |
| 3 | DataHolder.java | 15, 17 | 保存播放列表 |
| 4 | CloudMusicPlayerService.java | 352, 372-376 | 判断同曲播放 |
| 5 | initPlayerData (未执行) | 445, 532-533 | 刷新队列（被跳过） |
| 6 | next() | 1208, 1249, 1251 | 下一曲计算（异常点） |

**修复位置：** CloudMusicPlayerService.java 376行之后
```

### 文件输出

- **用户必须指定保存路径**，未指定则询问："请提供保存路径（如 D:\项目笔记\D01）"
- 文件名：描述性中英文名 + `.drawio`
- PNG：默认不导出；只有用户明确要求 PNG 时才执行 draw.io CLI 导出命令
