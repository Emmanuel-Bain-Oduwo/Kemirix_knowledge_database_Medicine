"""Engineering harness chain. Switching harnesses is an explicit writer handoff.

Codex + GPT-6 Astra is the primary engineering harness. OpenCode + GLM 5.3 is the
first fallback harness; OpenCode + Qwen 3.8 is the second fallback harness. GLM
5.3 and Qwen 3.8 are not Codex model-brain fallback profiles: every harness has
its own writer identity, so switching from Codex to OpenCode is a human-approved
writer handoff that preserves the same task, branch, base/HEAD SHA, Git-backed
memory, reports and deterministic coordinator state (see agents.tasks.handoff
and docs/AGENT_FAILOVER.md). Profiles carry no secret values; credentials stay
VM-side (/etc/kemirix/agents.env) or in each harness's own authentication.
"""

import os
from dataclasses import dataclass

SELECTION_ENV = "KEMIRIX_ENGINEERING_HARNESS"
PRIMARY = "codex-gpt-6-astra"


@dataclass(frozen=True)
class HarnessProfile:
    name: str
    harness: str
    model: str
    writer: str
    precedence: int


REGISTRY: dict[str, HarnessProfile] = {
    profile.name: profile
    for profile in [
        # Primary harness: ChatGPT-authenticated Codex; no API key in Git.
        HarnessProfile("codex-gpt-6-astra", "codex", "gpt-6-astra", "codex", 0),
        # First fallback harness: OpenCode running GLM 5.3 via Cloudflare.
        HarnessProfile("opencode-glm-5.3", "opencode", "@cf/zai-org/glm-5.3", "glm", 1),
        # Second fallback harness: OpenCode running Qwen 3.8 via Cloudflare.
        HarnessProfile("opencode-qwen-3.8-27b", "opencode", "@cf/qwen/qwen3.8-27b", "qwen", 2),
    ]
}


def fallback_chain():
    return sorted(REGISTRY.values(), key=lambda p: p.precedence)


def profile_for(name=None, env=None):
    """Resolve a harness profile by name, or from the selection environment.

    Unset selection means the primary Codex + GPT-6 Astra harness. Unknown names
    fail closed. No credential values are read, required or logged by this module.
    """
    if name is None:
        env = os.environ if env is None else env
        name = env.get(SELECTION_ENV) or PRIMARY
    if name not in REGISTRY:
        valid = ", ".join(p.name for p in fallback_chain())
        raise ValueError(f"unknown engineering harness; valid: {valid}")
    return REGISTRY[name]


def writer_identity(profile):
    """The production writer behind a harness; each harness has its own writer."""
    return profile.writer


def is_writer_handoff(old, new):
    """True when switching harnesses changes the writer and requires a handoff."""
    return old.writer != new.writer
