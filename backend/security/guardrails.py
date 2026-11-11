# backend/security/guardrails.py
"""
Production Guardrails for StackPulse Agentic AI Pipeline.
Enforces defense-in-depth across 4 critical attack vectors:
1. Direct Prompt Injection (User onboarding input)
2. Indirect Prompt Injection (Untrusted external web/README/comment data)
3. Tool Argument Hijacking & SSRF/Path Traversal (Tool least-privilege)
4. Sensitive Data Leakage & Secret Exfiltration (Output scanning)
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import log


# ── Category 1: Direct Prompt Injection Patterns ─────────────────────────────
DIRECT_INJECTION_PATTERNS = [
    r"(?i)(ignore|disregard|forget|bypass)\s+(all\s+)?(previous|prior|above|system)\s+(instructions|directives|prompts|rules)",
    r"(?i)you\s+are\s+now\s+(in\s+)?(dan|developer|unrestricted|jailbreak|god)\s+mode",
    r"(?i)system\s+(override|prompt|directive|command)\s*:",
    r"(?i)(reveal|show|print|output|display|repeat)\s+(your\s+)?(system\s+prompt|instructions|initial\s+prompt|secret)",
    r"(?i)(act\s+as|pretend\s+to\s+be)\s+an?\s+(unrestricted|unfiltered|malicious|jailbroken)\s+ai",
    r"(?i)new\s+rule\s*:\s*you\s+must",
    r"(?i)stop\s+being\s+an?\s+ai",
]

# ── Category 2: Indirect Web Content Hijacking Patterns ──────────────────────
INDIRECT_INJECTION_PATTERNS = [
    r"(?i)<!--\s*(system|instruction|command|override)",
    r"(?i)\[\s*system\s*:\s*[^\]]+\]",
    r"(?i)special\s+instruction\s*:\s*(ignore|tell\s+the\s+user|append|link)",
    r"(?i)click\s+here\s+to\s+(verify|login|claim|upgrade|win)\s*:",
    r"(?i)(eval|base64_decode|exec)\s*\(",
]

# ── Category 3: Tool Argument Hijacking / Path Traversal / SSRF ───────────────
SSRF_BLOCKED_HOSTS = [
    r"169\.254\.169\.254",   # AWS/GCP cloud metadata endpoint
    r"localhost",
    r"127\.0\.0\.1",
    r"0\.0\.0\.0",
    r"10\.\d+\.\d+\.\d+",
    r"192\.168\.\d+\.\d+",
]
PATH_TRAVERSAL_REGEX = r"(\.\./|\.\.\\|/etc/|C:\\Windows|/var/)"
SHELL_INJECTION_CHARS = [";", "&&", "||", "`", "$(", "|"]

# ── Category 4: Sensitive Data & Secret Leak Patterns ────────────────────────
SECRET_PATTERNS = [
    r"gsk_[a-zA-Z0-9]{20,}",                  # Groq API Key
    r"xkeysib-[a-zA-Z0-9]{40,}",              # Brevo API Key
    r"AIzaSy[a-zA-Z0-9_\-]{25,}",             # Google Gemini API Key
    r"lsv2_pt_[a-zA-Z0-9_]{20,}",             # LangSmith API Key
    r"postgres(?:ql)?://[^\s@]+:[^\s@]+@",    # Database connection with password
    r"Bearer\s+[a-zA-Z0-9_\-\.]{25,}",       # Generic Bearer Token
]


@dataclass
class GuardrailResult:
    is_safe: bool
    sanitized_input: str
    attack_category: Optional[str] = None
    reason: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail 1: Direct Prompt Injection Scanner (User Form Input)
# ─────────────────────────────────────────────────────────────────────────────
def scan_direct_prompt_injection(user_text: str) -> GuardrailResult:
    """
    Scans user inputs (custom_interests, keyword_alerts) for direct injection attacks.
    If detected, neutralizes the attack and returns a safe fallback.
    """
    if not user_text:
        return GuardrailResult(is_safe=True, sanitized_input="")

    for pattern in DIRECT_INJECTION_PATTERNS:
        if re.search(pattern, user_text):
            log.warning("security.direct_prompt_injection_blocked", text=user_text[:80])
            # Strip malicious command and return safe message
            sanitized = re.sub(pattern, "[sanitized security violation]", user_text).strip()
            return GuardrailResult(
                is_safe=False,
                sanitized_input="General technology and programming topics",
                attack_category="direct_prompt_injection",
                reason=f"Matched direct injection pattern: {pattern}",
            )

    # Clean zero-width unicode characters intended to bypass tokenizers
    cleaned = re.sub(r"[\u200B-\u200D\uFEFF]", "", user_text).strip()
    return GuardrailResult(is_safe=True, sanitized_input=cleaned)


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail 2: Indirect Prompt Injection Scanner (Scraped Web Data)
# ─────────────────────────────────────────────────────────────────────────────
def sanitize_untrusted_scraped_data(raw_text: str, source: str = "web") -> Tuple[str, bool]:
    """
    Sanitizes untrusted content from GitHub READMEs or Hacker News comments.
    Wraps content in XML boundary tags and strips instruction hijacking.
    Returns (safe_text, was_injection_detected).
    """
    if not raw_text:
        return "", False

    was_detected = False
    cleaned_text = raw_text

    # Strip zero-width characters
    cleaned_text = re.sub(r"[\u200B-\u200D\uFEFF]", "", cleaned_text)

    # Check for indirect injection signatures
    for pattern in INDIRECT_INJECTION_PATTERNS:
        if re.search(pattern, cleaned_text):
            log.warning("security.indirect_prompt_injection_detected", source=source)
            cleaned_text = re.sub(pattern, "[removed untrusted instruction]", cleaned_text)
            was_detected = True

    # Check for direct injection patterns inside scraped content
    for pattern in DIRECT_INJECTION_PATTERNS:
        if re.search(pattern, cleaned_text):
            log.warning("security.indirect_override_detected_in_scrape", source=source)
            cleaned_text = re.sub(pattern, "[removed malicious directive]", cleaned_text)
            was_detected = True

    # Boundary tagging: Isolates data inside inert tags so LLM treats it as pure payload
    sandboxed_content = f'<untrusted_data source="{source}">\n{cleaned_text}\n</untrusted_data>'
    return sandboxed_content, was_detected


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail 3: Tool Permission & Argument Boundary Enforcement
# ─────────────────────────────────────────────────────────────────────────────
def validate_tool_arguments(tool_name: str, args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Enforces strict least-privilege schemas on tool call parameters before execution.
    Prevents SSRF, Path Traversal, Shell Injection, and SQL Injection attempts.
    """
    if not isinstance(args, dict):
        return False, "Tool arguments must be a dictionary"

    # 1. GitHub Tool: strictly validate 'owner/repo' format
    if tool_name == "inspect_github_repo":
        repo_name = str(args.get("repo_name", "")).strip()
        # Disallow path traversal
        if re.search(PATH_TRAVERSAL_REGEX, repo_name, re.IGNORECASE):
            return False, "Path traversal attempt detected in repo_name"
        # Disallow shell characters
        if any(char in repo_name for char in SHELL_INJECTION_CHARS):
            return False, "Shell metacharacters detected in repo_name"
        # Disallow SSRF URLs
        for host in SSRF_BLOCKED_HOSTS:
            if re.search(host, repo_name):
                return False, f"SSRF blocked: illegal destination host in repo_name"

    # 2. Hacker News Tool: strictly enforce integer or clean ID format
    elif tool_name == "fetch_hn_discussion":
        story_id = str(args.get("story_id", "")).strip()
        # Reject SQL injection / URL injection in story ID
        if re.search(r"(\bOR\b|\bSELECT\b|--|;)", story_id, re.IGNORECASE):
            return False, "SQL injection pattern detected in story_id"
        # Must contain digits
        if not re.search(r"\d+", story_id):
            return False, "Invalid story_id format: must contain numeric ID"

    # 3. CVE Tool: validate package name & ecosystem allowlist
    elif tool_name == "check_cve_vulnerabilities":
        pkg = str(args.get("package_name", "")).strip()
        eco = str(args.get("ecosystem", "PyPI")).strip()

        # Disallow shell or SQL characters in package name
        if any(char in pkg for char in [";", "&", "|", "`", "$", "'", '"']):
            return False, "Illegal characters detected in package_name"

        allowed_ecosystems = ["pypi", "npm", "crates.io", "go", "maven", "packagist"]
        if eco.lower() not in allowed_ecosystems:
            return False, f"Ecosystem '{eco}' not permitted. Must be in {allowed_ecosystems}"

    return True, None


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail 4: Sensitive Data Leakage & Secret Sanitizer (Output Scanner)
# ─────────────────────────────────────────────────────────────────────────────
def scan_output_for_leaks(output_html_or_text: str) -> Tuple[str, bool]:
    """
    Scans final generated email HTML or text to guarantee no API keys,
    passwords, or internal secrets are leaked to the subscriber.
    Returns (sanitized_output, was_leak_prevented).
    """
    if not output_html_or_text:
        return "", False

    leaked = False
    sanitized = output_html_or_text

    for pattern in SECRET_PATTERNS:
        matches = re.findall(pattern, sanitized)
        if matches:
            leaked = True
            log.critical("security.secret_leak_intercepted", pattern=pattern)
            sanitized = re.sub(pattern, "[REDACTED_SECRET]", sanitized)

    return sanitized, leaked
