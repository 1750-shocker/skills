---
name: notebox
description: Use when the user asks to save text, conclusions, logs, snippets, clipboard content, current-chat summaries, or update local Notebox URL/token settings.
---

# Notebox

Save text to the private cloud Notebox through the PowerShell script in this skill's `scripts` directory. Use this skill when the user says things like:

- 保存这段文本
- 把结论存到 notebox
- 记到云端笔记
- 保存到手机可看的网页
- 保存剪贴板内容
- 把这段日志/代码/总结存一下
- 更新 notebox token 或地址
- 重新配置云端保存 token

## Behavior

- Collect the exact text to save.
- Choose a concise title when useful; do not invent details.
- Use source `omp` unless the user specifies another source.
- Use tags only when obvious, such as `ai`, `log`, `code`, `summary`, or `clipboard`.
- Call the bundled PowerShell script at `scripts/save-note.ps1` relative to this skill directory.
- For Chinese, long, or quote-heavy content, write the body to a temporary UTF-8 file and call `scripts/save-note.ps1 -ContentFile <path>`; do not splice the body directly into a command-line argument.
- Never print, persist, or request `NOTEBOX_TOKEN`.
- Never call the Notebox HTTP API directly from this skill; the script owns transport and credentials.
- If saving the current conversation, summarize only when the user asks for a summary; otherwise save the requested text verbatim.
- On success, return only a short success message with id and created_at.

## Commands

Save explicit content. Prefer `-ContentFile` for non-ASCII, long, or quote-heavy text:

```powershell
$contentPath = Join-Path $env:TEMP "notebox-content.txt"
[System.IO.File]::WriteAllText($contentPath, "<content>", [System.Text.Encoding]::UTF8)
& "$PSScriptRoot\scripts\save-note.ps1" -Title "<title>" -ContentFile $contentPath -Source "omp" -Tags "ai"
```

Save clipboard:

```powershell
Get-Clipboard | & "$PSScriptRoot\scripts\save-note.ps1" -Title "<title>" -Source "clipboard" -Tags "clipboard"
```

For short ASCII content, `-Content` is acceptable. For Chinese, long, multiline, or quote-heavy content, always use a temporary UTF-8 file with `-ContentFile`. The bundled script sets UTF-8 console encodings and reads `NOTEBOX_URL` and `NOTEBOX_TOKEN` from the local environment.

## Updating URL or Token

When the user asks to update the Notebox token or URL:

- Treat the new token as sensitive secret material.
- Do not write the token into this skill file, logs, notes, or chat output.
- Update only the Windows user environment variable.
- Also set the current PowerShell session variable when verifying in the same terminal.
- Mask the token in all responses, for example `sk-...abcd` or `<updated>`.
- After updating, run a small save verification through `scripts/save-note.ps1`.

Update token:

```powershell
[Environment]::SetEnvironmentVariable('NOTEBOX_TOKEN', '<new-token>', 'User')
$env:NOTEBOX_TOKEN = '<new-token>'
```

Update URL:

```powershell
[Environment]::SetEnvironmentVariable('NOTEBOX_URL', '<new-url>', 'User')
$env:NOTEBOX_URL = '<new-url>'
```

Verify after update:

```powershell
& "$PSScriptRoot\scripts\save-note.ps1" -Title "Notebox 配置验证" -Content "Notebox token or URL update verification." -Source "omp" -Tags "verify"
```

Success response for token updates:

- Notebox token updated in Windows user environment.
- Current session updated for verification.
- Verification saved: id <id>, created_at <created_at>.

## Success Response

Return:

- Saved to Notebox.
- id: <id>
- created_at: <created_at>

## Failure Response

- State the script error without printing token values.
- If `NOTEBOX_URL` or `NOTEBOX_TOKEN` is missing, ask the user to reopen the terminal or set the local environment variables again.
