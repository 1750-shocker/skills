---
name: optimize-config
description: When the user asks to optimize OpenCode configuration, permanently enable network access (websearch and webfetch), permanently write the OPENCODE_ENABLE_EXA environment variable to the shell profile, and remap the Ctrl+C keybinding so that it only clears the input box without exiting the application.
---

# Optimize OpenCode Config

When the user asks to optimize their OpenCode configuration, enable network access, persist the Exa web search environment variable, and configure Ctrl+C to only clear the input.

Follow these steps exactly:

## Step 1: Enable Network Access

Read and update `~/.config/opencode/opencode.json` (create if it doesn't exist). Ensure the `permission` block contains:
```json
"permission": {
  "websearch": "allow",
  "webfetch": "allow"
}
```
Merge this safely without destroying existing configuration (like `provider`, `model`, etc.).

## Step 2: Persist the Web Search Environment Variable

Append the environment variable to the user's shell profile to enable the Exa search tool permanently across terminal sessions.
Execute:
```bash
echo 'export OPENCODE_ENABLE_EXA=1' >> ~/.bashrc
```
(Check if it already exists first to avoid duplicates using `grep -q "OPENCODE_ENABLE_EXA" ~/.bashrc`).

## Step 3: Configure Keybinds

Read and update the TUI configuration file `~/.config/opencode/tui.json` (create if it doesn't exist).

To prevent `Ctrl+C` from exiting the app and make it ONLY clear the input, you need to:
1. Remove `ctrl+c` from `app_exit`.
2. Ensure `ctrl+c` is assigned to `input_clear`.

Add or update the `keybinds` object:
```json
{
  "$schema": "https://opencode.ai/tui.json",
  "keybinds": {
    "app_exit": "ctrl+d,<leader>q",
    "input_clear": "ctrl+c"
  }
}
```

## Step 4: Report Completion

Tell the user that:
1. Network access (web search and fetch) is permanently enabled.
2. `OPENCODE_ENABLE_EXA=1` is written to `~/.bashrc`.
3. `Ctrl+C` is now safely mapped to only clear the input box (use `Ctrl+D` or `<leader>q` to exit).
4. They need to restart OpenCode and open a new terminal (or `source ~/.bashrc`) for the changes to take effect.
