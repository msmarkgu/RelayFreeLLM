import requests
import json
import time

def print_interaction(step_name, payload, headers, response_json):
    print("\n" + "="*60)
    print(f"--- {step_name} ---")
    print("="*60)
    
    print(f"\n[REQUEST] X-Session-ID: {headers.get('X-Session-ID')}")
    print(json.dumps(payload, indent=2))
    
    used_model = response_json.get("model", "Unknown")
    meta = response_json.get("meta", {})
    provider = meta.get("provider", "Unknown")
    
    print(f"\n[RAW RESPONSE AS-IS] (Routed to {provider}/{used_model})")
    
    # Just print the meta header to avoid bloating screen
    print(f"Meta Stats: {json.dumps(meta, indent=2)}")
    
    if "choices" in response_json and len(response_json["choices"]) > 0:
        content = response_json["choices"][0]["message"].get("content", "")
        print(f"\n[EXTRACTED CONTENT]")
        print(content)

def run_demonstration():
    print("==================================================")
    print("RELAYFREELLM SESSION AFFINITY DEMONSTRATION")
    print("==================================================")
    url = "http://localhost:8000/v1/chat/completions"
    
    headers_alice = {"Content-Type": "application/json", "Authorization": "Bearer relay-free", "X-Session-ID": "alice-123"}
    headers_bob = {"Content-Type": "application/json", "Authorization": "Bearer relay-free", "X-Session-ID": "bob-456"}

    msg_alice_1 = {"role": "user", "content": "Alice: Hi, I'm Alice!"}
    msg_alice_2 = {"role": "user", "content": "Alice: Give me an update."}
    msg_bob_1 = {"role": "user", "content": "Bob: Hey there, I am Bob."}
    msg_bob_2 = {"role": "user", "content": "Bob: Any news?"}
    
    payload_alice_1 = {"model": "meta-model", "messages": [msg_alice_1]}
    payload_bob_1 = {"model": "meta-model", "messages": [msg_bob_1]}
    payload_alice_2 = {"model": "meta-model", "messages": [msg_alice_2]}
    payload_bob_2 = {"model": "meta-model", "messages": [msg_bob_2]}

    try:
        # Request 1: Alice enters the system (establishes an affinity lock)
        r_a1 = requests.post(url, json=payload_alice_1, headers=headers_alice)
        r_a1.raise_for_status()
        print_interaction("ALICE - REQUEST 1", payload_alice_1, headers_alice, r_a1.json())
        
        time.sleep(1)

        # Request 2: Bob enters the system (round-robin pushes Bob to a NEW provider)
        r_b1 = requests.post(url, json=payload_bob_1, headers=headers_bob)
        print_interaction("BOB - REQUEST 1", payload_bob_1, headers_bob, r_b1.json())
        
        time.sleep(1)

        # Request 3: Alice sends a follow-up (Affinity should pull her BACK to her original provider)
        r_a2 = requests.post(url, json=payload_alice_2, headers=headers_alice)
        print_interaction("ALICE - REQUEST 2", payload_alice_2, headers_alice, r_a2.json())
        
        time.sleep(1)

        # Request 4: Bob sends a follow-up (Affinity should pull him BACK to his different provider)
        r_b2 = requests.post(url, json=payload_bob_2, headers=headers_bob)
        print_interaction("BOB - REQUEST 2", payload_bob_2, headers_bob, r_b2.json())

    except Exception as e:
        print(f"\n[ERROR] Could not connect to API. Is RelayFreeLLM running on localhost:8000?\nDetails: {e}")

if __name__ == "__main__":
    run_demonstration()
