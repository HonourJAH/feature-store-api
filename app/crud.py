from sqlmodel import Session, select
from app.model import FeatureSnapshot
from app.schema import FeatureCreate


def save_snapshot(
    entity_id: str, features: FeatureCreate, db: Session
) -> FeatureSnapshot:
    """Insert a NEW historical snapshot for this entity.

    This is always an INSERT, never an UPDATE — every call
    creates a new row, preserving the full history. This is
    what gives the offline store its point-in-time correctness.
    """
    snapshot = FeatureSnapshot(
        entity_id=entity_id,
        **features.model_dump(),
    )

    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)

    return snapshot


def get_history(entity_id: str, db: Session) -> list[FeatureSnapshot]:
    """Return every historical snapshot for this entity,
    ordered from oldest to newest.
    """
    statement = (
        select(FeatureSnapshot)
        .where(FeatureSnapshot.entity_id == entity_id)
        .order_by(FeatureSnapshot.computed_at)
    )

    return db.exec(statement).all()
