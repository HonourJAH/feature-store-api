import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class FeatureSnapshot(SQLModel, table=True):
    """One row = one historical snapshot of an entity's features
    at a specific point in time.

    This table is APPEND-ONLY — every POST /features/{entity_id}
    call inserts a NEW row here, never updates an existing one.
    This is what gives point-in-time correctness for training:
    what a user's features looked like can always be reconstructed
    on any past date.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    entity_id: str = Field(index=True)

    total_purchases: int
    total_spend: float
    avg_order_value: float
    num_logins_7d: int
    num_logins_30d: int
    days_since_last_login: int
    days_since_last_purchase: int
    account_age_days: int

    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
