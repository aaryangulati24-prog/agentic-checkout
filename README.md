# Agentic Checkout — Northwind Gadgets Shopping Agent

**Track:** AI Growth & Agentic Commerce — Razorpay Buildathon

A conversational shopping agent that lets a buyer (human or AI) browse an
agent-readable merchant catalog, get recommendations, build a cart, and check
out via Razorpay test-mode APIs.

## Architecture

```
frontend/index.html        Simple chat UI (fetches from backend API)
        |
        v
backend/main.py             FastAPI app: /catalog, /chat, /checkout, /metrics
        |
        v
backend/agent/agent.py      CommerceAgent — Claude + tool-calling
        |                     tools: search_catalog, add_to_cart, remove_from_cart
        v
backend/data/catalog.json   Agent-readable merchant catalog (schema.org-style)
```

**Why tool-calling instead of free-text generation:** the agent's product
knowledge stays grounded in the real catalog — it can't hallucinate a product,
price, or stock level, because every claim about the catalog comes from a
`search_catalog` tool call, not the model's own memory. Cart mutations are
explicit tool calls too, so every action is auditable.

## Setup

```bash
cd backend
pip install -r requirements.txt

export ANTHROPIC_API_KEY=your_key_here
# export RAZORPAY_KEY_ID=your_test_key
# export RAZORPAY_KEY_SECRET=your_test_secret

uvicorn main:app --reload --port 8000
```

Then open `frontend/index.html` in a browser (or serve it with any static
server) to chat with the agent.

## Current status / stub notes

- `create_test_order()` in `main.py` is currently a stub that returns a fake
  order object so the project runs without live Razorpay credentials during
  development. Swap in the real `razorpay` SDK call (commented inline) once
  you have test-mode keys.
- Catalog is a small hardcoded JSON file (5 products) — good enough to demo
  the agent flow end-to-end. Swap for a real merchant's product feed later.

## Metrics tracked (for the "measurable impact" ask)

`GET /metrics` returns:
- `sessions_started` / `sessions_completed_purchase` → conversion rate
- `fallback_rate` → % of turns where the agent couldn't produce a grounded answer
- Per-session `time_to_purchase_sec` returned at checkout

## Roadmap / stretch goals

1. **AI-to-AI handshake (stretch):** add a second "buyer agent" that
   negotiates with this merchant agent programmatically (no human in the
   loop), following an ACP/AP2/x402-style request-offer-accept pattern.
2. Real Razorpay test-mode integration (order creation + payment capture webhook).
3. Persist sessions/cart in a real DB instead of in-memory dict.
4. Add upsell logic: when cart is built, agent proactively suggests a bundle
   (see `bundles` in catalog.json).
5. Pitch video + architecture diagram for submission.


