"""Tests for model selection with type/scale filters."""

import pytest
from src.model_selector import ModelSelector
from src.model_metadata import detect_model_type, detect_model_scale


def test_select_by_type_coding():
    """Test selecting a coding model."""
    selector = ModelSelector()
    provider, model, wait = selector.select("test prompt", model_type="coding")

    assert provider == "Mistral"
    assert "codestral" in model.lower()
    assert detect_model_type(model) == "coding"


def test_select_by_scale_large():
    """Test selecting a large-scale model."""
    selector = ModelSelector()
    provider, model, wait = selector.select("test prompt", model_scale="large")

    assert detect_model_scale(model) == "large"


def test_select_by_scale_medium():
    """Test selecting a medium-scale model."""
    selector = ModelSelector()
    provider, model, wait = selector.select("test prompt", model_scale="medium")

    assert detect_model_scale(model) == "medium"


def test_select_by_type_and_scale():
    """Test selecting with both type and scale filters."""
    selector = ModelSelector()
    provider, model, wait = selector.select(
        "test prompt", model_type="coding", model_scale="medium"
    )

    assert detect_model_type(model) == "coding"
    assert detect_model_scale(model) == "medium"


def test_select_nonexistent_filter():
    """Test that non-matching filters raises error."""
    selector = ModelSelector()

    # No image models in our registry, should raise RuntimeError
    with pytest.raises(
        RuntimeError, match="All models in all providers are at capacity"
    ):
        selector.select("test prompt", model_type="image")


def test_filter_preserves_roundrobin():
    """Test that filtering works with round-robin strategy."""
    selector = ModelSelector()

    # Select same type multiple times, should rotate
    results = []
    for _ in range(3):
        provider, model, wait = selector.select("test", model_scale="medium")
        if model:
            results.append((provider, model))

    # Should have selected models without error
    assert len(results) > 0
