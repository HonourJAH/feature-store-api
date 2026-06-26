import os
import json
import redis
from datetime import datetime, timezone

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

r = redis.from_url(REDIS_URL, decode_responses=True)


def save_online_features(entity_id: str, features: dict) -> dict:
    """Store the LATEST feature snapshot for an entity in Redis.

    This overwrites whatever was there before — the online store
    only ever holds the current/most recent values, never history.
    """
    record = {
        **features,
        "entity_id": entity_id,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    key = f"features:{entity_id}"
    r.set(key, json.dumps(record))

    return record


def get_online_features(entity_id: str) -> dict | None:
    """Fast lookup of an entity's latest feature values.

    Returns None if no features have ever been computed for this entity.
    """
    key = f"features:{entity_id}"
    data = r.get(key)

    if data is None:
        return None

    return json.loads(data)
