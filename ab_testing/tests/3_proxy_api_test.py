#!/usr/bin/env python3
"""
Walk through scenario with manual proxy requests.
Shows baseline vs noise-stripped tokens.
"""

import httpx
import json
import argparse
import os
import sys

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ab_testing.framework.scenario import load_scenario
from ab_testing.framework.simulator import RuntimeSimulator
from ab_testing.framework.strategies import no_compression, strip_tool_noise

def test_scenario_through_proxy(scenario_path):
    """
    Manual walkthrough:
    1. Load scenario
    2. Send BASELINE request (no compression)
    3. Send COMPRESSED request (with noise stripping)
    4. Compare token counts from API
    """
    
    # Load scenario
    try:
        scenario = load_scenario(scenario_path)
    except FileNotFoundError:
        if not os.path.exists(scenario_path) and os.path.exists(f"../{scenario_path}"):
            scenario = load_scenario(f"../{scenario_path}")
        else:
            scenario = load_scenario(scenario_path)
    simulator = RuntimeSimulator(scenario.to_dict())
    
    print("\n" + "="*80)
    print("SCENARIO WALKTHROUGH WITH PROXY")
    print("="*80)
    print(f"\nScenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    print(f"Tools available: {', '.join(scenario.available_tools)}")
    print(f"Virtual files: {', '.join(scenario.virtual_fs.keys())}")
    
    # ========== STEP 1: Build baseline messages (with tool results) ==========
    print("\n" + "="*80)
    print("STEP 1: BUILD CONVERSATION WITH TOOL RESULTS")
    print("="*80)
    
    baseline_messages = [
        {"role": "system", "content": scenario.system_prompt},
        {"role": "user", "content": scenario.turns[0]["content"]},
        {
            "role": "assistant",
            "content": "I'll check the files and run the script.",
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "Shell", "arguments": '{"command": "ls"}'}},
                {"id": "call_2", "type": "function", "function": {"name": "Shell", "arguments": '{"command": "python hello.py"}'}}
            ]
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": simulator.handle_shell("ls")
        },
        {
            "role": "tool",
            "tool_call_id": "call_2",
            "content": simulator.handle_shell("python hello.py")
        }
    ]
    
    # Show what we're sending
    print(f"\nMessages structure:")
    print(f"  [1] System prompt: {len(baseline_messages[0]['content'])} chars")
    print(f"  [2] User message: {len(baseline_messages[1]['content'])} chars")
    print(f"  [3] Assistant response with tool calls")
    print(f"  [4] Tool result (Shell ls): {len(baseline_messages[3]['content'])} chars")
    print(f"  [5] Tool result (Shell python): {len(baseline_messages[4]['content'])} chars")
    
    # ========== STEP 2: Send BASELINE to proxy ==========
    print("\n" + "="*80)
    print("STEP 2: SEND BASELINE REQUEST (NO COMPRESSION)")
    print("="*80)
    
    baseline_request = {
        "model": "openai/gpt-4o-mini",
        "messages": baseline_messages,
        "max_tokens": 100,
        "stream": False
    }
    
    # Count characters
    baseline_content = "".join(str(m.get("content", "")) for m in baseline_messages)
    baseline_chars = len(baseline_content)
    print(f"\nTotal characters in baseline: {baseline_chars}")
    
    print("\nSending to proxy: http://localhost:8000/v1/chat/completions")
    print("  Model: openai/gpt-4o-mini")
    print(f"  Messages: {len(baseline_messages)}")
    print("  Strategy: NONE (baseline)")
    
    try:
        response_baseline = httpx.post(
            "http://localhost:8000/v1/chat/completions",
            json=baseline_request,
            timeout=30
        )
        result_baseline = response_baseline.json()
        
        if "error" in result_baseline:
            print(f"\n❌ API Error: {result_baseline['error']}")
            print("\nThis is a known issue with the proxy's error handling.")
            print("Let's measure tokens manually instead...")
        else:
            usage_baseline = result_baseline.get("usage", {})
            print(f"\n✓ Response received!")
            print(f"  Input tokens (baseline): {usage_baseline.get('prompt_tokens', 0)}")
            print(f"  Output tokens: {usage_baseline.get('completion_tokens', 0)}")
            print(f"  Total tokens: {usage_baseline.get('total_tokens', 0)}")
            print(f"  Response: {result_baseline.get('choices', [{}])[0].get('message', {}).get('content', '')[:60]}...")
    except Exception as e:
        print(f"❌ Error: {e}")
        usage_baseline = None
    
    # ========== STEP 3: Apply noise stripping ==========
    print("\n" + "="*80)
    print("STEP 3: APPLY NOISE STRIPPING")
    print("="*80)
    
    compressed_messages = strip_tool_noise(baseline_messages)
    
    # Show what changed
    print(f"\nBefore compression:")
    for i, msg in enumerate(baseline_messages):
        if msg.get("role") == "tool":
            print(f"  Message {i} (tool result): {len(str(msg.get('content', '')))} chars")
    
    print(f"\nAfter noise stripping:")
    for i, msg in enumerate(compressed_messages):
        if msg.get("role") == "tool":
            print(f"  Message {i} (tool result): {len(str(msg.get('content', '')))} chars")
    
    # Count characters after compression
    compressed_content = "".join(str(m.get("content", "")) for m in compressed_messages)
    compressed_chars = len(compressed_content)
    char_savings = baseline_chars - compressed_chars
    char_savings_pct = (char_savings / baseline_chars * 100) if baseline_chars > 0 else 0
    
    print(f"\nCharacter savings:")
    print(f"  Before: {baseline_chars} chars")
    print(f"  After: {compressed_chars} chars")
    print(f"  Saved: {char_savings} chars ({char_savings_pct:.1f}%)")
    print(f"  Est. tokens saved: ~{char_savings // 4}")
    
    # ========== STEP 4: Send COMPRESSED to proxy ==========
    print("\n" + "="*80)
    print("STEP 4: SEND COMPRESSED REQUEST (WITH NOISE STRIPPING)")
    print("="*80)
    
    compressed_request = {
        "model": "openai/gpt-4o-mini",
        "messages": compressed_messages,
        "max_tokens": 100,
        "stream": False
    }
    
    print(f"\nTotal characters in compressed: {compressed_chars}")
    print("\nSending to proxy: http://localhost:8000/v1/chat/completions")
    print("  Model: openai/gpt-4o-mini")
    print(f"  Messages: {len(compressed_messages)}")
    print("  Strategy: NOISE_STRIP")
    
    try:
        response_compressed = httpx.post(
            "http://localhost:8000/v1/chat/completions",
            json=compressed_request,
            timeout=30
        )
        result_compressed = response_compressed.json()
        
        if "error" in result_compressed:
            print(f"\n❌ API Error: {result_compressed['error']}")
            usage_compressed = None
        else:
            usage_compressed = result_compressed.get("usage", {})
            print(f"\n✓ Response received!")
            print(f"  Input tokens (compressed): {usage_compressed.get('prompt_tokens', 0)}")
            print(f"  Output tokens: {usage_compressed.get('completion_tokens', 0)}")
            print(f"  Total tokens: {usage_compressed.get('total_tokens', 0)}")
            print(f"  Response: {result_compressed.get('choices', [{}])[0].get('message', {}).get('content', '')[:60]}...")
    except Exception as e:
        print(f"❌ Error: {e}")
        usage_compressed = None
    
    # ========== STEP 5: Compare ==========
    print("\n" + "="*80)
    print("STEP 5: COMPARISON")
    print("="*80)
    
    if usage_baseline and usage_compressed:
        baseline_total = usage_baseline.get("total_tokens", 0)
        compressed_total = usage_compressed.get("total_tokens", 0)
        token_savings = baseline_total - compressed_total
        token_savings_pct = (token_savings / baseline_total * 100) if baseline_total > 0 else 0
        
        print(f"\n{'Metric':<25} {'Baseline':<15} {'Compressed':<15} {'Savings':<15}")
        print("-" * 70)
        print(f"{'Input tokens':<25} {usage_baseline.get('prompt_tokens', 0):<15} {usage_compressed.get('prompt_tokens', 0):<15} {usage_baseline.get('prompt_tokens', 0) - usage_compressed.get('prompt_tokens', 0):<15}")
        print(f"{'Output tokens':<25} {usage_baseline.get('completion_tokens', 0):<15} {usage_compressed.get('completion_tokens', 0):<15} {usage_baseline.get('completion_tokens', 0) - usage_compressed.get('completion_tokens', 0):<15}")
        print(f"{'Total tokens':<25} {baseline_total:<15} {compressed_total:<15} {token_savings:<15}")
        print("-" * 70)
        print(f"\n✓ Token savings: {token_savings} tokens ({token_savings_pct:.1f}%)")
        print(f"  Cost saved: ${token_savings * 0.15 / 1_000_000:.6f}")
    else:
        print("\n⚠️ Could not get token counts from API (proxy issue)")
        print("But we can still measure character savings:")
        print(f"  Character savings: {char_savings} chars ({char_savings_pct:.1f}%)")
        print(f"  Estimated token savings: ~{char_savings // 4} tokens")
        print(f"  Estimated cost savings: ${char_savings * 0.15 / (1_000_000 * 4):.6f}")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Walk through scenario with manual proxy requests")
    parser.add_argument("scenario", nargs="?", default="../scenarios/simple_shell_noise.json", help="Path to scenario JSON file")
    args = parser.parse_args()
    
    test_scenario_through_proxy(args.scenario)
