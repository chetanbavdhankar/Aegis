"""
AEGIS Verification Agent — Mistral Agents API with web_search tool.

Architecture:
  1. Create a Mistral Agent with web_search built-in tool (once, on startup).
  2. Agent generates smart search queries (multilingual, location-aware).
  3. We execute searches via DuckDuckGo (news + web) client-side.
  4. Feed results back to the agent for analysis.
  5. Agent returns structured verification JSON.

This is a true Mistral Agent workflow — the LLM plans the search strategy,
we execute, and it synthesizes the results.
"""
import json
import logging
import requests as http_requests
from duckduckgo_search import DDGS
from backend.config import MISTRAL_API_KEY, MISTRAL_AGENT_MODEL
from backend import db

logger = logging.getLogger("aegis.agent")

_MISTRAL_BASE = "https://api.mistral.ai/v1"
_agent_id: str | None = None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }


def _ensure_agent() -> str:
    """Create the AEGIS verification agent on Mistral's platform (once per process)."""
    global _agent_id
    if _agent_id:
        return _agent_id

    logger.info("Creating Mistral verification agent...")
    resp = http_requests.post(
        f"{_MISTRAL_BASE}/agents",
        headers=_headers(),
        json={
            "model": MISTRAL_AGENT_MODEL,
            "name": "AEGIS-Verifier",
            "instructions": _AGENT_INSTRUCTIONS,
            "tools": [{"type": "web_search"}],
            "completion_args": {"temperature": 0.1},
        },
        timeout=15,
    )
    data = resp.json()

    if "id" not in data:
        raise RuntimeError(f"Failed to create Mistral agent: {data}")

    _agent_id = data["id"]
    logger.info("Mistral agent created: %s", _agent_id)
    return _agent_id


_AGENT_INSTRUCTIONS = """You are AEGIS Verification Agent. Your job is to verify emergency incident reports
by searching the web for corroborating evidence.

When given an incident report:
1. Use web_search to find related news, government alerts, or social media reports.
2. Search MULTIPLE times with different queries:
   - In English (e.g., "flood Juiz de Fora Brazil")
   - In the LOCAL language (e.g., "enchente Juiz de Fora")
   - With date context (add "2026" or "today" or "recent")
3. ALWAYS use the EXACT location from the report. NEVER substitute a different location.
4. After searching, return ONLY a valid JSON object (no markdown):

{
  "verification_status": "<verified|partially_verified|unverified|contradicted>",
  "confidence_score": <integer 1-10>,
  "summary": "<2-3 sentences explaining what evidence you found, citing specific sources>",
  "sources": ["<url1>", "<url2>"]
}

Rules:
- Never hallucinate sources — only cite what the search returned.
- If no results found, return confidence_score=3 and status="unverified".
- Use the GPS coordinates to identify the correct location if provided."""


def reverse_geocode(lat: float, lng: float) -> str:
    """Convert GPS coordinates to a human-readable location via Nominatim."""
    try:
        resp = http_requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={"lat": lat, "lon": lng, "format": "json", "zoom": 10},
            headers={"User-Agent": "AEGIS-CrisisSystem/1.0"},
            timeout=5,
        )
        data = resp.json()
        name = data.get("display_name", "")
        parts = [p.strip() for p in name.split(",")]
        return ", ".join(parts[:3]) if parts else name
    except Exception as e:
        logger.warning("Reverse geocode failed for %.4f,%.4f: %s", lat, lng, e)
        return ""


# ── DuckDuckGo search executors ─────────────────────────────────────────────

def _execute_web_search(query: str) -> str:
    """Execute a real DuckDuckGo web + news search for maximum coverage."""
    logger.info("Executing search: %s", query)
    results = []
    try:
        with DDGS() as ddgs:
            # Web search
            for r in ddgs.text(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                })
            # News search
            for r in ddgs.news(query, max_results=5):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("url", ""),
                    "source": r.get("source", ""),
                    "date": r.get("date", ""),
                })
    except Exception as e:
        logger.warning("Search failed for '%s': %s", query, e)
        results.append({"title": "Search error", "snippet": str(e), "url": ""})

    if not results:
        results.append({"title": "No results", "snippet": "No relevant results found.", "url": ""})

    logger.info("Search returned %d results for: %s", len(results), query)
    return json.dumps(results, ensure_ascii=False)


def _agent_complete(agent_id: str, messages: list) -> dict:
    """Call Mistral agents/completions endpoint and return the response."""
    resp = http_requests.post(
        f"{_MISTRAL_BASE}/agents/completions",
        headers=_headers(),
        json={"agent_id": agent_id, "messages": messages},
        timeout=60,
    )
    return resp.json()


def verify_incident(
    alert_id: int,
    incident_type: str,
    location_text: str,
    lat: float = None,
    lng: float = None,
) -> dict:
    """
    Run the Mistral verification agent for a given alert.
    The agent generates search queries → we execute them → agent analyzes results.
    """
    # ── Resolve location ─────────────────────────────────────────────────────
    geo_location = ""
    if lat is not None and lng is not None:
        geo_location = reverse_geocode(lat, lng)
        if geo_location:
            db.update_alert_location_name(alert_id, geo_location)

    effective_location = geo_location or location_text or "unknown location"
    logger.info(
        "Starting verification for alert #%d: type=%s, location=%s",
        alert_id, incident_type, effective_location,
    )

    try:
        agent_id = _ensure_agent()

        user_content = (
            f"Verify this incident report:\n"
            f"Type: {incident_type}\n"
            f"Location: {effective_location}\n"
            f"{'GPS: ' + str(lat) + ', ' + str(lng) if lat is not None else ''}\n"
            f"Search the web to check if this is real and currently happening."
        )

        messages = [{"role": "user", "content": user_content}]

        # ── Multi-round tool calling loop ────────────────────────────────────
        max_rounds = 4
        for round_num in range(max_rounds):
            data = _agent_complete(agent_id, messages)

            if "choices" not in data:
                raise RuntimeError(f"Agent API error: {data}")

            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", [])

            if not tool_calls or choice.get("finish_reason") != "tool_calls":
                # Agent is done — content should have the final answer
                break

            logger.info("Round %d: %d tool calls", round_num + 1, len(tool_calls))

            # Record assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            # Execute each search and feed results back
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                query = args.get("query", f"{incident_type} {effective_location}")

                search_result = _execute_web_search(query)

                messages.append({
                    "role": "tool",
                    "name": fn_name,
                    "content": search_result,
                    "tool_call_id": tc["id"],
                })
        else:
            # Exhausted rounds — force a final response
            messages.append({
                "role": "user",
                "content": "Stop searching and return your verification JSON now.",
            })
            data = _agent_complete(agent_id, messages)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # ── Parse the final JSON ─────────────────────────────────────────────
        if not content or not content.strip().startswith("{"):
            # Force JSON if the agent didn't produce it
            messages.append({"role": "assistant", "content": content or ""})
            messages.append({
                "role": "user",
                "content": "Return ONLY a JSON object with verification_status, confidence_score, summary, sources.",
            })
            data = _agent_complete(agent_id, messages)
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Clean markdown fencing if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        status = result.get("verification_status", "unverified")
        score = int(result.get("confidence_score", 3))
        summary = result.get("summary", "Verification completed.")

        # Append sources to summary
        sources = result.get("sources", [])
        if sources and isinstance(sources, list):
            source_list = " | ".join(s for s in sources[:3] if s)
            if source_list:
                summary = f"{summary}\n\nSources: {source_list}"

        logger.info("Verification for alert #%d: %s (score=%d)", alert_id, status, score)

    except Exception as e:
        logger.error("Verification agent error for alert #%d: %s", alert_id, e)
        status, summary, score = "pending", f"Verification failed: {e}", 0

    db.update_alert_verification(alert_id, status, summary, score)
    return {"verification_status": status, "summary": summary, "confidence_score": score}
