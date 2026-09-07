# Provider configuration and smoke checks

CodexExternalWriter uses the installed Codex CLI's `--version` and `login status` exit status. Codex is authenticated separately through ChatGPT; OPENAI_API_KEY is neither required nor read by this adapter. A CLI/authentication PASS does not prove inference quota or remaining credits.

| Role | Adapter | Default model | Environment references |
| --- | --- | --- | --- |
| KIMI | Nebius | moonshotai/Kimi-K3 | NEBIUS_API_KEY, optional NEBIUS_BASE_URL, KIMI_MODEL |
| NEMOTRON | Nebius | nvidia/nemotron-3-ultra-550b-a55b | NEBIUS_API_KEY, optional NEBIUS_BASE_URL, NEMOTRON_MODEL |
| GLM | Cloudflare | @cf/zai-org/glm-5.3 | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, GLM_MODEL |
| QWEN | Cloudflare | @cf/qwen/qwen3.8-27b | CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN, QWEN_MODEL |

These are the owner's requested identifiers. Availability and entitlement are unverified; do not silently substitute another model. Nebius defaults to its official Token Factory /v1 endpoint and allows explicit official legacy endpoints; configure the account's endpoint VM-side if needed. Cloudflare uses the Workers AI REST run endpoint. No SDK or model framework is added.

```sh
uv run python scripts/provider-smoke-test.py --provider codex
uv run python scripts/provider-smoke-test.py --provider kimi
uv run python scripts/provider-smoke-test.py --all
```

API checks use only a synthetic minimal-JSON connectivity prompt, temperature zero and bounded output. They have timeouts and safe error categories (configuration, authentication/permission, rate/quota, model/endpoint, timeout, network/TLS, malformed response). Raw provider error bodies, headers, keys and model replies are never printed. A failed requested role causes a nonzero exit status. No check has been performed simply because the script exists.

## Root-protected credential injection

Do not read or source /etc/kemirix/agents.env in an agent shell; never weaken its permissions. After reviewing an exact deployed/trusted foundation release, an operator may use systemd-run to read the root-owned EnvironmentFile and drop to a dedicated unprivileged agent user before running the smoke command. Example administrative pattern (replace kemirix-agent with the provisioned account):

```sh
sudo systemd-run --wait --pipe --collect \
  -p User=kemirix-agent \
  -p EnvironmentFile=/etc/kemirix/agents.env \
  -p WorkingDirectory=/srv/kemirix/runtime/development/current \
  /srv/kemirix/runtime/development/current/.venv/bin/python \
  scripts/provider-smoke-test.py --provider kimi
```

The code being given credentials must be a reviewed immutable release, not an arbitrary agent-writable script. Restrict any delegated sudo wrapper to this fixed trusted command and an allowlisted provider argument; never grant unrestricted systemd-run or shell sudo to agents. Use the Codex-authenticated Unix user for the separate Codex check; the API account need not have Codex credentials. Record only redacted role/status/date results in a reviewed report. This documentation does not run the command or read the secret file.

References: [Codex CLI reference](https://developers.openai.com/codex/cli/reference), [Nebius quickstart](https://docs.tokenfactory.nebius.com/quickstart), [Cloudflare REST API](https://developers.cloudflare.com/workers-ai/get-started/rest-api/).
