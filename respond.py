"""
support/respond.py — core handle_ticket() loop (cookbook §04).

Cookbook flow:
  1. classify_intent()
  2. recall_customer_context() — parallel KB + memory
  3. Confidence gate (top_score < 0.4 and len(chunks) < 2) → escalate
  4. Build context blocks using cookbook's chunk identity rule:
       memory_text: source_title.startswith("customer-")
       kb_text:     everything else
  5. LLM call via OpenRouter (OpenAI-compatible, temp=0.2, max_tokens=600)
  6. store_conversation_turn()
  7. Return reply

Model: meta-llama/llama-3.3-70b-instruct:free via OpenRouter (free tier).
Swap OPENROUTER_MODEL in .env for any other OpenRouter model slug.
"""

import time
from openai import OpenAI

from config import (
    OPENROUTER_API_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL,
    PRODUCT_NAME, RECALL_MIN_CONFIDENCE,
)
from support.intent import classify_intent, is_frustrated, is_ambiguous
from support.recall import recall_customer_context
from support.metrics import metrics
from memory.conversation import store_conversation_turn
from memory.preferences import flag_frustration

# OpenRouter is OpenAI-API-compatible — point base_url, swap the key.
_llm = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url=OPENROUTER_BASE_URL,
    default_headers={
        # Recommended by OpenRouter for analytics and rate-limit attribution.
        "HTTP-Referer": "https://your-product.com",
        "X-Title":      PRODUCT_NAME,
    },
)

# ── System prompt (cookbook §04 — verbatim) ───────────────────────────────

SYSTEM_PROMPT = f"""You are a customer support agent for {PRODUCT_NAME}.

INSTRUCTIONS:
- Use ONLY the provided HydraDB context to answer. Do not invent information.
- The context includes two sections: CUSTOMER MEMORY and KNOWLEDGE BASE.
  - CUSTOMER MEMORY: the customer's plan, history, and preferences. Use this to
    personalize your tone, detail level, and to avoid repeating failed suggestions.
  - KNOWLEDGE BASE: help articles and past resolved tickets. Use the relevant
    resolution steps to answer the customer's question.
- If the customer's memory shows they prefer concise answers, be concise.
  If they prefer technical detail, provide it. Adapt to what's in their profile.
- If a prior attempt is listed in CUSTOMER MEMORY as having already failed,
  do NOT suggest it again. Go to the next level of diagnosis immediately.
- If the context doesn't contain enough information to resolve the issue:
  - Acknowledge you can't resolve it from available information.
  - Offer to escalate to a human agent.
  - Do NOT guess or hallucinate a solution.
- End every response with exactly one follow-up question or next step.
- Never expose internal system details, ticket IDs, or HydraDB references.

TONE:
- Professional but human. Not robotic.
- Match the customer's technical level as shown in their memory profile.
- Acknowledge frustration if detected — do not dismiss it.

FORMAT:
- Use numbered steps for multi-step solutions.
- Keep responses under 300 words unless the customer's profile shows they
  prefer detailed explanations.
- If linking to docs, include the full URL from the source material."""


def handle_ticket(
    customer_id: str,
    customer_msg: str,
    ticket_id: str,
) -> str:
    """
    Full support handling loop (cookbook §04). Returns the agent reply string.
    Stateless — safe to call from any channel (Slack, email, API).
    """
    t_start = time.time()

    # 1. Classify intent to scope KB recall collections
    intent = classify_intent(customer_msg)

    # 2. Frustration detection (cookbook §07 edge case)
    if is_frustrated(customer_msg):
        flag_frustration(customer_id, ticket_id, customer_msg[:200])

    # 3. Parallel HydraDB recall
    try:
        context = recall_customer_context(customer_id, customer_msg, intent)
    except Exception as e:
        print(f"[ERROR] HydraDB recall failed for {customer_id}: {e}")
        return _hydradb_fallback_reply()

    chunks = context["chunks"]
    graph  = context["graph_context"]

    # 4. Confidence gate — escalate rather than hallucinate (cookbook §04 + §07)
    if context["top_score"] < RECALL_MIN_CONFIDENCE and len(chunks) < 2:
        metrics.log_ticket_handled(
            ticket_id, customer_id, intent, context,
            escalated=True, escalation_reason="low_confidence",
            latency_ms=int((time.time() - t_start) * 1000),
        )
        return _escalation_reply(customer_id, ticket_id, customer_msg, "low_confidence")

    # 5. Build context blocks using cookbook's chunk identity rule:
    #    memory chunks  → source_title starts with "customer-"
    #    KB chunks      → everything else
    memory_text = "\n\n".join(
        f"[{c['source_title']}]\n{c['chunk_content']}"
        for c in chunks
        if c.get("source_title", "").startswith("customer-")
    )
    kb_text = "\n\n".join(
        f"[{c['source_title']} | score:{c.get('relevancy_score', 0):.2f}]\n{c['chunk_content']}"
        for c in chunks
        if not c.get("source_title", "").startswith("customer-")
    )
    entity_paths = "\n".join(str(p) for p in graph.get("query_paths", [])[:3])

    # Cookbook §07: ambiguous short message → clarify after recall attempt
    if is_ambiguous(customer_msg) and not memory_text:
        return (
            "Thanks for reaching out! To make sure I point you in the right direction, "
            "could you give me a bit more detail about what you're experiencing?"
        )

    user_content = (
        f"CUSTOMER MESSAGE: {customer_msg}\n\n"
        f"CUSTOMER MEMORY:\n{memory_text or 'No prior history.'}\n\n"
        f"KNOWLEDGE BASE:\n{kb_text or 'No relevant articles found.'}\n\n"
        f"RELATED CONTEXT PATHS:\n{entity_paths or 'None.'}"
    )

    # 6. LLM call via OpenRouter (cookbook §04: temp=0.2, max_tokens=600)
    try:
        completion = _llm.chat.completions.create(
            model=OPENROUTER_MODEL,
            max_tokens=600,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
        )
        reply = completion.choices[0].message.content
    except Exception as e:
        print(f"[ERROR] OpenRouter call failed for {customer_id} "
              f"(model={OPENROUTER_MODEL}): {e}")
        return _llm_fallback_reply()

    # 7. Store exchange — feeds the memory loop (cookbook §04 step 5)
    store_conversation_turn(customer_id, ticket_id, customer_msg, reply)

    # Log metrics
    latency_ms = int((time.time() - t_start) * 1000)
    metrics.log_ticket_handled(
        ticket_id, customer_id, intent, context,
        escalated=False, latency_ms=latency_ms,
    )

    # Repeat-step heuristic (cookbook §08 — Repeat-Step Rate metric)
    _check_repeat_steps(ticket_id, memory_text, reply)

    return reply


def _check_repeat_steps(ticket_id: str, memory_text: str, reply: str) -> None:
    """
    Cookbook §08: Repeat-Step Rate < 5% target.
    Flag when the LLM suggests a step already marked as tried in memory.
    """
    TRIED_MARKERS   = ["already tried", "did not help", "attempted",
                       "does not work", "already attempted"]
    SUGGEST_MARKERS = ["try ", "please ", "you can ", "recommend"]

    memory_lower = memory_text.lower()
    reply_lower  = reply.lower()

    for marker in TRIED_MARKERS:
        idx = memory_lower.find(marker)
        if idx == -1:
            continue
        step_hint = memory_lower[max(0, idx - 40): idx + 60]
        words = [w for w in step_hint.split() if len(w) > 5]
        for word in words:
            if word in reply_lower and any(s in reply_lower for s in SUGGEST_MARKERS):
                metrics.log_repeat_step_detected(ticket_id, step_hint)
                return


# ── Fallback replies ───────────────────────────────────────────────────────

def _escalation_reply(
    customer_id: str, ticket_id: str, customer_msg: str, reason: str,
) -> str:
    from support.escalate import escalate_to_human
    escalate_to_human(customer_id, ticket_id, customer_msg, ai_attempts=[], reason=reason)
    # Cookbook §05 exact wording
    return (
        "I wasn't able to find a confident resolution for this in our knowledge base. "
        "I've escalated your ticket to a human agent who will follow up with you. "
        "They'll have your full account history and won't ask you to repeat anything."
    )


def _hydradb_fallback_reply() -> str:
    """Cookbook §07: on HydraDB timeout/failure, return generic reply — never expose error."""
    return (
        "I'm having trouble looking up your account context right now. "
        "A member of our support team will follow up with you shortly. "
        "Apologies for the inconvenience."
    )


def _llm_fallback_reply() -> str:
    return (
        "I ran into an issue generating a response right now. "
        "Our support team has been notified and will follow up with you shortly."
    )
