# Engineering harnesses and fallback strategy

Codex + GPT-6 Astra is the primary engineering harness. OpenCode + GLM 5.3 is the
first fallback harness; OpenCode + Qwen 3.8 is the second fallback harness.
GLM 5.3 and Qwen 3.8 are not Codex model-brain fallback profiles: each harness
has its own writer identity, and switching from Codex to OpenCode is an explicit
writer handoff (see [failover](AGENT_FAILOVER.md)).

## Harness order

| Precedence | Harness | Model | Writer | Use |
| --- | --- | --- | --- | --- |
| 0 | Codex | gpt-6-astra (Codex/ChatGPT authentication) | codex | Primary engineering harness |
| 1 | OpenCode | GLM 5.3 (Cloudflare @cf/zai-org/glm-5.3) | glm | First fallback harness |
| 2 | OpenCode | Qwen 3.8 27B (Cloudflare @cf/qwen/qwen3.8-27b) | qwen | Second fallback harness |

Kimi K3 (Nebius) remains the source/data researcher and Nemotron Ultra (Nebius)
remains adversarial QA; neither is an engineering harness. The registry lives in
`src/agents/harness.py` and is covered by tests: the fallback order matches the
frozen writer priority prefix (codex -> glm -> qwen), and every harness switch
changes the writer identity and therefore requires the human-approved writer
handoff.

## Selection

Harnesses are selected with the `KEMIRIX_ENGINEERING_HARNESS` environment
variable (unset means the primary Codex + GPT-6 Astra harness):

```sh
KEMIRIX_ENGINEERING_HARNESS=opencode-glm-5.3
KEMIRIX_ENGINEERING_HARNESS=opencode-qwen-3.8-27b
```

Unknown names fail closed; the selection variable never contains a credential.
No API keys are placed in Git or committed harness configuration. The primary
harness uses Codex's normal ChatGPT authentication (never broken by this
setup). The OpenCode harness is configured in `opencode.json`, which references
the Cloudflare credential by environment variable only (`{env:CLOUDFLARE_API_TOKEN}`)
and exposes the GLM 5.3 and Qwen 3.8 models; secret values stay VM-side
(/etc/kemirix/agents.env).

## Fallback procedure

When the primary harness is unavailable (for example Astra/Codex quota is low
or exhausted), switch to OpenCode + GLM 5.3 through the human-approved writer
handoff in [failover](AGENT_FAILOVER.md): stop Codex at a clean recorded
checkpoint, then hand off to writer glm. The handoff preserves the same task,
branch, base/HEAD SHA, Git-backed memory, reports and deterministic coordinator
state; the replacement writer resumes at the exact recorded checkpoint on the
task branch. If the first fallback harness is also unavailable, hand off again
to OpenCode + Qwen 3.8 (writer qwen). Returning to the primary harness likewise
requires another explicit writer handoff.

No fallback harness has been executed yet; this is configuration strategy
plus tested profile resolution, not an executed provider PASS.
