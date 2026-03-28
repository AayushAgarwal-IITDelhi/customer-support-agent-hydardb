"""
support/intent.py — fast intent classifier (cookbook §DESIGN).

Runs before HydraDB recall to scope which KB collections to weight.
Keyword lists match the cookbook exactly; additional signals layered on top.
"""

# ── Cookbook-exact definitions ─────────────────────────────────────────────

INTENT_COLLECTIONS: dict[str, list[str]] = {
    "billing":    ["billing", "account"],
    "technical":  ["technical", "onboarding"],
    "account":    ["account", "general"],
    "onboarding": ["onboarding", "general"],
    "general":    ["knowledge-base"],
}

INTENT_KEYWORDS: dict[str, list[str]] = {
    "billing":    ["invoice", "charge", "payment", "subscription", "refund", "plan"],
    "technical":  ["error", "bug", "crash", "api", "integration", "not working"],
    "account":    ["password", "login", "sso", "access", "permission"],
    "onboarding": ["setup", "getting started", "install", "configure"],
}


def classify_intent(message: str) -> str:
    """
    Returns the highest-scoring intent bucket.
    Falls back to "general" when no keywords match.
    Matches cookbook logic exactly.
    """
    msg_lower = message.lower()
    scores = {
        intent: sum(kw in msg_lower for kw in keywords)
        for intent, keywords in INTENT_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def collections_for_intent(intent: str) -> list[str]:
    """Returns the HydraDB collections to weight for this intent."""
    return INTENT_COLLECTIONS.get(intent, ["knowledge-base"])


# ── Additional signals (not in cookbook, layered on top) ──────────────────

FRUSTRATION_SIGNALS = [
    "useless", "terrible", "awful", "worst", "again", "third time",
    "still broken", "never works", "ridiculous", "unacceptable",
    "waste of time", "fix this", "!!!", "???",
]


def is_frustrated(message: str) -> bool:
    """
    Detect frustration signals (cookbook §07 edge case).
    Checks keyword list + all-caps words (>= 2 uppercase words of len > 2).
    """
    msg_lower = message.lower()
    if any(sig in msg_lower for sig in FRUSTRATION_SIGNALS):
        return True
    caps_run = sum(1 for w in message.split() if w.isupper() and len(w) > 2)
    return caps_run >= 2


def is_ambiguous(message: str) -> bool:
    """
    Cookbook §07: messages under 15 words with no clear technical signal
    are treated as ambiguous — recall preferences first, then clarify.
    """
    return len(message.split()) < 15 and classify_intent(message) == "general"
