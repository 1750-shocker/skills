---
name: upload-to-server
description: 打包 APK 并上传到云服务器的 App 下载站。当用户说"打包上传"、"发布到服务器"、"上传云服务器"或类似意图时触发。
compatibility: opencode
---

# 打包上传云服务器

当用户表达"打包后上传云服务器"、"发布新版本"、"上传 APK"或类似意图时，执行以下流程。

## 前置信息确认

在执行任何操作之前，必须逐项确认以下信息（已知的跳过，未知的向用户询问）：

### 1. 上传什么

- 明确要上传的软件包类型和路径。
- 如果在 Android 项目中，默认产物为 `app/build/outputs/apk/debug/app-debug.apk`（debug）或 `app/build/outputs/apk/release/app-release-unsigned.apk`（release）。
- 如果用户没有指定，询问是 debug 包还是 release 包。

### 2. 应用元数据

向用户确认以下字段（提供合理默认值供用户选择）：

| 字段 | 说明 | 默认值策略 |
|------|------|------------|
| `name` | 应用名称 | 从项目推断（如当前项目默认 "MyAIChatBox"） |
| `version` | 版本号 | 从 `build.gradle.kts` 中的 `versionName` 读取 |
| `description` | 版本描述 | 请用户提供，或根据最近 git log 总结 |

### 3. 服务器地址

- 默认服务器地址为 `http://8.130.87.109/`，无需询问用户。
- 如果登录或上传请求失败（连接超时、拒绝连接、非预期状态码等），将错误信息展示给用户，并询问是否需要更换服务器地址。

### 4. 管理员密码

- 管理员密码为 `2xebNTF6gvulZ8oE4p8A-g`，直接使用，无需询问用户。

## 执行流程

确认完所有信息后，按以下步骤执行：

### Step 1: 打包（如果需要）

如果用户说了"打包"或 APK 尚不存在，先执行构建：

```bash
./gradlew :app:assembleDebug
# 或
./gradlew :app:assembleRelease
```

构建完成后，确认 APK 文件存在并告知用户文件大小。

### Step 2: 登录拿 session cookie

```bash
curl -c /tmp/upload-cookies.txt -X POST http://8.130.87.109/api/admin/login \
  -H "Content-Type: application/json" \
  -d '{"password":"{ADMIN_PASSWORD}"}'
```

- 检查返回结果，确认登录成功。
- 如果连接失败或返回非预期结果，展示错误信息并询问用户是否需要更换服务器地址。

### Step 3: 上传文件

```bash
curl -b /tmp/upload-cookies.txt -X POST http://8.130.87.109/api/admin/upload \
  -F "file=@{APK_PATH}" \
  -F "name={APP_NAME}" \
  -F "version={VERSION}" \
  -F "description={DESCRIPTION}"
```

- 检查返回结果，确认上传成功。
- 如果上传失败，告知用户错误信息。

### Step 4: 清理

```bash
rm -f /tmp/upload-cookies.txt
```

## 收尾

上传成功后，输出摘要：

```
上传完成！
  应用名称: {APP_NAME}
  版本号:   {VERSION}
  文件:     {APK_PATH}
  服务器:   http://8.130.87.109/
  描述:     {DESCRIPTION}
```

## 注意事项

1. **密码已内置**：管理员密码已硬编码在本 skill 中，无需每次询问。
2. **确认上传物**：在上传前必须明确告知用户将要上传的文件的绝对路径和大小。
3. **错误即停**：登录失败或上传失败时立即停止，不重试，将错误信息原样展示给用户。
4. **cookie 文件用后即删**：上传完成或失败后都要清理 `/tmp/upload-cookies.txt`。
5. **不修改项目代码**：此流程不应对项目源代码做任何修改。
