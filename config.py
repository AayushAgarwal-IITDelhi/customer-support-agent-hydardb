"""
config.py — shared configuration (cookbook §01 constants + OpenRouter).
Import from every module — never re-read env vars directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API keys ───────────────────────────────────────────────────────────────
HYDRADB_API_KEY    = os.environ["HYDRADB_API_KEY"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]

# ── OpenRouter ─────────────────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
#
# Default: meta-llama/llama-3.3-70b-instruct:free
#   → Best quality available on the OpenRouter free tier.
#   → Append ":free" to any model slug to use the free variant.
#   → Change via OPENROUTER_MODEL in .env — no code changes needed.
#
# Other free options:
#   mistralai/mistral-7b-instruct:free   (lightweight)
#   google/gemma-3-27b-it:free           (Google, mid-tier)
#
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "meta-llama/llama-3.3-70b-instruct:free",
)

# ── HydraDB (cookbook §01 exact) ───────────────────────────────────────────
BASE_URL      = "https://api.hydradb.com"
TENANT_ID     = "customer-support"
KB_SUB_TENANT = "knowledge-base"   # shared — all agents read from here

HEADERS = {
    "Authorization": f"Bearer {HYDRADB_API_KEY}",
    "Content-Type":  "application/json",
}

# ── Product ────────────────────────────────────────────────────────────────
PRODUCT_NAME = os.getenv("PRODUCT_NAME", "YourProduct")

# ── Recall tuning (cookbook §04) ───────────────────────────────────────────
RECALL_MAX_RESULTS    = 12
RECALL_ALPHA          = 0.8   # 0=keyword, 1=semantic; 0.8=balanced (cookbook)
RECALL_MIN_CONFIDENCE = 0.4   # below this → escalate, not guess (cookbook)
HYDRADB_TIMEOUT       = 3     # seconds; cookbook §07 recommendation


def customer_sub(customer_id: str) -> str:
    """Maps customer ID to their isolated HydraDB sub-tenant (cookbook §01)."""
    return f"customer-{customer_id}"
