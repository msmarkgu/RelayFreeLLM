"""Tests for the provider-level 'enabled' flag in the registry."""

import json

import pytest

from src.model_selector import ModelSelector


def _make_selector(tmp_path, providers):
    path = tmp_path / "limits.json"
    path.write_text(json.dumps({"providers": providers}))
    selector = ModelSelector()
    selector.registry_file = str(path)
    selector.providers, selector.disabled_providers, selector.known_providers = (
        selector.load_api_limits_from_json(str(path))
    )
    selector.provider_sequence = list(selector.providers.keys())
    return selector


def _provider(name, enabled=None, models=None):
    prov = {"name": name, "url": "", "models": models or []}
    if enabled is not None:
        prov["enabled"] = enabled
    return prov


def _model(name):
    return {
        "name": name,
        "type": "text",
        "scale": "medium",
        "limits": {
            "requests_per_second": 1,
            "requests_per_minute": 10,
            "requests_per_hour": 60,
            "requests_per_day": 100,
            "tokens_per_minute": 1000,
            "tokens_per_hour": -1,
            "tokens_per_day": -1,
        },
        "Max_Context_Length": 4096,
        "modality": "text",
    }


def test_enabled_false_excluded_from_providers(tmp_path):
    selector = _make_selector(
        tmp_path,
        [
            _provider("Alpha", enabled=True, models=[_model("a-1")]),
            _provider("Beta", enabled=False, models=[_model("b-1")]),
        ],
    )
    assert "Alpha" in selector.providers
    assert "Beta" not in selector.providers


def test_disabled_still_in_known_providers(tmp_path):
    selector = _make_selector(
        tmp_path,
        [
            _provider("Alpha", enabled=True, models=[_model("a-1")]),
            _provider("Beta", enabled=False, models=[_model("b-1")]),
        ],
    )
    assert "Beta" in selector.known_providers
    assert "Beta" in selector.disabled_providers


def test_default_enabled_when_flag_absent(tmp_path):
    selector = _make_selector(
        tmp_path,
        [_provider("Alpha", models=[_model("a-1")])],
    )
    assert "Alpha" in selector.providers
    assert "Alpha" in selector.known_providers


def test_all_enabled_case(tmp_path):
    selector = _make_selector(
        tmp_path,
        [
            _provider("Alpha", enabled=True, models=[_model("a-1")]),
            _provider("Beta", enabled=True, models=[_model("b-1")]),
        ],
    )
    assert set(selector.providers.keys()) == {"Alpha", "Beta"}
    assert set(selector.known_providers) == {"Alpha", "Beta"}
    assert selector.disabled_providers == {}


def test_save_registry_preserves_enabled_off(tmp_path):
    selector = _make_selector(
        tmp_path,
        [
            _provider("Alpha", enabled=True, models=[_model("a-1")]),
            _provider("Beta", enabled=False, models=[_model("b-1")]),
        ],
    )
    selector.save_registry_to_json()
    data = json.loads(open(selector.registry_file).read())
    by_name = {p["name"]: p for p in data["providers"]}
    assert by_name["Alpha"]["enabled"] is True
    assert by_name["Beta"]["enabled"] is False


def test_save_registry_preserves_enabled_default(tmp_path):
    selector = _make_selector(
        tmp_path,
        [_provider("Alpha", models=[_model("a-1")])],
    )
    selector.save_registry_to_json()
    data = json.loads(open(selector.registry_file).read())
    assert data["providers"][0]["enabled"] is True


def test_disabled_provider_not_selected(tmp_path):
    selector = _make_selector(
        tmp_path,
        [
            _provider("Alpha", enabled=True, models=[_model("a-1")]),
            _provider("Beta", enabled=False, models=[_model("b-1")]),
        ],
    )
    for _ in range(10):
        provider, model, wait = selector.select("prompt", preferred_provider="Beta")
        assert provider == "Alpha"
        assert provider != "Beta"
