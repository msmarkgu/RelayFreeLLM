import os
import sys
import json

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def test_config_loading():
    print("Testing Configuration Loading...")
    
    # Import settings AFTER adding to sys.path
    from src.config import Settings
    
    # 1. Test loading from settings.json
    print("\n[Test 1] Loading from settings.json")
    # We'll use the current settings.json values from the file we just wrote
    # TTL should be 24 based on settings.json
    s = Settings()
    print(f"SESSION_TTL_HOURS: {s.SESSION_TTL_HOURS} (Expected: 24)")
    assert s.SESSION_TTL_HOURS == 24
    
    # 2. Test ENV override
    print("\n[Test 2] Testing Environment Variable Override")
    os.environ["SESSION_TTL_HOURS"] = "48"
    s2 = Settings()
    print(f"SESSION_TTL_HOURS: {s2.SESSION_TTL_HOURS} (Expected: 48)")
    assert s2.SESSION_TTL_HOURS == 48
    
    # 3. Test Global Provider Lock
    print("\n[Test 3] Testing Global Provider Lock")
    # Default in class was False, set to False in settings.json
    print(f"GLOBAL_PROVIDER_LOCK: {s.GLOBAL_PROVIDER_LOCK} (Expected: False)")
    assert s.GLOBAL_PROVIDER_LOCK == False
    
    print("\nAll Configuration Loading Tests Passed!")

if __name__ == "__main__":
    test_config_loading()
