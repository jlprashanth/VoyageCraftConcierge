# Copyright 2026 Google LLC
#
# Seed script for VoyageCraft Travel Concierge Firestore Database.

import sys
from google.cloud import firestore

# HARDCODED Project ID as required by Agent Platform standards
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-6c97d9d7ae82"

SEED_DESTINATIONS = [
    {
        "id": "san-francisco",
        "name": "San Francisco",
        "country": "USA",
        "description": "Iconic coastal city known for the Golden Gate Bridge, vibrant food scene, and historic streetcars.",
        "budget_tier": "moderate",
        "tags": ["coastal", "culture", "food", "sightseeing"],
        "recommended_activities": [
            "Golden Gate Bridge bike tour",
            "Alcatraz Island history visit",
            "Ferry Building Food Hall exploration",
        ],
        "rating": 4.8,
    },
    {
        "id": "tokyo",
        "name": "Tokyo",
        "country": "Japan",
        "description": "Dynamic metropolis blending futuristic skyscrapers, ancient temples, world-class dining, and pop culture.",
        "budget_tier": "moderate",
        "tags": ["metropolis", "food", "culture", "shopping", "temples"],
        "recommended_activities": [
            "Shibuya Crossing & Harajuku walk",
            "Senso-ji Temple visit in Asakusa",
            "Tsukiji Outer Market food tour",
        ],
        "rating": 4.9,
    },
    {
        "id": "paris",
        "name": "Paris",
        "country": "France",
        "description": "The City of Light, world-famous for art, gastronomy, fashion, and historical landmarks.",
        "budget_tier": "luxury",
        "tags": ["romance", "art", "museums", "gourmet", "architecture"],
        "recommended_activities": [
            "Louvre Museum guided tour",
            "Eiffel Tower sunset view",
            "Seine River evening cruise",
        ],
        "rating": 4.7,
    },
    {
        "id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "description": "Cultural heart of Japan with thousands of classical Buddhist temples, gardens, imperial palaces, and traditional wooden houses.",
        "budget_tier": "moderate",
        "tags": ["culture", "history", "temples", "nature"],
        "recommended_activities": [
            "Fushimi Inari Shrine hike",
            "Arashiyama Bamboo Grove walk",
            "Gion geisha district tour",
        ],
        "rating": 4.9,
    },
    {
        "id": "barcelona",
        "name": "Barcelona",
        "country": "Spain",
        "description": "Sun-drenched Mediterranean city renowned for Antoni Gaudí architecture, tapas bars, and sandy beaches.",
        "budget_tier": "budget",
        "tags": ["beach", "architecture", "food", "nightlife"],
        "recommended_activities": [
            "Sagrada Família tour",
            "Park Güell stroll",
            "Gothic Quarter tapas crawl",
        ],
        "rating": 4.7,
    },
]


def seed_database():
    print(f"Connecting to Firestore for project: {FIRESTORE_PROJECT_ID}...")
    db = firestore.Client(project=FIRESTORE_PROJECT_ID)
    collection_ref = db.collection("destinations")

    for dest in SEED_DESTINATIONS:
        doc_id = dest["id"]
        doc_ref = collection_ref.document(doc_id)
        doc_ref.set(dest)
        print(f"Seeded destination: {dest['name']} (ID: {doc_id})")

    print(f"✅ Successfully seeded {len(SEED_DESTINATIONS)} destinations into Firestore.")


if __name__ == "__main__":
    seed_database()
