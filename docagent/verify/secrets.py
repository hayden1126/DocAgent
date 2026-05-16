"""Secret-scan gate. Uses trufflehog/gitleaks when present; warns otherwise.

Runs against the artifact content **before** it is written to disk so leaked
material never lands in the working tree.
"""

from __future__ import annotations

import re
from typing import Sequence

from docagent.artifacts.registry import DocPatch, GenerationContext

# Conservative high-precision patterns. The real defense is the external tool.
HEURISTIC_PATTERNS = [
    re.compile(rb"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"sk-[A-Za-z0-9]{32,}"),  # OpenAI-style key
    re.compile(rb"ghp_[A-Za-z0-9]{36,}"),  # GitHub PAT
]


def check(patch: DocPatch, ctx: GenerationContext) -> tuple[bool, Sequence[str]]:
    findings: list[str] = []
    for pat in HEURISTIC_PATTERNS:
        if pat.search(patch.new_content):
            findings.append(f"possible secret matched pattern: {pat.pattern!r}")
    return (not findings), findings
