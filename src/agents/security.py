"""Conservative common-pattern checks; not a substitute for keeping secrets outside Git."""

import re
from pathlib import Path

PATTERNS = [
    re.compile(
        r"(?im)^[A-Z0-9_]*(?:API_KEY|API_TOKEN|PASSWORD|SECRET)[A-Z0-9_]*"
        r"[ \t]*=[ \t]*[\"\x27]?[A-Za-z0-9_+./=-]{20,}"
    ),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r'(?i)authorization\s*[:=]\s*["\x27]?bearer\s+[A-Za-z0-9._-]{12,}'),
    re.compile(
        r'(?i)(?:api_key|api_token|password|secret_access_key)\s*[:=]\s*["\x27][A-Za-z0-9/+_=.-]{20,}["\x27]'
    ),
    re.compile(r"postgres(?:ql)?://(?!USER:PASSWORD@HOST:PORT)[^\s:/]+:[^\s@]+@"),
]


def redact(text):
    for pattern in PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def ensure_no_secrets(text):
    if redact(text) != text:
        raise ValueError("possible secret detected; content withheld")


def safe_repo_path(root, relative):
    from .models import path_value

    path_value(relative)
    root = Path(root).resolve()
    candidate = root / relative
    # Reject symlink components even if their target stays in the repo.
    for parent in [candidate, *candidate.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlink paths are not accepted")
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("path escapes repository")
    return candidate
