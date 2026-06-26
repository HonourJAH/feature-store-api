from typing import Annotated

from fastapi import FastAPI, HTTPException, status, Depends
from sqlmodel import Session

from app.database import get_db
from app.schema import (
    FeatureCreate,
    FeatureResponse,
    FeatureHistoryResponse,
    RawFeatureData,
)
from app.services.features import compute_features
from app import store
from app import crud

app = FastAPI()

db_session = Annotated[Session, Depends(get_db)]


# Routes


@app.post("/features/{entity_id}", status_code=status.HTTP_201_CREATED)
async def create_features(
    entity_id: str, payload: FeatureCreate, db: db_session
) -> FeatureResponse:
    """Store computed features for an entity.

    Writes to BOTH stores:
    - Offline store (SQLite) — append-only historical snapshot
    - Online store (Redis)   — overwrites the 'latest' value
    """
    # 1. Append a permanent historical record
    crud.save_snapshot(entity_id, payload, db)

    # 2. Overwrite the fast-lookup current value
    record = store.save_online_features(entity_id, payload.model_dump())

    return FeatureResponse(**record)


@app.post("/features/{entity_id}/compute", status_code=status.HTTP_201_CREATED)
async def compute_and_store_features(
    entity_id: str, raw_data: RawFeatureData, db: db_session
) -> FeatureResponse:
    """Accepts raw event data, computes derived features server-side,
    then stores the result in both the offline and online stores —
    same dual-write pattern as the direct POST /features/{entity_id} route.
    """
    computed = compute_features(entity_id, raw_data.model_dump())

    # Reuse FeatureCreate to validate the computed output matches the schema
    payload = FeatureCreate(**computed)

    crud.save_snapshot(entity_id, payload, db)
    record = store.save_online_features(entity_id, payload.model_dump())

    return FeatureResponse(**record)


@app.get("/features/{entity_id}")
async def get_features(entity_id: str) -> FeatureResponse:
    """Fast lookup of an entity's CURRENT feature values from Redis.

    This is the online store path — millisecond lookup, no database
    query involved at all.
    """
    record = store.get_online_features(entity_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No features found for this entity",
        )

    return FeatureResponse(**record)


@app.get("/features/{entity_id}/history")
async def get_feature_history(entity_id: str, db: db_session) -> FeatureHistoryResponse:
    """Return the full historical record of feature snapshots
    for this entity, from the offline store (SQLite).

    This is what you'd use to build a training dataset — every
    point-in-time snapshot ever computed for this entity.
    """
    history = crud.get_history(entity_id, db)

    return FeatureHistoryResponse(
        entity_id=entity_id,
        result=len(history),
        history=history,
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
