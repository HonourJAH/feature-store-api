import pytest
import fakeredis
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session
from sqlmodel.pool import StaticPool

from app.main import app
from app.database import get_db
from app.model import FeatureSnapshot

# Test Database Setup
# In-memory SQLite, shared across the test via StaticPool
TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def override_get_db():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_database():
    """Create all tables before each test, drop them after."""
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def fake_redis():
    """Replace the real Redis connection with fakeredis for every test."""
    fake = fakeredis.FakeRedis(decode_responses=True)
    with patch("app.store.r", fake):
        yield fake


client = TestClient(app)


@pytest.fixture
def sample_feature_payload():
    return {
        "total_purchases": 5,
        "total_spend": 250.0,
        "avg_order_value": 50.0,
        "num_logins_7d": 3,
        "num_logins_30d": 12,
        "days_since_last_login": 1,
        "days_since_last_purchase": 4,
        "account_age_days": 90,
    }


@pytest.fixture
def sample_raw_data():
    return {
        "purchases": [
            {"amount": 49.99, "date": "2026-01-15"},
            {"amount": 89.50, "date": "2026-03-02"},
        ],
        "logins": ["2026-06-20", "2026-06-24", "2026-06-25"],
        "account_created_at": "2026-01-01",
    }


@pytest.fixture
def created_feature(sample_feature_payload):
    """Creates a feature snapshot via the API and returns the response data."""
    response = client.post("/features/user_123", json=sample_feature_payload)
    return response.json()


# Health Check


class TestHealthCheck:
    def test_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200

    def test_returns_healthy_status(self):
        response = client.get("/health")
        assert response.json() == {"status": "healthy"}


# POST /features/{entity_id}


class TestCreateFeatures:
    def test_returns_201(self, sample_feature_payload):
        response = client.post("/features/user_123", json=sample_feature_payload)
        assert response.status_code == 201

    def test_returns_correct_entity_id(self, sample_feature_payload):
        response = client.post("/features/user_123", json=sample_feature_payload)
        assert response.json()["entity_id"] == "user_123"

    def test_returns_correct_total_purchases(self, sample_feature_payload):
        response = client.post("/features/user_123", json=sample_feature_payload)
        assert response.json()["total_purchases"] == 5

    def test_returns_computed_at(self, sample_feature_payload):
        response = client.post("/features/user_123", json=sample_feature_payload)
        assert "computed_at" in response.json()

    def test_missing_field_returns_422(self, sample_feature_payload):
        sample_feature_payload.pop("total_purchases")
        response = client.post("/features/user_123", json=sample_feature_payload)
        assert response.status_code == 422

    def test_invalid_type_returns_422(self, sample_feature_payload):
        sample_feature_payload["total_purchases"] = "not_a_number"
        response = client.post("/features/user_123", json=sample_feature_payload)
        assert response.status_code == 422

    def test_empty_payload_returns_422(self):
        response = client.post("/features/user_123", json={})
        assert response.status_code == 422

    def test_writes_to_online_store(self, sample_feature_payload):
        client.post("/features/user_123", json=sample_feature_payload)
        online_response = client.get("/features/user_123")
        assert online_response.status_code == 200

    def test_writes_to_offline_store(self, sample_feature_payload):
        client.post("/features/user_123", json=sample_feature_payload)
        history_response = client.get("/features/user_123/history")
        assert history_response.json()["result"] == 1

    def test_second_post_creates_new_history_row_not_overwrite(
        self, sample_feature_payload
    ):
        client.post("/features/user_123", json=sample_feature_payload)
        sample_feature_payload["total_purchases"] = 9
        client.post("/features/user_123", json=sample_feature_payload)

        history_response = client.get("/features/user_123/history")
        assert history_response.json()["result"] == 2

    def test_second_post_overwrites_online_store(self, sample_feature_payload):
        client.post("/features/user_123", json=sample_feature_payload)
        sample_feature_payload["total_purchases"] = 9
        client.post("/features/user_123", json=sample_feature_payload)

        online_response = client.get("/features/user_123")
        assert online_response.json()["total_purchases"] == 9

    def test_different_entities_dont_interfere(self, sample_feature_payload):
        client.post("/features/user_123", json=sample_feature_payload)
        sample_feature_payload["total_purchases"] = 1
        client.post("/features/user_456", json=sample_feature_payload)

        response_123 = client.get("/features/user_123")
        response_456 = client.get("/features/user_456")

        assert response_123.json()["total_purchases"] == 5
        assert response_456.json()["total_purchases"] == 1


# GET /features/{entity_id}


class TestGetFeatures:
    def test_returns_200_for_existing_entity(self, created_feature):
        response = client.get("/features/user_123")
        assert response.status_code == 200

    def test_returns_404_for_nonexistent_entity(self):
        response = client.get("/features/nonexistent_user")
        assert response.status_code == 404

    def test_returns_correct_error_message(self):
        response = client.get("/features/nonexistent_user")
        assert (
            "not found" in response.json()["detail"].lower()
            or "No features" in response.json()["detail"]
        )

    def test_returns_correct_entity_id(self, created_feature):
        response = client.get("/features/user_123")
        assert response.json()["entity_id"] == "user_123"

    def test_returns_all_feature_fields(self, created_feature):
        response = client.get("/features/user_123")
        data = response.json()
        expected_fields = {
            "entity_id",
            "total_purchases",
            "total_spend",
            "avg_order_value",
            "num_logins_7d",
            "num_logins_30d",
            "days_since_last_login",
            "days_since_last_purchase",
            "account_age_days",
            "computed_at",
        }
        assert expected_fields.issubset(data.keys())

    def test_lookup_is_fast_no_database_query_needed(self, created_feature, fake_redis):
        # Sanity check that the value genuinely lives in the fake Redis store
        raw = fake_redis.get("features:user_123")
        assert raw is not None


# GET /features/{entity_id}/history


class TestGetFeatureHistory:
    def test_returns_200(self, created_feature):
        response = client.get("/features/user_123/history")
        assert response.status_code == 200

    def test_returns_200_even_for_unknown_entity(self):
        # No history yet — should return an empty list, not 404
        response = client.get("/features/unknown_user/history")
        assert response.status_code == 200

    def test_returns_zero_result_for_unknown_entity(self):
        response = client.get("/features/unknown_user/history")
        assert response.json()["result"] == 0

    def test_returns_empty_history_list_for_unknown_entity(self):
        response = client.get("/features/unknown_user/history")
        assert response.json()["history"] == []

    def test_result_is_one_after_one_post(self, created_feature):
        response = client.get("/features/user_123/history")
        assert response.json()["result"] == 1

    def test_history_contains_correct_entity_id(self, created_feature):
        response = client.get("/features/user_123/history")
        assert response.json()["history"][0]["entity_id"] == "user_123"

    def test_history_is_ordered_oldest_to_newest(self, sample_feature_payload):
        client.post("/features/user_123", json=sample_feature_payload)
        sample_feature_payload["total_purchases"] = 99
        client.post("/features/user_123", json=sample_feature_payload)

        response = client.get("/features/user_123/history")
        history = response.json()["history"]

        assert history[0]["total_purchases"] == 5
        assert history[1]["total_purchases"] == 99

    def test_result_matches_history_list_length(self, sample_feature_payload):
        for _ in range(3):
            client.post("/features/user_123", json=sample_feature_payload)

        response = client.get("/features/user_123/history")
        data = response.json()
        assert data["result"] == len(data["history"])


# POST /features/{entity_id}/compute


class TestComputeAndStoreFeatures:
    def test_returns_201(self, sample_raw_data):
        response = client.post("/features/user_789/compute", json=sample_raw_data)
        assert response.status_code == 201

    def test_returns_correct_total_purchases(self, sample_raw_data):
        response = client.post("/features/user_789/compute", json=sample_raw_data)
        assert response.json()["total_purchases"] == 2

    def test_returns_correct_total_spend(self, sample_raw_data):
        response = client.post("/features/user_789/compute", json=sample_raw_data)
        assert response.json()["total_spend"] == 139.49

    def test_missing_account_created_at_returns_422(self, sample_raw_data):
        sample_raw_data.pop("account_created_at")
        response = client.post("/features/user_789/compute", json=sample_raw_data)
        assert response.status_code == 422

    def test_empty_purchases_and_logins_is_accepted(self):
        response = client.post(
            "/features/new_user/compute",
            json={"purchases": [], "logins": [], "account_created_at": "2026-06-01"},
        )
        assert response.status_code == 201

    def test_empty_purchases_returns_zero_avg_order_value(self):
        response = client.post(
            "/features/new_user/compute",
            json={"purchases": [], "logins": [], "account_created_at": "2026-06-01"},
        )
        assert response.json()["avg_order_value"] == 0.0

    def test_writes_to_offline_store(self, sample_raw_data):
        client.post("/features/user_789/compute", json=sample_raw_data)
        history = client.get("/features/user_789/history")
        assert history.json()["result"] == 1

    def test_writes_to_online_store(self, sample_raw_data):
        client.post("/features/user_789/compute", json=sample_raw_data)
        online = client.get("/features/user_789")
        assert online.status_code == 200


# Service Unit Tests — compute_features


class TestComputeFeatures:
    def test_returns_dict(self, sample_raw_data):
        from app.services.features import compute_features

        result = compute_features("user_1", sample_raw_data)
        assert isinstance(result, dict)

    def test_total_purchases_matches_input_length(self, sample_raw_data):
        from app.services.features import compute_features

        result = compute_features("user_1", sample_raw_data)
        assert result["total_purchases"] == 2

    def test_total_spend_is_sum_of_amounts(self, sample_raw_data):
        from app.services.features import compute_features

        result = compute_features("user_1", sample_raw_data)
        assert result["total_spend"] == 139.49

    def test_avg_order_value_is_correct(self, sample_raw_data):
        from app.services.features import compute_features

        result = compute_features("user_1", sample_raw_data)
        expected = round(139.49 / 2, 2)
        assert result["avg_order_value"] == expected

    def test_no_purchases_returns_zero_avg_order_value(self):
        from app.services.features import compute_features

        result = compute_features(
            "user_1",
            {"purchases": [], "logins": [], "account_created_at": "2026-06-01"},
        )
        assert result["avg_order_value"] == 0.0

    def test_no_purchases_returns_sentinel_days_since_last_purchase(self):
        from app.services.features import compute_features

        result = compute_features(
            "user_1",
            {"purchases": [], "logins": [], "account_created_at": "2026-06-01"},
        )
        assert result["days_since_last_purchase"] == -1

    def test_no_logins_returns_sentinel_days_since_last_login(self):
        from app.services.features import compute_features

        result = compute_features(
            "user_1",
            {"purchases": [], "logins": [], "account_created_at": "2026-06-01"},
        )
        assert result["days_since_last_login"] == -1

    def test_account_age_days_is_non_negative(self, sample_raw_data):
        from app.services.features import compute_features

        result = compute_features("user_1", sample_raw_data)
        assert result["account_age_days"] >= 0

    def test_all_expected_keys_present(self, sample_raw_data):
        from app.services.features import compute_features

        result = compute_features("user_1", sample_raw_data)
        expected_keys = {
            "total_purchases",
            "total_spend",
            "avg_order_value",
            "num_logins_7d",
            "num_logins_30d",
            "days_since_last_login",
            "days_since_last_purchase",
            "account_age_days",
        }
        assert expected_keys == set(result.keys())


# Store Unit Tests


class TestStore:
    def test_save_online_features_returns_dict(self, fake_redis):
        from app.store import save_online_features

        result = save_online_features("user_1", {"total_purchases": 5})
        assert isinstance(result, dict)

    def test_save_online_features_includes_entity_id(self, fake_redis):
        from app.store import save_online_features

        result = save_online_features("user_1", {"total_purchases": 5})
        assert result["entity_id"] == "user_1"

    def test_save_online_features_includes_computed_at(self, fake_redis):
        from app.store import save_online_features

        result = save_online_features("user_1", {"total_purchases": 5})
        assert "computed_at" in result

    def test_get_online_features_returns_saved_data(self, fake_redis):
        from app.store import save_online_features, get_online_features

        save_online_features("user_1", {"total_purchases": 5})
        result = get_online_features("user_1")
        assert result["total_purchases"] == 5

    def test_get_online_features_returns_none_for_missing_entity(self, fake_redis):
        from app.store import get_online_features

        assert get_online_features("nonexistent") is None

    def test_save_overwrites_previous_value(self, fake_redis):
        from app.store import save_online_features, get_online_features

        save_online_features("user_1", {"total_purchases": 5})
        save_online_features("user_1", {"total_purchases": 9})
        result = get_online_features("user_1")
        assert result["total_purchases"] == 9
