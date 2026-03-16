import sys
import os
import random
from collections import Counter
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.model_selector import ModelSelector
from src.api_provider import ApiProvider
from src.api_limits_tracker import ApiLimitsTracker

def create_mock_provider(name, model_names):
    models = [
        ApiLimitsTracker(name, mname, {
            "requests_per_second": 100,
            "requests_per_minute": 1000,
            "requests_per_hour": 10000,
            "requests_per_day": 100000,
            "tokens_per_minute": 1000000,
            "tokens_per_hour": -1,
            "tokens_per_day": -1
        }) for mname in model_names
    ]
    return ApiProvider(name, models)

def setup_selector(provider_strat, model_strat):
    # Mock the loading of limits to use our own test providers
    test_providers = {
        "P1": create_mock_provider("P1", ["M1", "M2"]),
        "P2": create_mock_provider("P2", ["M3", "M4"])
    }
    
    with patch("src.model_selector.ModelSelector.load_api_limits_from_json", return_value=test_providers):
        return ModelSelector(
            provider_sequence=["P1", "P2"],
            provider_strategy=provider_strat,
            model_strategy=model_strat
        )

def run_test_combination(provider_strat, model_strat, iterations=40):
    print(f"\n>>> Strategy Combination: Provider={provider_strat}, Model={model_strat}")
    selector = setup_selector(provider_strat, model_strat)
    providers = selector.provider_sequence
    
    provider_counts = Counter()
    model_counts = Counter()
    selections = []
    
    for i in range(iterations):
        prov, model = selector.select("test input")
        provider_counts[prov] += 1
        model_counts[f"{prov}:{model}"] += 1
        selections.append((prov, model))
    
    # Analysis
    print(f"Provider distribution: {dict(provider_counts)}")
    
    if provider_strat == "roundrobin":
        # Check if providers are cycled
        # For our mock (P1, P2), it should be alternating.
        # Note: ModelSelector starts at a random index for RR if last_provider_index == -1.
        for i in range(len(selections) - 1):
            curr_p = selections[i][0]
            next_p = selections[i+1][0]
            curr_idx = providers.index(curr_p)
            expected_next = providers[(curr_idx + 1) % len(providers)]
            assert next_p == expected_next, f"RR Provider failed: expected {expected_next} after {curr_p}, got {next_p}"
        print("✓ Round-robin provider order verified")

    if model_strat == "roundrobin":
        # Check model balance per provider
        for p_name in providers:
            p_models = [m for m in model_counts if m.startswith(p_name)]
            counts = [model_counts[m] for m in p_models]
            if counts:
                diff = max(counts) - min(counts)
                assert diff <= 1, f"RR Model failed for {p_name}: counts {counts} too far apart"
        print("✓ Round-robin model distribution verified")

if __name__ == "__main__":
    try:
        combinations = [
            ("random", "random"),
            ("random", "roundrobin"),
            ("roundrobin", "random"),
            ("roundrobin", "roundrobin"),
        ]
        
        for p_strat, m_strat in combinations:
            run_test_combination(p_strat, m_strat)
            
        print("\nAll strategy combinations passed verification!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
