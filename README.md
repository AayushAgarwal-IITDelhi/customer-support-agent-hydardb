# HydraDB AI Customer Support Agent

A production-ready customer support agent using HydraDB for long-term memory and knowledge retrieval, powered by Claude (Anthropic) for response generation.

## Architecture

```
Customer Message (Slack / Email / API)
        ↓
  Intent Classification
        ↓
  ┌─────────────────────────┐
  │ Parallel HydraDB Recall │
  │  /recall/full_recall    │  ← Knowledge base (docs, past tickets)
  │  /recall/recall_prefs   │  ← Per-customer memory (history, prefs)
  └─────────────────────────┘
        ↓ Merged context (<400ms)
  Claude API (claude-sonnet-4-20250514)
        ↓
  Personalized Response
        ↓
  Store exchange in HydraDB
```

## Project Structure

```
hydradb-support-agent/
├── .env.example             # Environment variables template
├── config.py                # Shared config / constants
├── support/
│   ├── intent.py            # Intent classification
│   ├── recall.py            # Two-call recall pattern
│   ├── respond.py           # Core handle_ticket() loop
│   └── escalate.py          # Escalation & human handoff
├── memory/
│   ├── conversation.py      # Store conversation turns (infer:false)
│   └── preferences.py       # Store preference signals (infer:true)
├── ingest/
│   ├── help_docs.py         # Ingest KB articles / FAQs
│   └── past_tickets.py      # Ingest resolved tickets
├── channels/
│   ├── slack.py             # Slack Bolt listener
│   └── email_webhook.py     # Flask email webhook
└── scripts/
    └── setup_tenant.py      # One-time tenant creation
```

## Setup

### 1. Install dependencies

```bash
pip install anthropic hydra-db-python slack-bolt flask python-dotenv requests
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Create the tenant (one-time)

```bash
python scripts/setup_tenant.py
```

### 4. Seed the knowledge base

```python
from ingest.help_docs import ingest_help_docs
from ingest.past_tickets import ingest_resolved_tickets

# Your articles as a list of dicts
ingest_help_docs(your_articles)
ingest_resolved_tickets(your_tickets)
```

### 5. Run a channel

```bash
# Slack
python channels/slack.py

# Email webhook
python channels/email_webhook.py
```

## Key Design Decisions

- **Claude over GPT-4o**: Uses `claude-sonnet-4-20250514` for response generation — better instruction-following and lower hallucination rate on grounded prompts.
- **Two-call parallel recall**: Both HydraDB calls (`full_recall` + `recall_preferences`) run concurrently via `ThreadPoolExecutor`, keeping total latency under 400ms.
- **Confidence gate**: If `top_score < 0.4`, escalate immediately rather than hallucinate.
- **infer:false for turns, infer:true for preferences**: Keeps verbatim history clean while letting HydraDB build the preference graph automatically.
- **Consistent `customer_id`**: The same identifier is used across all channels (Slack, email, API) for automatic cross-channel memory.
