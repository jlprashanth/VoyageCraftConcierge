"""Minimal FastAPI proxy for a deployed A2A agent (Agent Runtime, agents-cli 1.1.0+).

The browser talks ONLY to this proxy (same origin, no CORS, no GCP creds in the
browser). The proxy authenticates with Application Default Credentials and
forwards chat to the deployed agent over the A2A protocol, returning replies as
structured parts the chat UI knows how to show:

  * {"kind": "text", "text": ...}  -> a normal chat bubble
  * {"kind": "a2ui", "data": ...}  -> one A2UI message (beginRendering /
    surfaceUpdate); static/index.html renders these as a card.

Why A2A: agents-cli 1.1.0 (GA) deploys ADK agents to Agent Runtime as A2A agents
and no longer registers the reasoning-engine operation schema the old
`agent_engines.get(...).stream_query()` path relied on (operation_schemas() comes
back empty). The container serves the A2A protocol over the Agent Engine HTTP
passthrough, so this proxy fetches the agent's card and sends messages with the
a2a-sdk client (the same path `agents-cli run --mode a2a` uses). This works for
both A2A and plain ADK 1.1.0 deployments (the container serves A2A either way).

Run:
  pip install -r requirements.txt
  export AGENT_ENGINE_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
  export AGENT_DIRECTORY="app"   # your agent's app directory (agents-cli-manifest.yaml)
  python main.py                 # -> http://localhost:8080
"""

import os
import uuid

import google.auth
import google.auth.transport.requests
import httpx
from a2a.client.client_factory import ClientConfig, ClientFactory, TransportProtocol
from a2a.types import (
    AgentCard,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

RESOURCE = os.environ["AGENT_ENGINE_RESOURCE_NAME"]
# The agent's app directory (matches agent_directory in agents-cli-manifest.yaml).
AGENT_DIRECTORY = os.environ.get("AGENT_DIRECTORY", "app")

def _resolve_service_url() -> str:
    if RESOURCE.startswith("http://") or RESOURCE.startswith("https://"):
        return RESOURCE.rstrip("/")
    try:
        import subprocess, json
        out = subprocess.run(["gcloud", "run", "services", "list", "--format=json"], capture_output=True, text=True)
        svcs = json.loads(out.stdout)
        if svcs:
            return svcs[0]["status"]["url"]
    except Exception:
        pass
    return "https://voyagecraft-concierge-1069236132412.us-east1.run.app"


SERVICE_URL = _resolve_service_url()
A2A_BASE = f"{SERVICE_URL}/a2a/{AGENT_DIRECTORY}"
A2A_CARD_URL = f"{A2A_BASE}/.well-known/agent-card.json"

# The agent tags its A2UI data parts with this mime type.
_A2UI_MIME = "application/json+a2ui"

# One set of ADC credentials, refreshed per request (access tokens expire ~1h).
_creds, _ = google.auth.default(
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    try:
        import google.auth.transport.requests
        if SERVICE_URL.startswith("http"):
            import google.oauth2.id_token
            auth_req = google.auth.transport.requests.Request()
            token = google.oauth2.id_token.fetch_id_token(auth_req, SERVICE_URL)
            headers["Authorization"] = f"Bearer {token}"
        else:
            _creds.refresh(google.auth.transport.requests.Request())
            headers["Authorization"] = f"Bearer {_creds.token}"
    except Exception:
        pass
    return headers


app = FastAPI()


@app.exception_handler(Exception)
async def _json_errors(request: Request, exc: Exception):
    # Always return JSON so the browser never receives a plain-text 500 page
    # (which shows up in the chat as "Unexpected token 'I', "Internal S"... is
    # not valid JSON"). Any server-side failure now surfaces as a readable
    # message in the chat bubble instead.
    return JSONResponse(
        status_code=200,
        content={
            "parts": [{"kind": "text", "text": f"Error: {type(exc).__name__}: {exc}"}]
        },
    )


# Reuse ONE A2A context per user so the agent remembers the conversation.
_contexts: dict[str, str] = {}
# Cache the agent card after the first fetch.
_card: AgentCard | None = None


async def _get_card(client: httpx.AsyncClient) -> AgentCard:
    global _card
    if _card is None:
        try:
            resp = await client.get(A2A_CARD_URL)
            resp.raise_for_status()
            card = AgentCard(**resp.json())
            card.url = A2A_BASE
            _card = card
        except Exception:
            from a2a.types import AgentInterface
            card = AgentCard(name=AGENT_DIRECTORY)
            target_url = RESOURCE if (RESOURCE.startswith("http://") or RESOURCE.startswith("https://")) else A2A_BASE
            card.supported_interfaces.append(AgentInterface(url=target_url, protocol_binding="JSONRPC"))
            _card = card
    return _card


def _extract_parts(parts: list) -> list[dict]:
    """Turn A2A response parts into structured parts for the chat UI.

    Text parts pass through as {"kind": "text"}. A2UI data parts (tagged
    application/json+a2ui) become {"kind": "a2ui", "data": <message>} so the UI
    renders the card; each data part is one A2UI message (beginRendering or
    surfaceUpdate).
    """
    out: list[dict] = []
    for p in parts:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            out.append({"kind": "text", "text": text})
            continue
        data = getattr(root, "data", None)
        if data is not None:
            meta = getattr(root, "metadata", None) or {}
            mime = meta.get("mimeType") if isinstance(meta, dict) else getattr(root, "media_type", None)
            if mime == _A2UI_MIME or (isinstance(data, dict) and any(k in data for k in ("beginRendering", "surfaceUpdate"))):
                out.append({"kind": "a2ui", "data": data})
            continue
        url = getattr(root, "url", None)
        if url:
            out.append({"kind": "text", "text": url})
    return out


def _process_a2a_event(event, parts_list: list, contexts_dict: dict, user_id: str):
    print("EVENT RECEIVED:", type(event), event, flush=True)
    if not event:
        return
    if isinstance(event, tuple):
        for item in event:
            _process_a2a_event(item, parts_list, contexts_dict, user_id)
        return

    ctx_id = getattr(event, "context_id", None)
    if ctx_id:
        contexts_dict[user_id] = ctx_id

    # Check protobuf WhichOneof if present
    if hasattr(event, "WhichOneof"):
        try:
            field = event.WhichOneof("response")
            if field:
                sub = getattr(event, field, None)
                if sub:
                    _process_a2a_event(sub, parts_list, contexts_dict, user_id)
                    return
        except Exception:
            pass

    # Check task sub-object
    t = getattr(event, "task", None)
    if t is not None and t is not event:
        _process_a2a_event(t, parts_list, contexts_dict, user_id)

    # Check artifact sub-object
    art = getattr(event, "artifact", None)
    if art is not None:
        parts_attr = getattr(art, "parts", None)
        if parts_attr:
            for p in _extract_parts(parts_attr):
                if p not in parts_list:
                    parts_list.append(p)

    # Check artifacts list
    artifacts = getattr(event, "artifacts", None)
    if artifacts:
        for a in artifacts:
            parts_attr = getattr(a, "parts", None)
            if parts_attr:
                for p in _extract_parts(parts_attr):
                    if p not in parts_list:
                        parts_list.append(p)

    # Check direct parts
    parts_attr = getattr(event, "parts", None)
    if parts_attr:
        for p in _extract_parts(parts_attr):
            if p not in parts_list:
                parts_list.append(p)


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    message = body.get("message", "")
    user_id = body.get("user_id") or "web-user"
    parts: list[dict] = []

    async with httpx.AsyncClient(headers=_auth_headers(), timeout=120) as client:
        card = await _get_card(client)
        try:
            config = ClientConfig(
                supported_protocol_bindings=["JSONRPC", "HTTP+JSON"],
                httpx_client=client,
            )
        except TypeError:
            config = ClientConfig(httpx_client=client)
        factory = ClientFactory(config)
        a2a_client = factory.create(card)

        from a2a.types import SendMessageRequest

        msg = Message(
            message_id=str(uuid.uuid4()),
            role=Role.ROLE_USER,
            parts=[Part(text=message)],
            context_id=_contexts.get(user_id),
        )
        req = SendMessageRequest(message=msg)

        async for event in a2a_client.send_message(req):
            _process_a2a_event(event, parts, _contexts, user_id)

    if not parts:
        # The turn produced no text or UI (e.g. the agent only ran tools, or a
        # tool stalled). Be honest rather than silent.
        parts = [{"kind": "text", "text": "(The agent didn't return a reply.)"}]
    return JSONResponse({"parts": parts})


# Serve the chat UI (keep this mount last so /chat wins).
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
