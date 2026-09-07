"""Small HTTP adapters. No filesystem tools, automatic writer switching or clinical approval."""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

MODELS = {
    "kimi": ("nebius", "KIMI_MODEL", "moonshotai/Kimi-K3"),
    "nemotron": ("nebius", "NEMOTRON_MODEL", "nvidia/nemotron-3-ultra-550b-a55b"),
    "glm": ("cloudflare", "GLM_MODEL", "@cf/zai-org/glm-5.3"),
    "qwen": ("cloudflare", "QWEN_MODEL", "@cf/qwen/qwen3.8-27b"),
}
SMOKE_PROMPT = 'Return only this minimal JSON object confirming connectivity: {"connectivity":"ok"}'


class ProviderError(RuntimeError):
    """Only safe category strings cross the provider boundary."""


@dataclass(frozen=True)
class SmokeResult:
    provider: str
    status: str
    detail: str


def classify(status):
    if status in (401, 403):
        return "authentication_or_permission"
    if status == 429:
        return "rate_limit_or_quota"
    if status == 404:
        return "model_or_endpoint_unavailable"
    if status >= 500:
        return "provider_unavailable"
    return "invalid_request"


class CodexExternalWriter:
    def smoke(self, timeout=15):
        executable = shutil.which("codex")
        if not executable:
            raise ProviderError("cli_not_installed")
        try:
            for args in ([executable, "--version"], [executable, "login", "status"]):
                # Suppress even authenticated identity details; do not launch a model request.
                result = subprocess.run(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout,
                    check=False,
                )
                if result.returncode:
                    raise ProviderError("cli_or_authentication_unavailable")
        except subprocess.TimeoutExpired:
            raise ProviderError("timeout") from None
        return SmokeResult("codex", "PASS", "CLI and login status only; inference quota unverified")


CodexProvider = CodexExternalWriter


class HTTPProvider:
    def __init__(self, env=None, transport=None, timeout=30):
        self.env = os.environ if env is None else env
        self.transport = transport
        self.timeout = timeout

    def required(self, name):
        value = self.env.get(name)
        if not value:
            raise ProviderError("missing_configuration")
        return value

    def post(self, url, token, payload):
        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                with client.stream(
                    "POST",
                    url,
                    headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "identity"},
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        raise ProviderError(classify(response.status_code))
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise ProviderError("unsupported_response_encoding")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 262144:
                            raise ProviderError("response_too_large")
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError("object response required")
                    return data
        except httpx.TimeoutException:
            raise ProviderError("timeout") from None
        except httpx.HTTPError:
            raise ProviderError("network_or_tls") from None
        except (ValueError, KeyError, TypeError):
            raise ProviderError("invalid_response") from None

    def smoke(self, role):
        try:
            content = self.complete(role, SMOKE_PROMPT, max_tokens=128)
            if json.loads(content) != {"connectivity": "ok"}:
                raise ValueError()
        except (ValueError, TypeError, KeyError, IndexError):
            raise ProviderError("invalid_smoke_response") from None
        return SmokeResult(role, "PASS", "minimal JSON connectivity response validated")


class NebiusProvider(HTTPProvider):
    def complete(self, role, prompt, max_tokens=2048):
        from .security import ensure_no_secrets

        ensure_no_secrets(prompt)
        if role not in ["kimi", "nemotron"]:
            raise ProviderError("invalid_role")
        # Operators may select either official endpoint; never forward keys to arbitrary hosts.
        base = self.env.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1").rstrip("/")
        parsed = urlsplit(base)
        if (
            parsed.scheme != "https"
            or parsed.hostname
            not in ["api.tokenfactory.nebius.com", "api.studio.nebius.com", "api.studio.nebius.ai"]
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.port not in [None, 443]
        ):
            raise ProviderError("invalid_endpoint")
        _, key, default = MODELS[role]
        data = self.post(
            base + "/chat/completions",
            self.required("NEBIUS_API_KEY"),
            {
                "model": self.env.get(key, default),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, TypeError, IndexError):
            raise ProviderError("invalid_response") from None


class CloudflareProvider(HTTPProvider):
    def complete(self, role, prompt, max_tokens=2048):
        from .security import ensure_no_secrets

        ensure_no_secrets(prompt)
        if role not in ["glm", "qwen"]:
            raise ProviderError("invalid_role")
        account = self.required("CLOUDFLARE_ACCOUNT_ID")
        if not re.fullmatch("[0-9a-fA-F]{32}", account):
            raise ProviderError("invalid_account_configuration")
        _, key, default = MODELS[role]
        model = self.env.get(key, default)
        if not re.fullmatch(r"@cf/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+", model):
            raise ProviderError("invalid_model_configuration")
        data = self.post(
            f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}",
            self.required("CLOUDFLARE_API_TOKEN"),
            {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        if data.get("success") is not True:
            raise ProviderError("provider_rejected_request")
        try:
            return data["result"]["response"]
        except (KeyError, TypeError):
            raise ProviderError("invalid_response") from None


def provider_for(role, **kwargs):
    if role == "codex":
        return CodexExternalWriter()
    if role not in MODELS:
        raise ProviderError("invalid_role")
    return (NebiusProvider if MODELS[role][0] == "nebius" else CloudflareProvider)(**kwargs)
