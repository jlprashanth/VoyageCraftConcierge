# Copyright 2026 Google LLC
#
# VoyageCraft Travel Concierge Agent Definition

import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.a2ui_utils import a2ui_callback
from app.tools import (
    add_destination,
    calculate_trip_budget,
    generate_destination_postcard,
    generate_destination_preview_video,
    get_destination_details,
    get_exchange_rate,
    search_destinations,
)

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are VoyageCraft, an expert travel concierge agent. Help users discover destinations, "
        "search destination catalogs in Firestore, view detailed activity recommendations, "
        "estimate itemized trip budgets, check real-time currency exchange rates, generate destination postcard images, "
        "and add new travel destinations to the system database."
    ),
    workflow_description=(
        "Analyze the request and return structured UI when appropriate.\n"
        "Memory & Personalization: You have long-term cross-session memory via Memory Bank. "
        "Actively pay attention to and remember all of the user's favorite destinations, preferred travel styles, activity preferences, and budget constraints. "
        "When the user expresses a favorite destination or preference (e.g., 'I love Kyoto', 'Add Paris to my favorite destinations', 'My favorite place is Kyoto'), "
        "acknowledge it clearly so it gets extracted into long-term memory. "
        "Always use these remembered favorite destinations and preferences to personalize future recommendations and trip suggestions.\n"
        "When performing code execution or Python calculations, write the Python code inside ```python ... ``` code blocks. "
        "The code blocks will be automatically executed in your Agent Engine sandbox environment. Do not attempt to call a function tool named run_code."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


async def generate_memories_callback(callback_context: CallbackContext):
    """WRITE: after each turn, send the session to Memory Bank for extraction."""
    await callback_context.add_session_to_memory()
    return None


# Load Agent Engine resource name from deployment_metadata.json
metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
agent_engine_name = None
if metadata_path.exists():
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
            agent_engine_name = (
                metadata.get("agent_engine_resource_name")
                or metadata.get("remote_agent_runtime_id")
            )
    except Exception:
        pass


def get_weather(query: str) -> str:
    """Simulates a web search for weather information.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Gets the current local time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    elif "tokyo" in query.lower() or "japan" in query.lower():
        tz_identifier = "Asia/Tokyo"
    elif "paris" in query.lower() or "france" in query.lower():
        tz_identifier = "Europe/Paris"
    else:
        tz_identifier = "UTC"

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=agent_engine_name
    ),
    instruction=a2ui_instruction,
    tools=[
        search_destinations,
        get_destination_details,
        add_destination,
        calculate_trip_budget,
        get_exchange_rate,
        generate_destination_postcard,
        generate_destination_preview_video,
        get_weather,
        get_current_time,
        PreloadMemoryTool(),
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
