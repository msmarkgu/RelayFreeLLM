import pytest
from fastapi.testclient import TestClient

from src.server import app


def test_filter_by_type_and_scale():
    """Test filtering models by type and scale."""
    with TestClient(app) as client:
        filter_resp = client.get(
            "/v1/models", params={"type": "text", "scale": "large"}
        )
        assert filter_resp.status_code == 200, "Catalog filter should return 200"
        filtered = filter_resp.json()

        assert "data" in filtered
        assert isinstance(filtered["data"], list)

        for model in filtered["data"]:
            if model.get("type") and model.get("scale"):
                assert model["type"] == "text"
                assert model["scale"] == "large"


def test_filter_coding_models():
    """Test filtering for coding models."""
    with TestClient(app) as client:
        filter_resp = client.get("/v1/models", params={"type": "coding"})
        assert filter_resp.status_code == 200
        filtered = filter_resp.json()

        assert "data" in filtered
        coding_models = [m for m in filtered["data"] if m.get("type") == "coding"]
        assert len(coding_models) > 0, "Should have at least one coding model"


def test_filter_medium_scale():
    """Test filtering for medium scale models."""
    with TestClient(app) as client:
        filter_resp = client.get("/v1/models", params={"scale": "medium"})
        assert filter_resp.status_code == 200
        filtered = filter_resp.json()

        assert "data" in filtered
        medium_models = [m for m in filtered["data"] if m.get("scale") == "medium"]
        assert len(medium_models) > 0, "Should have at least one medium model"


def test_model_metadata_in_response():
    """Test that model metadata (type, scale) is included in response."""
    with TestClient(app) as client:
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()

        models_with_metadata = [
            m for m in data["data"] if m.get("type") and m.get("scale")
        ]
        assert len(models_with_metadata) > 0, (
            "Should have models with type and scale metadata"
        )
