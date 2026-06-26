from datetime import datetime
from pydantic import BaseModel


class FeatureCreate(BaseModel):
    """What the caller sends to POST /features/{entity_id}."""

    total_purchases: int
    total_spend: float
    avg_order_value: float
    num_logins_7d: int
    num_logins_30d: int
    days_since_last_login: int
    days_since_last_purchase: int
    account_age_days: int


class FeatureResponse(BaseModel):
    """Returned by both POST /features/{entity_id} and
    GET /features/{entity_id} — the current/latest snapshot.
    """

    entity_id: str
    total_purchases: int
    total_spend: float
    avg_order_value: float
    num_logins_7d: int
    num_logins_30d: int
    days_since_last_login: int
    days_since_last_purchase: int
    account_age_days: int
    computed_at: datetime
    model_config = {"from_attributes": True}


class FeatureHistoryResponse(BaseModel):
    """Returned by GET /features/{entity_id}/history.
    A list of every historical snapshot for this entity,
    ordered by time.
    """

    entity_id: str
    result: int
    history: list[FeatureResponse]


class Purchase(BaseModel):
    amount: float
    date: str


class RawFeatureData(BaseModel):
    """What the caller sends to POST /features/{entity_id}/compute.
    Simulates raw event data pulled from a real orders/logins database.
    """

    purchases: list[Purchase] = []
    logins: list[str] = []
    account_created_at: str
