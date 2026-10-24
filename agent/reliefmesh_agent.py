"""ReliefMesh Buyer Agent: a Fetch.ai uAgent that operates ReliefMesh from an ASI:One conversation.

Every reply is assembled from real ReliefMesh API responses. The agent holds an
organization-scoped token that can create missions, run evidence checks and discovery,
optimize, and explain decisions. It cannot approve plans, issue purchase orders, move
money, or override policy; ReliefMesh rejects those calls for agent tokens.

Runs two ways:
- Agentverse hosted agent: paste this file into the hosted editor; `agent` is predefined.
  Set secrets RELIEFMESH_API_URL, RELIEFMESH_AGENT_TOKEN, optional ASI1_API_KEY.
- Local mailbox agent: `python reliefmesh_agent.py` with the same environment variables
  plus AGENT_SEED; connect the mailbox from the printed inspector URL.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    EndSessionContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

API_URL = os.environ.get("RELIEFMESH_API_URL", "http://127.0.0.1:8100").rstrip("/")
APP_URL = os.environ.get("RELIEFMESH_APP_URL", "").rstrip("/")
AGENT_TOKEN = os.environ.get("RELIEFMESH_AGENT_TOKEN", "")
ASI1_API_KEY = os.environ.get("ASI1_API_KEY", "")
ASI1_URL = "https://api.asi1.ai/v1/chat/completions"
ASI1_MODEL = os.environ.get("ASI1_MODEL", "asi1-mini")

HELP = (
    "I am the **ReliefMesh Buyer Agent**. I operate a real emergency-procurement workspace:\n"
    "- `create a mission for 300 blankets delivered to Oakland, CA within 24 hours under $8,000`\n"
    "- `show wildfire events in California` (live NASA EONET)\n"
    "- `status` / `brief` for the current mission (quotes, policy, plan, disruptions)\n"
    "- `run evidence checks` (live OFAC, SAM.gov, openFDA, USAspending)\n"
    "- `find suppliers for N95 masks` (Apify discovery; results are leads, never quotes)\n"
    "- `optimize` (deterministic policy + integer optimizer)\n"
    "- `why was Pioneer rejected?`\n"
    "I cannot approve spending or send purchase orders. A human coordinator does that in ReliefMesh."
)


class ReliefMeshClient:
    def __init__(self, base: str, token: str) -> None:
        self.base = base
        self.headers = {"Authorization": f"Bearer {token}"}

    async def call(self, method: str, path: str, body: Any = None) -> Any:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, f"{self.base}{path}", headers=self.headers, json=body)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail")
            except ValueError:
                detail = response.text[:200]
            raise RuntimeError(f"ReliefMesh refused ({response.status_code}): {detail}")
        return response.json()


def money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


# ----- deterministic intent parsing (also validates LLM tool arguments) -----

def parse_deadline_hours(text: str) -> int:
    lowered = text.lower()
    match = re.search(r"(?:within|in|next)\s+(\d+)\s*(hours?|hrs?|h|days?|d)\b", lowered)
    if match:
        amount = int(match.group(1))
        return amount * 24 if match.group(2).startswith("d") else amount
    if "tomorrow" in lowered:
        return 24
    if "tonight" in lowered or "today" in lowered:
        return 12
    if "this week" in lowered:
        return 120
    return 72


def parse_mission(text: str) -> dict[str, Any] | None:
    quantity_item = re.search(r"(\d[\d,]*)\s+((?:[a-z0-9][\w-]*\s?){1,4}?)\s*(?=delivered|deliver|to\b|for\b|in\b|by\b|under\b|within\b|,|$)",
                              text, re.IGNORECASE)
    if not quantity_item:
        return None
    quantity = int(quantity_item.group(1).replace(",", ""))
    item = quantity_item.group(2).strip().lower()
    location_match = re.search(r"\b(?:to|in|at)\s+([A-Z][A-Za-z .'-]+?,\s*[A-Z]{2})\b", text) or \
        re.search(r"\b(?:to|in|at)\s+([A-Z][A-Za-z .'-]{2,40}?)(?=\s+(?:by|within|under|in|before)\b|[,.]|$)", text)
    budget_match = re.search(r"\$\s?([\d,]+(?:\.\d{1,2})?)\s*(k)?", text, re.IGNORECASE) or \
        re.search(r"(?:under|budget(?: of)?|max(?:imum)?)\s+([\d,]+(?:\.\d{1,2})?)\s*(k)?", text, re.IGNORECASE)
    if not (location_match and budget_match):
        return None
    budget = float(budget_match.group(1).replace(",", "")) * (1000 if budget_match.group(2) else 1)
    location = location_match.group(1).strip()
    event = re.search(r"\b(EONET_\d+)\b", text)
    return {
        **({"emergency_event_id": event.group(1)} if event else {}),
        "name": f"{item.title()} for {location.split(',')[0]}",
        "delivery_location": location,
        "deadline_hours": parse_deadline_hours(text),
        "budget": f"{budget:.2f}",
        "requirements": [{"item": item, "quantity": quantity}],
    }


def classify(text: str) -> tuple[str, dict[str, Any]]:
    lowered = text.lower().strip()
    if re.search(r"\b(create|start|open|new)\b.*\bmission\b|\bneed\b.*\d", lowered):
        parsed = parse_mission(text)
        return ("create_mission", parsed or {}) if parsed else ("clarify_mission", {})
    if re.search(r"\b(event|events|emergenc|wildfire|storm|flood|volcano|disaster)", lowered) and \
            re.search(r"\b(show|list|find|what|which|any|current|active)\b", lowered):
        category = next((c for c, words in {"wildfires": ("wildfire", "fire"), "severeStorms": ("storm", "hurricane"),
                                             "floods": ("flood",), "volcanoes": ("volcan",)}.items()
                         if any(w in lowered for w in words)), None)
        return "find_events", {"category": category, "query": text}
    match = re.search(r"\b(?:why|explain)\b.*?\b(?:was|is|did|about)?\s*([A-Za-z][\w .&'-]{2,60}?)\s*(?:rejected|excluded|blocked|"
                      r"zero|not chosen|get zero|left out|allocated|\?|$)", text, re.IGNORECASE)
    if match and re.search(r"\b(why|explain)\b", lowered):
        name = re.sub(r"^(?:(?:was|is|did|does|the|supplier|vendor)\s+)+", "", match.group(1).strip(), flags=re.IGNORECASE)
        return "explain", {"supplier": name}
    if re.search(r"\b(evidence|screen|sanction|ofac|compliance)\b", lowered):
        return "evidence", {}
    if re.search(r"\b(find|discover|search|source)\b.*\b(supplier|vendor|lead)s?\b", lowered):
        topic = re.sub(r".*\b(?:for|of)\b\s*", "", text, flags=re.IGNORECASE).strip() or "relief supplies"
        return "discover", {"query": topic}
    if re.search(r"\b(optimi[sz]e|replan|allocate|plan it|run the plan|compute)\b", lowered):
        return "optimize", {}
    if re.search(r"\b(disrupt|withdr|what changed|what happened|recover)", lowered):
        return "disruption", {}
    if re.search(r"\b(status|brief|summary|update|where are we|plan|missions?)\b", lowered):
        return "brief", {}
    return "help", {}


# ----- tool execution against the real API -----

async def current_mission(client: ReliefMeshClient, ctx: Context | None, sender: str) -> dict[str, Any] | None:
    overview = await client.call("GET", "/v1/agent/overview")
    missions = overview["missions"]
    remembered = ctx.storage.get(f"mission:{sender}") if ctx else None
    for mission in missions:
        if mission["id"] == remembered:
            return mission
    return missions[0] if missions else None


def remember(ctx: Context | None, sender: str, mission_id: str) -> None:
    if ctx:
        ctx.storage.set(f"mission:{sender}", mission_id)


def link(mission_id: str) -> str:
    return f" ([open in ReliefMesh]({APP_URL}/missions/{mission_id}))" if APP_URL else ""


async def run_tool(client: ReliefMeshClient, intent: str, args: dict[str, Any], ctx: Context | None, sender: str) -> str:
    if intent == "help":
        return HELP
    if intent == "clarify_mission":
        return ("To create a mission I need a quantity + item, a US delivery location (City, ST), and a budget, e.g. "
                "`create a mission for 300 blankets delivered to Oakland, CA within 24 hours under $8,000`.")
    if intent == "find_events":
        params = f"?category={args['category']}" if args.get("category") else ""
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(f"{client.base}/v1/emergency-events{params}")
            response.raise_for_status()
            events = response.json()
        state = re.search(r"\b(california|oregon|washington|texas|florida|arizona|colorado|nevada|alaska|hawaii)\b",
                          args.get("query", "").lower())
        if state:
            events = [e for e in events if state.group(1) in e["title"].lower() or
                      (e.get("state") and e["state"].lower() == state.group(1)[:2])] or events
        if not events:
            return "NASA EONET reports no open events for that query right now."
        lines = [f"**Open NASA EONET events** ({events[0]['provenance']}, retrieved {events[0]['retrieved_at'][:16]}Z):"]
        for event in events[:6]:
            point = event.get("point") or {}
            lines.append(f"- `{event['id']}` {event['title']} · {', '.join(c['title'] for c in event['categories'])}"
                         + (f" · {point.get('lat', 0):.2f},{point.get('lon', 0):.2f}" if point else ""))
        lines.append("Say `create a mission for <qty> <item> delivered to <City, ST> under $<budget> for event <id>`.")
        return "\n".join(lines)
    if intent == "create_mission":
        body = dict(args)
        event = re.search(r"(EONET_\d+)", ctx.storage.get(f"last_text:{sender}") or "") if ctx else None
        if args.get("emergency_event_id") or event:
            body["emergency_event_id"] = args.get("emergency_event_id") or event.group(1)
        mission = await client.call("POST", "/v1/agent/missions", body)
        remember(ctx, sender, mission["id"])
        event_line = f"\nLinked emergency: {mission['emergency_event']['title']} (LIVE NASA EONET)." \
            if mission.get("emergency_event") else ""
        return (f"Created mission **{mission['name']}**: {mission['requirements'][0]['quantity']} "
                f"{mission['requirements'][0]['item']} to {mission['delivery_location']} by "
                f"{mission['delivery_deadline'][:16]}Z, budget {money(mission['budget'])}.{event_line}{link(mission['id'])}\n"
                "Next: a coordinator sends RFQs (or say `find suppliers for <item>`). Suppliers submit binding quotes "
                "themselves; I never invent prices or inventory.")

    mission = await current_mission(client, ctx, sender)
    if not mission:
        return "This organization has no missions yet. Try `create a mission for 300 blankets delivered to Oakland, CA under $8,000`."
    mission_id = mission["id"]
    remember(ctx, sender, mission_id)
    if intent == "evidence":
        result = await client.call("POST", f"/v1/missions/{mission_id}/evidence/refresh", {})
        brief = await client.call("GET", f"/v1/missions/{mission_id}/brief")
        lines = [f"Ran live evidence checks on {len(result['checked'])} supplier(s) for **{mission['name']}**:"]
        for row in brief["suppliers"]:
            findings = f" open findings: {', '.join(row['open_findings'])}" if row["open_findings"] else ""
            lines.append(f"- {row['name']}{' (TEST)' if row['is_test'] else ''}: **{row['status']}**{findings}")
        if result["policy_changes"]:
            lines.append("Policy changed for: " + "; ".join(f"{c['before']}→{c['after']}" for c in result["policy_changes"])
                         + ". The current plan was invalidated and an autonomous replan was queued.")
        return "\n".join(lines)
    if intent == "discover":
        job = await client.call("POST", f"/v1/missions/{mission_id}/discovery",
                                {"query": args.get("query") or "relief supplies", "max_results": 8})
        return (f"Started Apify supplier discovery for '{args.get('query')}' near {mission['delivery_location']} "
                f"(job `{job['id'][:8]}`). Results arrive as **leads** with public contact data only; a lead becomes a "
                "supplier only after accepting an RFQ and quoting.")
    if intent == "optimize":
        result = await client.call("POST", f"/v1/missions/{mission_id}/optimize")
        plan = await client.call("GET", f"/v1/plans/{result['plan_id']}")
        return describe_plan(mission, plan)
    if intent == "explain":
        explanation = await client.call("GET", f"/v1/missions/{mission_id}/explain?supplier={httpx.QueryParams({'q': args['supplier']})['q']}")
        if not explanation.get("found"):
            return explanation.get("message", "No matching supplier.")
        return explanation["explanation"].replace("\n", "\n- ").replace(": policy", ": policy", 1)
    brief = await client.call("GET", f"/v1/missions/{mission_id}/brief")
    if intent == "disruption":
        disruption = brief.get("latest_disruption")
        plan = brief.get("latest_plan")
        if not disruption:
            return f"No disruption recorded yet for **{mission['name']}**. Latest plan: " + \
                (f"v{plan['version']} {plan['status']} {money(plan['total_cost'])}." if plan else "none.")
        difference = (plan or {}).get("difference") or {}
        return (f"**Latest disruption:** {disruption['summary']} ({disruption['created_at'][:16]}Z).\n"
                f"Recovery: plan v{difference.get('previous_version')} → v{plan['version']} ({plan['status']}), "
                f"total {money(difference.get('total_cost_before'))} → {money(plan['total_cost'])} "
                f"(delta {difference.get('cost_delta')}). Why: {'; '.join(difference.get('why') or [])}.\n"
                f"Approval: {(brief.get('approval') or {}).get('status')}"
                + (" (" + str(brief["approval"].get("invalidation_reason")) + ")" if (brief.get("approval") or {}).get("invalidation_reason") else "")
                + ". A human coordinator must approve the new plan.")
    return describe_brief(brief)


def describe_plan(mission: dict[str, Any], plan: dict[str, Any]) -> str:
    if plan["status"] == "infeasible":
        shortages = "; ".join(f"{s['item']} short {s['shortage']} ({s['reason']})" for s in plan["shortages"])
        return f"Plan v{plan['version']} for **{mission['name']}** is infeasible: {shortages}."
    lines = [f"**Plan v{plan['version']}** ({plan['status']}) for {mission['name']}: total {money(plan['total_cost'])}, "
             f"remaining budget {money(plan['remaining_budget'])}."]
    for row in plan["allocations"]:
        name = plan["policy"]["suppliers"].get(row["supplier_id"], {}).get("legal_name") or row["supplier_email"]
        lines.append(f"- {name}: {row['quantity']} {row['item']} × {money(row['unit_price'])} = {money(row['line_cost'])}")
    withheld = [r for r in plan["rejected_quotes"] if r["reason"].startswith("policy")]
    for row in withheld:
        name = plan["policy"]["suppliers"].get(row.get("supplier_id"), {}).get("legal_name") or row.get("supplier_email")
        lines.append(f"- Withheld by policy: {name} ({', '.join(row.get('rules') or [])})")
    lines.append("This plan needs a human approval in ReliefMesh before any purchase order exists." + link(mission["id"]))
    return "\n".join(lines)


def describe_brief(brief: dict[str, Any]) -> str:
    mission = brief["mission"]
    plan = brief.get("latest_plan")
    needs = ", ".join(str(r["quantity"]) + " " + r["item"] for r in mission["requirements"])
    lines = [f"**{mission['name']}**: {needs} to {mission['delivery_location']}, budget {money(mission['budget'])}."]
    if brief.get("event"):
        lines.append(f"Emergency: {brief['event']['title']}.")
    lines.append(f"Quotes: {brief['quotes']['active']} active of {brief['quotes']['total']}. Leads: {brief['leads']['total']}.")
    for row in brief["suppliers"]:
        lines.append(f"- {row['name']}{' (TEST)' if row['is_test'] else ''}: {row['status']}"
                     + (f" — {', '.join(row['open_findings'])}" if row["open_findings"] else ""))
    if plan:
        lines.append(f"Latest plan v{plan['version']} {plan['status']} {money(plan['total_cost'])}"
                     + (f" (delta {plan['difference']['cost_delta']})" if (plan.get("difference") or {}).get("cost_delta") else "") + ".")
    if brief.get("approval"):
        lines.append(f"Approval: {brief['approval']['status']}.")
    lines.extend(f"· {message}" for message in brief["recent_notifications"][:3])
    return "\n".join(lines) + link(mission["id"])


# ----- optional ASI:One LLM routing (tool selection only; the API remains the authority) -----

TOOLS = [
    {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}
    for name, description, parameters in [
        ("create_mission", "Create a procurement mission", {"type": "object", "properties": {
            "item": {"type": "string"}, "quantity": {"type": "integer"}, "delivery_location": {"type": "string",
            "description": "City, ST"}, "deadline_hours": {"type": "integer"}, "budget": {"type": "number"},
            "emergency_event_id": {"type": "string"}}, "required": ["item", "quantity", "delivery_location", "budget"]}),
        ("find_events", "List open NASA EONET emergency events", {"type": "object", "properties": {
            "category": {"type": "string", "enum": ["wildfires", "severeStorms", "floods", "volcanoes"]}}}),
        ("brief", "Summarize the current mission", {"type": "object", "properties": {}}),
        ("evidence", "Run supplier evidence checks", {"type": "object", "properties": {}}),
        ("discover", "Discover supplier leads", {"type": "object", "properties": {"query": {"type": "string"}},
                                                  "required": ["query"]}),
        ("optimize", "Run the policy-gated optimizer", {"type": "object", "properties": {}}),
        ("explain", "Explain a supplier's allocation or rejection", {"type": "object", "properties": {
            "supplier": {"type": "string"}}, "required": ["supplier"]}),
        ("disruption", "Describe the latest disruption and recovery", {"type": "object", "properties": {}}),
        ("help", "Explain what the agent can do", {"type": "object", "properties": {}}),
    ]
]


async def route_with_asi1(text: str) -> tuple[str, dict[str, Any]] | None:
    if not ASI1_API_KEY:
        return None
    body = {"model": ASI1_MODEL, "tools": TOOLS, "tool_choice": "required", "temperature": 0,
            "messages": [{"role": "system", "content": "Route the user's request to exactly one ReliefMesh tool. "
                          "Never invent quantities, prices, or locations the user did not state."},
                         {"role": "user", "content": text}]}
    try:
        async with httpx.AsyncClient(timeout=25) as http:
            response = await http.post(ASI1_URL, json=body, headers={"Authorization": f"Bearer {ASI1_API_KEY}"})
        response.raise_for_status()
        call = response.json()["choices"][0]["message"]["tool_calls"][0]["function"]
        args = json.loads(call["arguments"] or "{}")
    except Exception:  # routing falls back to the deterministic parser
        return None
    if call["name"] == "create_mission":
        if not all(args.get(k) for k in ("item", "quantity", "delivery_location", "budget")):
            return "clarify_mission", {}
        args = {"name": f"{str(args['item']).title()} for {str(args['delivery_location']).split(',')[0]}",
                "delivery_location": args["delivery_location"],
                "deadline_hours": int(args.get("deadline_hours") or parse_deadline_hours(text)),
                "budget": f"{float(args['budget']):.2f}",
                "requirements": [{"item": str(args["item"]).lower(), "quantity": int(args["quantity"])}],
                **({"emergency_event_id": args["emergency_event_id"]} if args.get("emergency_event_id") else {})}
    return call["name"], args


async def answer(text: str, ctx: Context | None = None, sender: str = "local") -> str:
    if not AGENT_TOKEN:
        return "ReliefMesh agent token is not configured on this agent (RELIEFMESH_AGENT_TOKEN)."
    if ctx:
        previous = ctx.storage.get(f"last_text:{sender}") or ""
        ctx.storage.set(f"last_text:{sender}", (previous + " " + text)[-600:])
    routed = await route_with_asi1(text)
    intent, args = routed or classify(text)
    try:
        return await run_tool(ReliefMeshClient(API_URL, AGENT_TOKEN), intent, args, ctx, sender)
    except Exception as exc:
        return f"I could not complete that: {exc}"


# ----- Agent Chat Protocol wiring -----

try:
    agent  # type: ignore[name-defined]  # predefined on Agentverse hosted agents
except NameError:
    agent = Agent(
        name="reliefmesh-buyer-agent",
        seed=os.environ.get("AGENT_SEED", "reliefmesh-buyer-agent-local-dev-seed"),
        port=int(os.environ.get("AGENT_PORT", "8001")),
        mailbox=True,
        publish_agent_details=True,
        description="Emergency procurement agent: creates missions from real emergencies, screens suppliers against "
                    "OFAC/SAM/openFDA, runs a policy-gated optimizer, and explains autonomous replans. Never approves spend.",
        readme_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
    )

chat = Protocol(spec=chat_protocol_spec)


def reply(text: str, end: bool = False) -> ChatMessage:
    content: list[Any] = [TextContent(type="text", text=text)]
    if end:
        content.append(EndSessionContent(type="end-session"))
    return ChatMessage(timestamp=datetime.now(timezone.utc), msg_id=uuid4(), content=content)


@chat.on_message(ChatMessage)
async def handle_chat(ctx: Context, sender: str, msg: ChatMessage) -> None:
    await ctx.send(sender, ChatAcknowledgement(timestamp=datetime.now(timezone.utc), acknowledged_msg_id=msg.msg_id))
    if any(isinstance(item, StartSessionContent) for item in msg.content) and not msg.text().strip():
        await ctx.send(sender, reply(HELP))
        return
    text = msg.text().strip()
    if not text:
        return
    ctx.logger.info(f"chat from {sender[:16]}: {text[:120]}")
    await ctx.send(sender, reply(await answer(text, ctx, sender)))


@chat.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement) -> None:
    ctx.logger.debug(f"ack {msg.acknowledged_msg_id} from {sender[:16]}")


agent.include(chat, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
