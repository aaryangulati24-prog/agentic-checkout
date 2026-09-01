"""
Agentic Checkout — FastAPI backend
Track 1: AI Growth & Agentic Commerce (Razorpay Buildathon)

Exposes:
- GET  /catalog                 -> full agent-readable catalog
- GET  /catalog/search?q=       -> keyword search over catalog
- POST /chat                    -> conversational endpoint, agent responds + can build cart
- POST /checkout                -> creates a Razorpay test-mode order for the current cart
- GET  /metrics                 -> simple session metrics (time-to-purchase, fallback rate)
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.agent import CommerceAgent

DATA_PATH = Path(__file__).parent / "data" / "catalog.json"

app = FastAPI(title="Agentic Checkout Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory state (fine for a buildathon demo; swap for a DB later) ---
SESSIONS: dict = {}
METRICS = {
    "sessions_started": 0,
    "sessions_completed_purchase": 0,
    "fallback_responses": 0,
    "total_responses": 0,
}

with open(DATA_PATH) as f:
    CATALOG = json.load(f)

agent = CommerceAgent(catalog=CATALOG)


class ChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    cart: list
    fallback: bool = False


class CheckoutRequest(BaseModel):
    session_id: str


@app.get("/catalog")
def get_catalog():
    return CATALOG


@app.get("/catalog/search")
def search_catalog(q: str):
    q_lower = q.lower()
    results = [
        p for p in CATALOG["products"]
        if q_lower in p["name"].lower()
        or q_lower in p["description"].lower()
        or any(q_lower in t for t in p["tags"])
    ]
    return {"query": q, "results": results}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {"cart": [], "started_at": time.time()}
        METRICS["sessions_started"] += 1

    session = SESSIONS[session_id]

    result = agent.respond(message=req.message, session=session)

    METRICS["total_responses"] += 1
    if result["fallback"]:
        METRICS["fallback_responses"] += 1

    return ChatResponse(
        session_id=session_id,
        reply=result["reply"],
        cart=session["cart"],
        fallback=result["fallback"],
    )


@app.post("/checkout")
def checkout(req: CheckoutRequest):
    session = SESSIONS.get(req.session_id)
    if not session or not session["cart"]:
        raise HTTPException(status_code=400, detail="Cart is empty or session not found")

    total_amount = sum(item["price_inr"] * item["qty"] for item in session["cart"])

    # NOTE: Razorpay test-mode order creation.
    # Wire in real Razorpay SDK here — see README for setup instructions.
    order = create_test_order(amount_inr=total_amount, session_id=req.session_id)

    session["completed_at"] = time.time()
    session["time_to_purchase_sec"] = session["completed_at"] - session["started_at"]
    METRICS["sessions_completed_purchase"] += 1

    return {
        "order": order,
        "amount_inr": total_amount,
        "time_to_purchase_sec": round(session["time_to_purchase_sec"], 2),
    }


def create_test_order(amount_inr: float, session_id: str):
    """
    Stub for Razorpay test-mode order creation.
    Replace with:

        import razorpay
        client = razorpay.Client(auth=(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"]))
        order = client.order.create({
            "amount": int(amount_inr * 100),  # paise
            "currency": "INR",
            "receipt": session_id,
        })
        return order

    Kept as a stub so the project runs without live credentials during development.
    """
    return {
        "id": f"order_test_{uuid.uuid4().hex[:12]}",
        "amount": int(amount_inr * 100),
        "currency": "INR",
        "status": "created (test-mode stub)",
        "receipt": session_id,
    }


@app.get("/metrics")
def get_metrics():
    fallback_rate = (
        METRICS["fallback_responses"] / METRICS["total_responses"]
        if METRICS["total_responses"] else 0
    )
    return {**METRICS, "fallback_rate": round(fallback_rate, 3)}


@app.get("/health")
def health():
    return {"status": "ok"}
