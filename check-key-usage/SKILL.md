---
name: check-key-usage
description: When the user asks to check usage/balance/spend/quota, key permissions, model accessibility, or whether configured providers use the correct protocol/parameters. Reads ~/.omp/agent/models.yml, queries gateway management endpoints (LiteLLM /key/info, /user/info, OpenRouter /api/v1/auth/key, etc.), and can validate configured models with protocol-specific probes plus runtime CLI checks.
---

# Check Key Usage

When user asks anything like "查一下当前 key 的用量"、"看下消费"、"还剩多少额度"、"check my balance"、"我这个 key 还能用多久"、"检查模型是否可访问"、"看看 SDK/请求参数是否正确"、etc., follow this workflow.

This skill has two modes:

1. **Usage mode**: check spend, quota, owner, authorized models, reset time, and recent activity.
2. **Access/config mode**: check whether configured OpenCode models are actually callable, whether each provider uses the right AI SDK package, and whether request parameters match the endpoint/protocol.

## Step 1: Identify ALL configured keys and models

1. Read `~/.omp/agent/models.yml`.
2. Under `providers`, inspect every provider with both `baseUrl` and `apiKey`.
3. Resolve each provider `apiKey` using OMP's current rules:
   - if the value names an existing environment variable, use that env var's value
   - if the value starts with `!`, run the command and use trimmed stdout
   - otherwise treat the value itself as the literal key
4. For each unique resolved key, record:
   - masked key
   - `baseUrl` (strip `/v1` suffix for management endpoints)
   - provider ID(s) using the key
   - provider `api` value
   - all configured model IDs under that provider
5. **Default behavior: ALWAYS query ALL unique resolved keys**, not just the active model's key.
6. If user explicitly asks about only one specific key/provider, then query just that one.

Typical current providers in `models.yml`:

| apiKey field | Provider IDs | Base URL | Notes |
|---|---|---|---|
| `AL_API_KEY` | autolink | `https://cc.auto-link.com.cn/pro/v1` | resolve env var first, then query relay usage endpoints |
| `DEEPSEEK_API_KEY` | deepseek | `https://api.deepseek.com` | direct provider; spend check is console-only unless a relay is introduced |
If the model in use is from a native provider (Anthropic/OpenAI/Google direct), tell the user usage check has to happen on the provider's web console — no programmatic endpoint for individual key spend. Stop here.

If the user asks about model accessibility or SDK correctness, do **not** stop after usage endpoints. Continue to Step 5 and Step 6.

## Step 2: Query all keys in parallel

For each unique resolved API key, fire `/key/info` and `/user/info` requests **in parallel** when the resolved `baseUrl` is a relay that exposes them. Use the actual resolved key value in request headers, but never print it back to the user. For the current `autolink` provider, after stripping `/v1`, make these requests:

1. `GET https://cc.auto-link.com.cn/pro/key/info` with `Bearer <resolved AL_API_KEY>`
2. `GET https://cc.auto-link.com.cn/pro/user/info` with `Bearer <resolved AL_API_KEY>`

If multiple relay-backed providers resolve to different keys, do the same for each unique key. For direct vendors like `https://api.deepseek.com`, skip these relay endpoints and report that spend must be checked in the vendor console.

### Gateway endpoint reference
```
GET <baseURL>/key/info          → key metadata, alias, budget, spend, models
GET <baseURL>/user/info         → total user spend across all keys, list of sibling keys
GET <baseURL>/v1/model/info     → per-model cost & routing
GET <baseURL>/global/spend/logs → admin-only, usually 401
```
Note: baseURL might end with `/v1`. The management endpoints sit at the root, not under `/v1`. So if `baseURL = https://x.com/pro/v1`, try `https://x.com/pro/key/info` (strip `/v1`).

All require `Authorization: Bearer <key>`.

### OpenRouter
```
GET https://openrouter.ai/api/v1/auth/key   → usage, limit, label, free/pro tier
GET https://openrouter.ai/api/v1/credits    → balance
```

### Anthropic / OpenAI / Google official APIs
These do NOT expose per-key spend via API. Direct the user to:
- Anthropic: https://console.anthropic.com/settings/usage
- OpenAI: https://platform.openai.com/usage
- Google AI Studio: https://aistudio.google.com/app/usage

### Other relays (302.AI, AnyRouter, etc.)
Try `/api/key/info`, `/v1/dashboard/billing/credit_grants`, `/v1/dashboard/billing/usage`. If nothing matches, fall back to GET `/v1/models` to confirm the key works, then tell user no usage endpoint was found.

## Step 3: Aggregate and present

Build a clear summary table with at minimum:

| Field | Value |
|---|---|
| Key alias / name | from key_name or key_alias |
| Owner / user_id | from user_id |
| Total budget | max_budget |
| Period | budget_duration (1d / 30d / unlimited) |
| Current spend (this period) | spend |
| Remaining | budget − spend |
| Resets at | budget_reset_at |
| Authorized models | models array |
| TPM/RPM limit | tpm_limit / rpm_limit if set |
| Last active | last_active timestamp |
| Created | created_at |

Then add a **user-level rollup** if available (from /user/info):
- Lifetime total spend across all keys
- A detailed breakdown of EVERY key the user owns: Key alias, this period's spend, and remaining budget (if budget info is available in /user/info).

Finally, ALWAYS include a **comparison table of all configured resolved keys** at the end:

| | Key A (`sk-...xxxx`) | Key B (`sk-...yyyy`) |
|---|---|---|
| 别名 | (from key_alias) | (from key_alias) |
| 用途 | provider IDs / relay purpose | provider IDs / relay purpose |
| 今日已用 | $X.XX | $X.XX |
| 今日剩余 | $X.XX | $X.XX |
| 累计总消费 | $X.XX | $X.XX |

This comparison table is mandatory — do NOT skip it.

If the user specifically asks to "查一下所有 key" or "看看其他 key", or simply says "查用量"/"查一下用" without specifying which key, check ALL configured resolved keys (this is the default behavior).

When asked to check all configured keys, extract every unique resolved `apiKey` and its `baseUrl` from `models.yml`, strip `/v1` from relay URLs, and query `/key/info` for each relay-backed key. Present a combined table comparing them (User ID, Alias, Spend, Remaining). If `models.yml` only resolves to one relay-backed key, still include the single-key comparison table and mention any direct-vendor providers separately.

If router_settings / fallbacks are configured on the key, mention them — they affect what actually runs.

If pricing data is available (from /v1/model/info input_cost_per_token), optionally translate "$X already spent" into approximate token volume to give the user intuition.

## Step 4: Sanity checks for usage data

- If `spend > max_budget * 0.8`, warn the user they're close to budget cap.
- If `budget_reset_at` is in the past, note the reset already happened (current `spend` may be stale).
- If the key returned 401 on /key/info but works for /chat/completions, say so — usage endpoint not exposed.
- If model_group/info shows `providers: []` for any authorized model, mention those are stubs.

## Step 5: Validate SDK/protocol fit when asked about model access

Use the provider's `api` field to infer the intended protocol. Do not assume every model under the same gateway uses the same endpoint.

| Provider `api` | Intended protocol | Probe endpoint | Minimal probe payload |
|---|---|---|---|
| `openai-completions` | OpenAI-compatible chat/completions | `<baseURL>/chat/completions` | `{ "model": "...", "messages": [{ "role": "user", "content": "Reply OK only." }], "max_tokens": 16, "stream": false }` |
| `openai-responses` | OpenAI Responses API | `<baseURL>/responses` | `{ "model": "...", "input": [{ "role": "user", "content": "Reply OK only." }], "max_output_tokens": 16, "stream": false }` |
| `openai-codex-responses` | OpenAI Codex/Responses API | `<baseURL>/responses` | `{ "model": "...", "input": [{ "role": "user", "content": "Reply OK only." }], "max_output_tokens": 16, "stream": false }` |
| `anthropic-messages` | Anthropic Messages API | `<baseURL>/messages` | `{ "model": "...", "max_tokens": 16, "messages": [{ "role": "user", "content": "Reply OK only." }] }` |

Rules learned from the gateway check:

- If `/chat/completions` returns fast with `Unknown items in responses API response`, the model may still be valid but belongs under a responses-style `api` (`openai-responses` or `openai-codex-responses`) instead of `openai-completions`.
- If `/responses` succeeds quickly while `/chat/completions` fails, recommend moving or duplicating that model under a responses-style provider config, not deleting the model.
- If the runtime CLI succeeds for `provider/model`, treat the model as accessible even if the raw probe failed; the client may transform prompts differently than the manual probe.
- If the runtime CLI times out at 120 seconds, retry once with 300 seconds before declaring it unavailable. Report slow/unstable separately from unavailable.
- If the gateway returns `key not allowed to access model`, this is a key permission/model ID issue, not an SDK issue.
- If the gateway returns `This model is not available in your region`, this is a provider/region restriction.
- If the authorized models list contains a near match (for example `glm-5` but config has `glm5`), call out the exact model ID typo.

## Step 6: Validate model invocation through OpenCode

When the user asks "是否都可访问" or "SDK/参数是否正确", verify selected or all configured models through OpenCode itself:

```bash
opencode run "Reply with exactly: OK" -m "provider/model" --variant high
```

Use `--variant` only when checking variant parameters. Otherwise omit it to test the base model first.

Interpret results carefully:

- `OK` or exit code 0 with sensible output: accessible.
- Exit code 0 with empty output: reachable, but output/parsing may be suspicious; mark as "needs manual confirmation".
- HTTP 401/403 with key/model message: key permission problem.
- HTTP 500 with LiteLLM fallback/model-group text: usually gateway routing/protocol/model-group mismatch.
- Timeout: retry with a longer timeout and then label as slow/unstable, not immediately unavailable.

## Step 7: Validate request parameters and variants

Check `models.yml` compatibility settings against the provider `api` style:

- `openai-completions`: validate `compat.maxTokensField`, `compat.supportsReasoningEffort`, `compat.reasoningEffortMap`, and `compat.extraBody` when present.
- `openai-responses` / `openai-codex-responses`: validate the model through the runtime CLI first; if extra request shaping is needed, prefer `compat.extraBody` or provider/model headers over inventing a second config path.
- `anthropic-messages`: `disableStrictTools: true` is often required for Anthropic-compatible relays that reject `strict`; verify tool calls against the real endpoint.
- `authHeader: true` means the resolved key should be injected as `Authorization: Bearer <key>`; mismatches here are auth wiring bugs, not model bugs.
- If the runtime also has per-variant reasoning knobs elsewhere, validate them with the runtime CLI after the base `models.yml` transport is confirmed.

When reporting, separate these categories:

1. **Accessible and correctly configured**
2. **Accessible but better under another SDK/protocol**
3. **Model ID typo or key permission issue**
4. **Region/provider restriction**
5. **Slow/unstable, needs longer timeout or manual retest**

## Step 8: Respect privacy

Never echo the full API key back. Show only the masked form `sk-...xxxx` (last 4 chars), which is what /key/info already returns.

## Don't

- Don't list raw JSON dumps — always summarize into a table.
- Don't combine multiple users' data into one view unless user explicitly asks.
- Don't claim a number is "real-time" — LiteLLM spend can lag a few seconds after a request.
- Don't try to fetch `/global/spend/logs` — it requires admin and will always fail for user keys; mention it's admin-only and skip.
