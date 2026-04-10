import os
import requests
import json
import time

def print_interaction(step_name, payload, response_json):
    print("\n" + "="*60)
    print(f"--- {step_name} ---")
    print("="*60)
    
    # Print exactly what we send
    print("\n[REQUEST PAYLOAD AS-IS]")
    print(json.dumps(payload, indent=2))
    
    # Extract model routing info if available
    used_model = response_json.get("model", "Unknown")
    
    # Print exact response structure
    print(f"\n[RAW RESPONSE AS-IS] (Routed to Model: {used_model})")
    print(json.dumps(response_json, indent=2))
    
    # Focus on the generated text
    if "choices" in response_json and len(response_json["choices"]) > 0:
        content = response_json["choices"][0]["message"].get("content", "")
        print(f"\n[EXTRACTED CONTENT]")
        print(content)
        return content
    return ""


def run_demonstration():
    print("==================================================")
    print("RELAYFREELLM CONTEXT DEMONSTRATION")
    print("==================================================")
    url = "http://localhost:8000/v1/chat/completions"
    headers = {
        "Content-Type": "application/json", 
        "Authorization": "Bearer relay-free"
    }

    # 1. Establish a strict logical rule
    msg1 = {
        "role": "user", 
        "content": "For the rest of our conversation, we are playing a word replacement game. Whenever I say 'Alpha', you must reply exactly with 'Omega'. Whenever I say 'Up', you must reply exactly with 'Down'. Acknowledge if you understand the rules."
    }
    
    payload1 = {
        "model": "meta-model",
        "messages": [msg1]
    }

    try:
        r1 = requests.post(url, json=payload1, headers=headers)
        r1.raise_for_status()
        resp1_json = r1.json()
        resp1_content = print_interaction("STEP 1: ESTABLISH RULE", payload1, resp1_json)
        msg2 = {"role": "assistant", "content": resp1_content}
    except Exception as e:
        print(f"\n[ERROR] Could not connect to API. Is RelayFreeLLM running on localhost:8000?\nDetails: {e}")
        return

    time.sleep(1)

    # 2. Trigger the rule WITHOUT context
    msg3 = {"role": "user", "content": "Alpha. Up. Up. Alpha."}
    
    payload_no_context = {
        "model": "meta-model",
        "messages": [msg3]
    }
    
    r2 = requests.post(url, json=payload_no_context, headers=headers)
    print_interaction("TEST 1: CONTEXT DISABLED", payload_no_context, r2.json())

    time.sleep(1)

    # 3. Trigger the rule WITH context
    payload_with_context = {
        "model": "meta-model",
        "messages": [msg1, msg2, msg3]
    }
    
    r3 = requests.post(url, json=payload_with_context, headers=headers)
    print_interaction("TEST 2: CONTEXT ENABLED", payload_with_context, r3.json())

if __name__ == "__main__":
    run_demonstration()
