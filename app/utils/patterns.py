"""Centralised compiled regex pattern registry.

Patterns are compiled once at import time — never inside a hot validate() loop.
All guardrails import from here to avoid duplicating and re-compiling patterns.
"""

import re

# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------
PROMPT_INJECTION: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)\b",
        r"\bdisregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)\b",
        r"\bforget\s+(everything|all|your instructions?)\b",
        r"\byou\s+are\s+now\s+(?!an? (?:ai|assistant))\b",  # "you are now DAN"
        r"\bact\s+as\s+(if\s+you\s+(were|are)\s+)?(?!an? (?:helpful|ai|assistant))\w+",
        r"\bjailbreak\b",
        r"\bdan\s+mode\b",
        r"\bdo\s+anything\s+now\b",
        r"\bpretend\s+(you\s+)?(have\s+no|don.t\s+have\s+any)\s+(restrictions?|limits?|rules?)\b",
        r"\byour\s+(true|real|actual)\s+(purpose|goal|task)\s+is\b",
        r"\bsystem\s*prompt\b.*\bignore\b",
        r"\boverride\s+(safety|content|system)\b",
    ]
]

# ---------------------------------------------------------------------------
# Jailbreak
# ---------------------------------------------------------------------------
JAILBREAK: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bgrandma\s+(exploit|trick|hack|loophole)\b",
        r"\b(evil|opposite|reverse|dark)\s+(mode|twin|version|persona)\b",
        r"\bdev(eloper)?\s+mode\b",
        r"\bno\s+(restrictions?|limits?|filters?|safeguards?|guidelines?)\b",
        r"\bunfiltered\b",
        r"\buncensored\b",
        r"\bbypass\s+(the\s+)?(safety|content|filter|restriction|guidelines?)\b",
        r"\b(always|will\s+always)\s+(respond|comply|obey|answer)\b.*\b(without|ignoring)\b",
        r"\bimagine\s+(you\s+(are|were|have|had)|there\s+are\s+no)\b",
        r"\bsimulate\s+(a\s+)?(different|unrestricted|uncensored)\b",
        r"\bfor\s+(educational|research|fictional|hypothetical|creative)\s+purposes?\b.*\b(bomb|weapon|exploit|malware|virus)\b",
        r"\btoken\s*smuggling\b",
        r"\bprompt\s*leak\b",
    ]
]

# ---------------------------------------------------------------------------
# PII
# ---------------------------------------------------------------------------
PII: dict[str, re.Pattern[str]] = {
    "EMAIL": re.compile(r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"),
    "PHONE": re.compile(r"\b(\+?\d[\d\s\-().]{7,}\d)\b"),
    "SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "DATE_OF_BIRTH": re.compile(
        r"\b(?:dob|date\s+of\s+birth)[:\s]+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        re.IGNORECASE,
    ),
    "PASSPORT": re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
}

# ---------------------------------------------------------------------------
# Secrets / API keys
# ---------------------------------------------------------------------------
SECRETS: dict[str, re.Pattern[str]] = {
    "OPENAI_KEY": re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    "ANTHROPIC_KEY": re.compile(r"\bsk-ant-[a-zA-Z0-9\-_]{20,}\b"),
    "GITHUB_TOKEN": re.compile(r"\bghp_[a-zA-Z0-9]{36}\b"),
    "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "AWS_SECRET_KEY": re.compile(r"\b[a-zA-Z0-9/+]{40}\b"),  # broad; contextual
    "GCP_API_KEY": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "PRIVATE_KEY": re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
    "BEARER_TOKEN": re.compile(r"\bBearer\s+[a-zA-Z0-9\-_.~+/]+=*\b", re.IGNORECASE),
    "GENERIC_SECRET": re.compile(
        r'(?:secret|api[_\-]?key|auth[_\-]?token|password)\s*[=:]\s*["\']?[a-zA-Z0-9\-_.]{8,}',
        re.IGNORECASE,
    ),
}

# ---------------------------------------------------------------------------
# Toxicity — coarse keyword/phrase matching (no ML dependency)
# ---------------------------------------------------------------------------
TOXICITY: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bkill\s+(yourself|all|them|everyone|you)\b",
        r"\b(stupid|dumb|idiot|moron|imbecile)\b",
        r"\bhate\s+(you|them|all|everyone|everything|this|it)\b",
        r"\b(fuck|shit|bitch|asshole|bastard|cunt|damn)\b",
        r"\b(racist|sexist|homophobic|transphobic)\b",
        r"\bslur\b",
        r"\b(threaten|threat|threatening)\b",
    ]
]
