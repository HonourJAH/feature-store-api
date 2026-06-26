from datetime import date, datetime, timezone


def _parse_date(value: str) -> date:
    """Convert an ISO date string into a date object."""
    return datetime.fromisoformat(value).date()


def compute_features(entity_id: str, raw_data: dict) -> dict:
    """Takes raw event data for an entity and computes the derived
    features defined in the schema.

    In a real system, raw_data would come from a database of orders,
    logins, etc. Here, the caller provides it directly so it can
    demonstrates the computation logic itself.

    Expected raw_data shape:
    {
        "purchases": [{"amount": float, "date": "YYYY-MM-DD"}, ...],
        "logins": ["YYYY-MM-DD", ...],
        "account_created_at": "YYYY-MM-DD",
    }
    """
    today = datetime.now(timezone.utc).date()

    purchases = raw_data.get("purchases", [])
    logins = raw_data.get("logins", [])
    created_at = _parse_date(raw_data["account_created_at"])

    # Purchase-based features
    total_purchases = len(purchases)
    total_spend = sum(p["amount"] for p in purchases)

    # Guard against division by zero — a brand new user has made 0 purchases
    avg_order_value = total_spend / total_purchases if total_purchases > 0 else 0.0

    if purchases:
        purchase_dates = [_parse_date(p["date"]) for p in purchases]
        days_since_last_purchase = (today - max(purchase_dates)).days
    else:
        # No purchase history — use a sentinel value rather than crashing
        days_since_last_purchase = -1

    # Login-based features
    login_dates = [_parse_date(l) for l in logins]

    num_logins_7d = sum(1 for d in login_dates if (today - d).days <= 7)
    num_logins_30d = sum(1 for d in login_dates if (today - d).days <= 30)

    if login_dates:
        days_since_last_login = (today - max(login_dates)).days
    else:
        days_since_last_login = -1

    # Account-based features
    account_age_days = (today - created_at).days

    return {
        "total_purchases": total_purchases,
        "total_spend": round(total_spend, 2),
        "avg_order_value": round(avg_order_value, 2),
        "num_logins_7d": num_logins_7d,
        "num_logins_30d": num_logins_30d,
        "days_since_last_login": days_since_last_login,
        "days_since_last_purchase": days_since_last_purchase,
        "account_age_days": account_age_days,
    }
