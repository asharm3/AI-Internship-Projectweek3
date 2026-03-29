"""
Multi-Agent Customer Support System -- ADK + MCP + Local Tools + A2A Returns

Usage:  Start returns A2A service first (for RETURNS scenario):
           uvicorn returns_agent:app --host 127.0.0.1 --port 8002
        Then:  python main.py
Note:   Disconnect VPN and clear proxy before running (MCP).
"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from google.genai import types
from mcp.client.stdio import StdioServerParameters

MODEL = "gemini-2.5-flash"

# --- Layer 1: Support Ticket Agent (local tools) ---

def search_tickets(customer_email: str) -> dict:
    """Search support tickets by customer email."""
    tickets = {
        "alice.johnson@example.com": [
            {"ticket": "TKT-2026-001", "subject": "Package shows delivered but not received", "status": "open", "priority": "high", "category": "shipping"},
        ],
        "bob.smith@example.com": [
            {"ticket": "TKT-2026-002", "subject": "Want to cancel my pending order", "status": "open", "priority": "medium", "category": "billing"},
        ],
        "grace.kim@example.com": [
            {"ticket": "TKT-2026-007", "subject": "Thunderbolt dock not connecting", "status": "open", "priority": "urgent", "category": "technical"},
        ],
        "frank.garcia@example.com": [
            {"ticket": "TKT-2026-006", "subject": "Wrong item in package", "status": "in_progress", "priority": "high", "category": "product"},
        ],
    }
    return tickets.get(customer_email.lower(), {"message": f"No tickets found for {customer_email}"})

def create_ticket(customer_email: str, subject: str, priority: str, category: str) -> dict:
    """Create a new support ticket. Priority: low/medium/high/urgent. Category: billing/shipping/product/technical/general."""
    return {"ticket": "TKT-2026-016", "customer": customer_email, "subject": subject,
            "priority": priority, "category": category, "status": "open", "message": "Ticket created successfully."}

def update_ticket_status(ticket_number: str, new_status: str) -> dict:
    """Update a ticket's status. Valid: open, in_progress, waiting_on_customer, resolved, closed."""
    return {"ticket": ticket_number, "status": new_status, "message": f"Ticket {ticket_number} updated to {new_status}."}

support_agent = Agent(
    name="support_ticket_agent", model=MODEL,
    description="Handles support tickets: lookups, creation, status updates, complaints, and issue resolution.",
    instruction="You are a support ticket specialist. Use search_tickets to find tickets by email, "
                "create_ticket to open new tickets, and update_ticket_status to change ticket status.",
    tools=[search_tickets, create_ticket, update_ticket_status],
)

# --- Layer 2: Order Tracking Agent (MCP -> Supabase) ---

TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN", "")
PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF", "")

if not TOKEN:
    print("WARNING: SUPABASE_ACCESS_TOKEN not set -- order agent won't work.")

mcp_args = ["-y", "@supabase/mcp-server-supabase@latest", "--access-token", TOKEN]
if PROJECT_REF:
    mcp_args += ["--project-ref", PROJECT_REF]

supabase_mcp = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(command="npx", args=mcp_args),
        timeout=30.0,
    ),
)

order_agent = Agent(
    name="order_tracking_agent", model=MODEL,
    description="Order tracking agent with real Supabase database access via MCP.",
    instruction="You are an order tracking specialist. Use MCP tools to query customers, orders, and support_tickets.",
    tools=[supabase_mcp],
)

# --- Layer 3: Returns Agent (A2A -> remote service on port 8002) ---

returns_a2a_agent = RemoteA2aAgent(
    name="returns_agent",
    agent_card="http://localhost:8002",
    description="Remote agent for returns, refunds, RMA, and exchange eligibility via A2A.",
)

# --- Root Router ---

root_agent = Agent(
    name="customer_support_router", model=MODEL,
    instruction="Route to order_tracking_agent (orders, shipping, deliveries, order status) "
                "or support_ticket_agent (tickets, complaints, issues, creating/updating tickets) "
                "or returns_agent (returns, refunds, RMA, exchange eligibility, initiating returns). "
                "Never answer directly.",
    sub_agents=[order_agent, support_agent, returns_a2a_agent],
)

# --- Runner ---

async def ask(agent, message):
    service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="demo", session_service=service)
    session = await service.create_session(app_name="demo", user_id="user1")
    content = types.Content(role="user", parts=[types.Part(text=message)])
    async for event in runner.run_async(user_id="user1", session_id=session.id, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            return event.content.parts[0].text
    return "(no response)"

async def main():
    scenarios = [
        ("ORDER (MCP/Supabase)", "What is the status of order ORD-2026-007? Who placed it?"),
        ("SUPPORT (Local)", "I'm grace.kim@example.com. What open tickets do I have?"),
        ("SUPPORT (Local)", "Create a high priority shipping ticket for bob.smith@example.com about a damaged package."),
        # Requires: uvicorn returns_agent:app --host 127.0.0.1 --port 8002
        ("RETURNS (A2A)", "I'm grace.kim@example.com. Am I eligible to return order ORD-2026-007?"),
    ]
    for label, query in scenarios:
        print(f"\n--- {label} ---")
        print(f"User: {query}\n")
        print(f"Agent: {await ask(root_agent, query)}\n")

if __name__ == "__main__":
    asyncio.run(main())
