---
name: configure-llm-gateway
description: When the user provides an LLM gateway baseURL and API key (LiteLLM proxy, OpenRouter, custom OpenAI-compatible endpoint, official Anthropic/Google/OpenAI, or self-hosted gateway) and asks to add it to OpenCode. Probes the gateway, tests model availability, detects per-model protocol (OpenAI-compat / Anthropic native / Google native), verifies provider-specific features (thinking / reasoning_effort / budget_tokens), and writes a complete, working ~/.config/opencode/opencode.json entry with appropriate variants.
---

# Configure LLM Gateway for OpenCode

When the user gives you a `baseURL` + `apiKey` (with optional model hint) and asks to configure it for OpenCode, follow this full workflow.

## Step 1: Probe the gateway

Try in order:

1. `curl baseURL/v1/models` with the key as `Authorization: Bearer <key>` — most gateways expose this.
2. If 401/404, try without `/v1`, or just hit `baseURL/` to detect a Swagger / OpenAPI page.
3. If it's a LiteLLM gateway (returns a `data: [{id, object: "model"}]` list), also try the management endpoints:
   - `GET /key/info` — current key alias, budget, spend, authorized models
   - `GET /user/info` — total user spend, list of all keys
   - `GET /v1/model/info` — per-model routing (provider, api_base, cost)
   - `GET /model_group/info` — providers configured for each model (`[]` means stub, not callable)
   - `GET /health/readiness` — version, plugins (no auth needed)

This tells you which models are real vs stubs.

## Step 2: Test each listed model

For every model, fire a minimal request and classify:

```bash
curl -s "<baseURL>/v1/chat/completions" \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"<id>","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

Mark OK / FAIL. Skip stubs (providers `[]` in LiteLLM model_group/info).

## Step 3: Detect per-model protocol

- For LiteLLM, read `/v1/model/info`: the `litellm_params.model` field reveals the underlying provider:
  - `custom_openai/...` or `openai/...` → use `@ai-sdk/openai-compatible`
  - `anthropic/...` → also try `/v1/messages` to confirm Anthropic native endpoint works
  - `vertex_ai/...` or `gemini/...` → Google
- For other gateways, infer from model name (claude → Anthropic, gpt → OpenAI, gemini → Google).
- Probe `POST baseURL/v1/messages` with an Anthropic body to confirm a Claude native path exists. If 200, prefer routing Claude models through `@ai-sdk/anthropic` so `thinking` works properly.

## Step 4: Look up each model's official feature spec

Use websearch / WebFetch on the official docs:

- Claude: which models accept `thinking: {type:"enabled", budget_tokens}` vs `thinking: {type:"adaptive"}` + `effort`? Which `effort` levels are valid (`low/medium/high/xhigh/max`)? Does it need `display: "summarized"` to actually return thinking?
- OpenAI GPT: which `reasoning_effort` levels are valid (`none/low/medium/high/xhigh`)?
- Gemini: `thinking_level` (`low/medium/high`, no `minimal` on Pro) — but via OpenAI compat the SDK maps `reasoning_effort` to `thinking_level`.

Don't guess defaults — official limits change across versions.

## Step 5: Implementation-test the feature parameters

For each provider-specific parameter (thinking, effort, budget_tokens), send a real request to the gateway and check whether the upstream actually honors it. Some proxies accept the field silently but the upstream model doesn't respond — observe `reasoning_tokens` / `thinking_content` length, not just HTTP 200.

Examples that have failed in past sessions:
- Wangsu GPT-5.4 accepts `reasoning_effort` but `reasoning_tokens` stays 0 → don't add variants
- Opus 4.7 returns `display: "omitted"` by default → must set `display: "summarized"` in config
- Opus 4.7 rejects `budget_tokens` with 400 → must use `adaptive` + `effort`

If a parameter doesn't actually work end-to-end, leave it out of the variants. Misleading config is worse than no config.

## Step 6: Group models into providers

Each entry in `provider` must use a single `npm` package. Don't mix Claude and GPT under one OpenAI-compatible provider — split them:

- `litellm-openai` (`@ai-sdk/openai-compatible`) — GPT, Gemini, GLM, MiniMax, etc.
- `litellm-claude` (`@ai-sdk/anthropic`) — Claude models, when `/v1/messages` is available
- One provider per API key. If the user has multiple keys with different scopes, give each its own provider entry with a clear name suffix.

baseURL rules:
- `@ai-sdk/openai-compatible` → baseURL ends with `/v1`
- `@ai-sdk/anthropic` → baseURL also ends with `/v1` (it appends `/messages`)
- For Anthropic provider, always include both `apiKey` and `headers.x-api-key` + `anthropic-version: 2023-06-01` for max compatibility with proxies.

## Step 7: Write the config

Read existing `~/.config/opencode/opencode.json` first, merge the new providers, don't overwrite unrelated keys like `permission` or existing providers. Keep the `model` default unchanged unless user asks.

## Step 8: Report

Tell the user:
- Which models actually work (table)
- Which protocol each routes through
- Which provider-specific features were verified to actually work
- Anything dropped (stub models, non-honored params)
- How to switch / set default

Skip restart instructions unless asked.

## Anti-patterns

- Don't trust `/v1/models` listing alone — many entries are stubs.
- Don't configure `budget_tokens` on Opus 4.7 / Mythos.
- Don't put Claude models under `@ai-sdk/openai-compatible` if `/v1/messages` exists — you lose `thinking` block separation.
- Don't add variants for features the gateway doesn't actually respect.
- Don't append `>>` to opencode.json — always read, merge in memory, write the whole file.
