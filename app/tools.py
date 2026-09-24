import inspect
import json
import os
import urllib.request
import uuid
from typing import Any

from google import genai
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

# HARDCODED Project ID & Bucket Name as required by Agent Platform standards
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-6c97d9d7ae82"
GCS_BUCKET_NAME = "voyagecraft-assets-1069236132412"


def _get_firestore_client() -> firestore.Client:
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def search_destinations(
    query: str = "", budget_tier: str = "", tag: str = ""
) -> list[dict[str, Any]]:
    """Searches travel destinations in the Firestore database by query keyword, budget tier, or tag.

    Args:
        query: Optional search keyword (matches city name, country, or description).
        budget_tier: Optional budget category ("budget", "moderate", "luxury").
        tag: Optional category tag (e.g., "coastal", "culture", "food", "beach", "temples").

    Returns:
        A list of matching destination records from Firestore.
    """
    db = _get_firestore_client()
    collection_ref = db.collection("destinations")
    docs = collection_ref.stream()

    results = []
    query_lower = query.lower().strip()
    budget_lower = budget_tier.lower().strip()
    tag_lower = tag.lower().strip()

    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id

        # Apply filters
        if budget_lower and data.get("budget_tier", "").lower() != budget_lower:
            continue

        if tag_lower:
            doc_tags = [t.lower() for t in data.get("tags", [])]
            if tag_lower not in doc_tags:
                continue

        if query_lower:
            match = (
                query_lower in data.get("name", "").lower()
                or query_lower in data.get("country", "").lower()
                or query_lower in data.get("description", "").lower()
            )
            if not match:
                continue

        results.append(data)

    return results


def get_destination_details(destination_id: str) -> dict[str, Any]:
    """Retrieves full details of a specific destination from Firestore by ID.

    Args:
        destination_id: Unique destination identifier (e.g., "san-francisco", "tokyo", "paris", "kyoto", "barcelona").

    Returns:
        Destination details dictionary or error dictionary if not found.
    """
    db = _get_firestore_client()
    doc_ref = db.collection("destinations").document(destination_id.lower().strip())
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Destination with ID '{destination_id}' not found."}

    data = doc.to_dict()
    data["id"] = doc.id
    return data


def add_destination(
    destination_id: str,
    name: str,
    country: str,
    description: str,
    budget_tier: str = "moderate",
    tags: list[str] = None,
    recommended_activities: list[str] = None,
    rating: float = 4.5,
) -> dict[str, Any]:
    """Adds a new destination record to the Firestore database.

    Args:
        destination_id: Unique slug identifier for the destination (e.g. "rome", "sydney").
        name: Name of the destination city or region.
        country: Country where the destination is located.
        description: Brief summary of what makes this destination special.
        budget_tier: Price level ("budget", "moderate", "luxury").
        tags: List of descriptive tags (e.g. ["history", "food"]).
        recommended_activities: List of top things to do.
        rating: Rating out of 5.0.

    Returns:
        Dictionary confirming creation status and destination payload.
    """
    db = _get_firestore_client()
    doc_id = destination_id.lower().strip().replace(" ", "-")

    dest_data = {
        "id": doc_id,
        "name": name,
        "country": country,
        "description": description,
        "budget_tier": budget_tier,
        "tags": tags or [],
        "recommended_activities": recommended_activities or [],
        "rating": float(rating),
    }

    db.collection("destinations").document(doc_id).set(dest_data)
    return {
        "status": "success",
        "message": f"Successfully saved destination '{name}'.",
        "destination": dest_data,
    }


def calculate_trip_budget(
    destination: str,
    duration_days: int = 5,
    travelers: int = 2,
    budget_tier: str = "moderate",
) -> dict[str, Any]:
    """Calculates estimated trip budget and itemized cost breakdown for a destination.

    Args:
        destination: Name of the destination (e.g. "Tokyo", "Paris", "San Francisco").
        duration_days: Number of days for the trip (default 5).
        travelers: Number of travelers in the party (default 2).
        budget_tier: Spending level ("budget", "moderate", "luxury").

    Returns:
        Dictionary containing itemized costs for flights, lodging, food, activities, transit, and total estimated USD.
    """
    tier = budget_tier.lower().strip()
    tier_rates = {
        "budget": {"lodging": 60, "food": 35, "activities": 25, "transit": 15, "flight": 300},
        "moderate": {"lodging": 160, "food": 75, "activities": 55, "transit": 30, "flight": 650},
        "luxury": {"lodging": 450, "food": 200, "activities": 150, "transit": 80, "flight": 1500},
    }

    rates = tier_rates.get(tier, tier_rates["moderate"])

    days = max(1, duration_days)
    people = max(1, travelers)

    flights_total = rates["flight"] * people
    lodging_total = rates["lodging"] * max(1, days - 1)
    food_total = rates["food"] * days * people
    activities_total = rates["activities"] * days * people
    transit_total = rates["transit"] * days * people

    total_usd = flights_total + lodging_total + food_total + activities_total + transit_total

    return {
        "destination": destination,
        "duration_days": days,
        "travelers": people,
        "budget_tier": budget_tier,
        "breakdown_usd": {
            "flights_total": flights_total,
            "lodging_total": lodging_total,
            "food_total": food_total,
            "activities_total": activities_total,
            "transit_total": transit_total,
        },
        "total_estimated_usd": total_usd,
        "estimated_per_person_usd": round(total_usd / people, 2),
    }


def get_exchange_rate(
    base_currency: str = "USD", target_currency: str = "JPY"
) -> dict[str, Any]:
    """Fetches real-time foreign exchange rate between currencies using a live public API.

    Args:
        base_currency: Base currency code (e.g. "USD", "EUR", "GBP").
        target_currency: Target currency code (e.g. "JPY", "EUR", "GBP", "CAD").

    Returns:
        Dictionary containing live exchange rate, base currency, target currency, and last update date.
    """
    import json
    import os
    import urllib.request

    base = base_currency.upper().strip()
    target = target_currency.upper().strip()

    api_key = os.getenv("EXCHANGE_RATE_API_KEY")
    if api_key:
        url = f"https://v6.exchangerate-api.com/v6/{api_key}/pair/{base}/{target}"
    else:
        url = f"https://api.exchangerate-api.com/v4/latest/{base}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VoyageCraft/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

            if "rates" in data:
                rate = data["rates"].get(target)
                if rate is None:
                    return {"error": f"Target currency '{target}' not supported."}
                return {
                    "base_currency": base,
                    "target_currency": target,
                    "exchange_rate": rate,
                    "last_updated": data.get("date"),
                }
            elif "conversion_rate" in data:
                return {
                    "base_currency": base,
                    "target_currency": target,
                    "exchange_rate": data["conversion_rate"],
                    "last_updated": data.get("time_last_update_utc"),
                }
            return {"error": "Unexpected API response structure."}
    except Exception as e:
        return {"error": f"Failed to fetch exchange rate: {str(e)}"}


async def generate_destination_postcard(
    destination: str,
    description: str = "",
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """Generates a high-quality postcard image for a travel destination using gemini-3.1-flash-lite-image,
    saves it as a session artifact for the Playground, and uploads it to public Cloud Storage.

    Args:
        destination: Name of the travel destination (e.g., "Kyoto", "Paris", "Hawaii").
        description: Optional visual prompt or scene description for the postcard.
        tool_context: ADK ToolContext passed automatically by the framework to record session artifacts.

    Returns:
        Dictionary containing destination name, public GCS HTTPS image URL, mime_type, and status message.
    """
    prompt = f"A beautiful high-resolution travel postcard photo of {destination}"
    if description:
        prompt += f", featuring {description}"

    client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
    )

    if not response.candidates or not response.candidates[0].content.parts:
        return {"error": "Failed to generate image: empty response from model."}

    part = response.candidates[0].content.parts[0]
    if not part.inline_data or not part.inline_data.data:
        return {"error": "No image data returned in model response."}

    img_bytes = part.inline_data.data
    mime_type = part.inline_data.mime_type or "image/jpeg"

    # Unique filename for artifact and GCS
    clean_name = destination.lower().strip().replace(" ", "-")
    short_id = uuid.uuid4().hex[:6]
    ext = "png" if "png" in mime_type else "jpg"
    filename = f"postcard-{clean_name}-{short_id}.{ext}"

    # 1. Save artifact to ToolContext for Playground
    if tool_context is not None:
        artifact_part = types.Part.from_bytes(data=img_bytes, mime_type=mime_type)
        res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
        if inspect.isawaitable(res):
            await res

    # 2. Upload image bytes directly to public GCS bucket (in-memory; no local file writing)
    blob_name = f"postcards/{filename}"
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(img_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"

    return {
        "status": "success",
        "destination": destination,
        "public_url": public_url,
        "filename": filename,
        "mime_type": mime_type,
        "message": f"Successfully generated postcard for '{destination}' and published to Cloud Storage.",
    }


async def generate_destination_preview_video(
    destination: str,
    scene_description: str = "",
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """Generates a short travel video preview for a destination using Google's Omni model (gemini-omni-flash-preview)
    in the global region, saves it as a session artifact for the Playground, and uploads it to public Cloud Storage.

    Args:
        destination: Name of the destination city or region (e.g. "Tokyo", "Kyoto", "Paris", "Bali").
        scene_description: Optional visual scene or activity prompt (e.g. "sunset over the ocean", "cherry blossoms in spring").
        tool_context: ADK ToolContext passed automatically by the framework to record session artifacts.

    Returns:
        Dictionary containing destination name, public GCS HTTPS video URL, mime_type, and status message.
    """
    prompt = f"Generate a short high-quality travel video preview of {destination}"
    if scene_description:
        prompt += f", featuring {scene_description}"

    client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )

    interaction = client.interactions.create(
        model="gemini-omni-flash-preview",
        input=prompt,
    )

    if not interaction or not getattr(interaction, "output_video", None):
        return {"error": "Failed to generate video: no output_video returned from model interaction."}

    video_bytes = interaction.output_video.data
    mime_type = getattr(interaction.output_video, "mime_type", None) or "video/mp4"

    if not video_bytes:
        return {"error": "Empty video bytes received from model interaction."}

    # Unique filename for artifact and GCS
    clean_name = destination.lower().strip().replace(" ", "-")
    short_id = uuid.uuid4().hex[:6]
    ext = "mp4" if "mp4" in mime_type else "mp4"
    filename = f"video-{clean_name}-{short_id}.{ext}"

    # 1. Save artifact to ToolContext for Playground
    if tool_context is not None:
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
        if inspect.isawaitable(res):
            await res

    # 2. Upload video bytes directly to public GCS bucket (in-memory; no local file writing)
    blob_name = f"videos/{filename}"
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{blob_name}"

    return {
        "status": "success",
        "destination": destination,
        "public_url": public_url,
        "filename": filename,
        "mime_type": mime_type,
        "message": f"Successfully generated video preview for '{destination}' and published to Cloud Storage.",
    }




