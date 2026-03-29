"""
Returns Agent -- exposed via A2A.

Start this service before running main.py scenarios that hit returns:

    uvicorn returns_agent:app --host 127.0.0.1 --port 8002
"""

import os
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.a2a.utils.agent_to_a2a import to_a2a

load_dotenv(encoding="utf-8-sig")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# order_id -> mock order facts for returns
_ORDERS = {
    "ORD-2026-007": {
        "customer_email": "grace.kim@example.com",
        "status": "delivered",
        "days_since_delivery": 10,
        "return_window_days": 30,
    },
    "ORD-2026-003": {
        "customer_email": "alice.johnson@example.com",
        "status": "shipped",
        "days_since_delivery": None,
        "return_window_days": 30,
    },
    "ORD-2026-001": {
        "customer_email": "alice.johnson@example.com",
        "status": "cancelled",
        "days_since_delivery": None,
        "return_window_days": 30,
    },
    "ORD-2026-099": {
        "customer_email": "bob.smith@example.com",
        "status": "delivered",
        "days_since_delivery": 45,
        "return_window_days": 30,
    },
}


def _eligibility_payload(order_id: str, customer_email: str) -> dict:
    email_key = customer_email.strip().lower()
    row = _ORDERS.get(order_id)
    if not row:
        return {
            "eligible": False,
            "order_id": order_id,
            "reason": "unknown_order",
            "message": f"No order found for id {order_id}.",
        }
    if row["customer_email"].lower() != email_key:
        return {
            "eligible": False,
            "order_id": order_id,
            "reason": "email_mismatch",
            "message": "Customer email does not match the order on file.",
        }
    if row["status"] == "cancelled":
        return {
            "eligible": False,
            "order_id": order_id,
            "reason": "order_cancelled",
            "message": "Cancelled orders are not eligible for return.",
        }
    if row["status"] != "delivered":
        return {
            "eligible": False,
            "order_id": order_id,
            "reason": "not_delivered",
            "message": "Returns can only be started after the order is delivered.",
        }
    days = row["days_since_delivery"]
    window = row["return_window_days"]
    if days is None or days > window:
        return {
            "eligible": False,
            "order_id": order_id,
            "reason": "outside_return_window",
            "message": f"Return window is {window} days from delivery; this order is outside that window.",
            "days_since_delivery": days,
            "return_window_days": window,
        }
    return {
        "eligible": True,
        "order_id": order_id,
        "reason": "ok",
        "message": "Order is within the return window and may be returned.",
        "days_since_delivery": days,
        "return_window_days": window,
    }


def check_return_eligibility(order_id: str, customer_email: str) -> dict:
    """Check whether a customer may return an order.

    Returns a dict with keys: eligible (bool), order_id, reason, message,
    and optionally days_since_delivery and return_window_days when relevant.
    """
    return _eligibility_payload(order_id, customer_email)


def initiate_return(order_id: str, customer_email: str, reason: str) -> dict:
    """Start a return (mock). Call check_return_eligibility first when unsure.

    On success returns return_id, status, and message. On failure returns
    eligible False-style fields from the eligibility check.
    """
    eligibility = _eligibility_payload(order_id, customer_email)
    if not eligibility["eligible"]:
        return {
            **eligibility,
            "return_id": None,
            "message": eligibility["message"] + " Return was not created.",
        }
    return {
        "eligible": True,
        "order_id": order_id,
        "return_id": "RMA-2026-1042",
        "status": "label_issued",
        "reason_recorded": reason.strip(),
        "message": "Return initiated. A prepaid label will be emailed to the customer.",
    }


returns_agent = Agent(
    name="returns_agent",
    model=MODEL,
    description="Handles product returns: eligibility, RMA, refunds, and exchanges.",
    instruction="You are a returns specialist. Use check_return_eligibility before initiating "
    "a return when the customer has not already been confirmed eligible. Use initiate_return "
    "to create a return after eligibility is clear. Summarize tool results clearly.",
    tools=[check_return_eligibility, initiate_return],
)

app = to_a2a(returns_agent, port=8002)
