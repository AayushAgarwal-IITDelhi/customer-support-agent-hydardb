"""
support/recall.py — two-call parallel recall pattern (cookbook §04).

Cookbook spec:
  1. /recall/full_recall       → knowledge base (docs + resolved tickets)
  2. /recall/recall_preferences → customer personal memory (prefs, history)
  Both run in parallel via ThreadPoolExecutor.
  Personal memory chunks first in merged list (higher personalization weight).

Chunk identity (cookbook §04 respond.py):
  Memory chunks  → source_title.startswith("customer-")
  KB chunks      → everything else
"""

import concurrent.futures
import requests

from config import (
    BASE_URL, HEADERS, TENANT_ID, KB_SUB_TENANT,
    RECALL_MAX_RESULTS, RECALL_ALPHA, HYDRADB_TIMEOUT,
    customer_sub,
)
from support.intent import collections_for_intent


def recall_customer_context(
    customer_id: str,
    customer_msg: str,
    intent: str = "general",
) -> dict:
    """
    Returns merged context dict matching cookbook structure:
    {
        "chunks":        [...],   # mem chunks first, then KB chunks
        "graph_context": {...},   # cross-document entity paths from KB call
        "top_score":     float,   # highest relevancy_score in KB chunks
        "mem_chunks":    [...],   # personal memory only (for metrics)
        "kb_chunks":     [...],   # KB only (for metrics)
    }
    """
    collections = collections_for_intent(intent)

    def _kb_call():
        return requests.post(
            f"{BASE_URL}/recall/full_recall",
            headers=HEADERS,
            json={
                "tenant_id":     TENANT_ID,
                "sub_tenant_id": KB_SUB_TENANT,
                "query":         customer_msg,
                "max_results":   RECALL_MAX_RESULTS,
                "mode":          "thinking",   # personalised ranking
                "graph_context": True,         # cross-document entity linking
                "alpha":         RECALL_ALPHA, # 0.8 = balanced semantic + keyword
                "collections":   collections,
            },
            timeout=HYDRADB_TIMEOUT,
        )

    def _mem_call():
        return requests.post(
            f"{BASE_URL}/recall/recall_preferences",
            headers=HEADERS,
            json={
                "tenant_id":     TENANT_ID,
                "sub_tenant_id": customer_sub(customer_id),
                "query":         customer_msg,
                "user_name":     customer_id,
                "mode":          "thinking",
            },
            timeout=HYDRADB_TIMEOUT,
        )

    # Run both calls in parallel — cuts total latency roughly in half
    with concurrent.futures.ThreadPoolExecutor() as pool:
        kb_fut  = pool.submit(_kb_call)
        mem_fut = pool.submit(_mem_call)
        kb_resp  = kb_fut.result()
        mem_resp = mem_fut.result()

    kb_resp.raise_for_status()
    mem_resp.raise_for_status()

    kb_data  = kb_resp.json()
    mem_data = mem_resp.json()

    kb_chunks  = kb_data.get("chunks", [])
    mem_chunks = mem_data.get("chunks", [])

    # Personal memory first — higher personalization weight in LLM context
    # then KB chunks — the actual solutions
    # then graph context — entity relationship paths across documents
    return {
        "chunks":        mem_chunks + kb_chunks,
        "graph_context": kb_data.get("graph_context", {}),
        "top_score": max(
            (c.get("relevancy_score", 0) for c in kb_chunks),
            default=0,
        ),
        # Extra keys for metrics logging — not used by LLM
        "mem_chunks": mem_chunks,
        "kb_chunks":  kb_chunks,
    }
