"""
CommerceAgent — the conversational buying agent.

Uses Claude with tool-calling so the model can:
  - search_catalog(query)      -> look up products
  - add_to_cart(product_id, qty) -> add an item to the session cart
  - remove_from_cart(product_id) -> remove an item

This keeps the agent's product knowledge grounded in the actual catalog
(no hallucinated products/prices) and makes cart actions auditable.
"""

import json
import os

import anthropic

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are a friendly, efficient shopping assistant for Northwind Gadgets.
Help the buyer find products, answer questions using ONLY the catalog (never invent
products, prices, or stock), and build their cart. When they're ready, tell them to
say "checkout" to complete the purchase.

Be concise. Don't repeat the full catalog unprompted — recommend based on what they ask for.
If you don't have enough info, ask a short clarifying question instead of guessing.
"""

TOOLS = [
    {
        "name": "search_catalog",
        "description": "Search the merchant's product catalog by keyword (name, description, or tags).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keywords, e.g. 'wireless headphones'"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "add_to_cart",
        "description": "Add a product to the buyer's cart.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "qty": {"type": "integer", "default": 1},
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "remove_from_cart",
        "description": "Remove a product from the buyer's cart.",
        "input_schema": {
            "type": "object",
            "properties": {"product_id": {"type": "string"}},
            "required": ["product_id"],
        },
    },
]


class CommerceAgent:
    def __init__(self, catalog: dict):
        self.catalog = catalog
        self.products_by_id = {p["id"]: p for p in catalog["products"]}
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    # ---- tool implementations -------------------------------------------------

    def _search_catalog(self, query: str):
        q = query.lower()
        results = [
            p for p in self.catalog["products"]
            if q in p["name"].lower() or q in p["description"].lower() or any(q in t for t in p["tags"])
        ]
        return results or [{"note": "No matching products found."}]

    def _add_to_cart(self, session: dict, product_id: str, qty: int = 1):
        product = self.products_by_id.get(product_id)
        if not product:
            return {"error": f"No product with id {product_id}"}
        for item in session["cart"]:
            if item["product_id"] == product_id:
                item["qty"] += qty
                return {"cart": session["cart"]}
        session["cart"].append({
            "product_id": product_id,
            "name": product["name"],
            "price_inr": product["price_inr"],
            "qty": qty,
        })
        return {"cart": session["cart"]}

    def _remove_from_cart(self, session: dict, product_id: str):
        session["cart"] = [i for i in session["cart"] if i["product_id"] != product_id]
        return {"cart": session["cart"]}

    # ---- main entrypoint --------------------------------------------------

    def respond(self, message: str, session: dict) -> dict:
        if "messages" not in session:
            session["messages"] = []

        session["messages"].append({"role": "user", "content": message})

        try:
            reply_text, fallback = self._run_turn(session)
        except Exception as e:
            # Graceful fallback if the API call fails (no key set, network issue, etc.)
            reply_text = (
                "Sorry, I'm having trouble reaching the assistant right now. "
                "You can browse the catalog directly at /catalog in the meantime."
            )
            fallback = True

        session["messages"].append({"role": "assistant", "content": reply_text})
        return {"reply": reply_text, "fallback": fallback}

    def _run_turn(self, session: dict):
        messages = session["messages"]
        fallback = False

        while True:
            resp = self.client.messages.create(
                model=MODEL,
                max_tokens=800,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            text_blocks = [b.text for b in resp.content if b.type == "text"]

            if not tool_uses:
                return "".join(text_blocks) or "Sorry, could you rephrase that?", fallback

            # Execute each tool call and feed results back to the model
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for tu in tool_uses:
                result = self._dispatch_tool(tu.name, tu.input, session)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "user", "content": tool_results})

    def _dispatch_tool(self, name: str, tool_input: dict, session: dict):
        if name == "search_catalog":
            return self._search_catalog(tool_input["query"])
        if name == "add_to_cart":
            return self._add_to_cart(session, tool_input["product_id"], tool_input.get("qty", 1))
        if name == "remove_from_cart":
            return self._remove_from_cart(session, tool_input["product_id"])
        return {"error": f"Unknown tool {name}"}
