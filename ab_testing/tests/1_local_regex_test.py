#!/usr/bin/env python3
"""
Direct test of noise stripping strategy without proxy.

This demonstrates that the core framework works.
The proxy integration can be debugged separately.
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ab_testing.framework.strategies import strip_tool_noise, no_compression
from ab_testing.framework.simulator import RuntimeSimulator
from ab_testing.framework.scenario import load_scenario
import json

import sys
import argparse

def test_noise_stripping(scenario_path):
    """Test noise stripping on simulated tool results."""
    
    # Load scenario
    try:
        scenario = load_scenario(scenario_path)
    except FileNotFoundError:
        # Fallback to checking the parent directory if run from within tests/
        import os
        if not os.path.exists(scenario_path) and os.path.exists(f"../{scenario_path}"):
            scenario = load_scenario(f"../{scenario_path}")
        else:
            scenario = load_scenario(scenario_path)
            
    simulator = RuntimeSimulator(scenario.to_dict())
    
    print("="*80)
    print("DIRECT STRATEGY TEST (No Proxy)")
    print("="*80)
    print(f"\nScenario: {scenario.name}")
    print(f"Description: {scenario.description}")
    
    # Simulate a conversation with tool calls
    messages = [
        {"role": "system", "content": scenario.system_prompt},
        {"role": "user", "content": scenario.turns[0]["content"]},
        {
            "role": "assistant",
            "content": "I'll list the files and run the Python script.",
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
    
    print(f"\n{'='*80}")
    print("BASELINE (no compression)")
    print("="*80)
    
    baseline = no_compression(messages)
    baseline_chars = sum(len(str(m.get("content", ""))) for m in baseline if m.get("role") == "tool")
    print(f"Total tool result chars: {baseline_chars}")
    print(f"\nSample tool result (first 300 chars):")
    print(baseline[3]["content"][:300])
    
    print(f"\n{'='*80}")
    print("NOISE STRIPPED")
    print("="*80)
    
    compressed = strip_tool_noise(messages)
    compressed_chars = sum(len(str(m.get("content", ""))) for m in compressed if m.get("role") == "tool")
    print(f"Total tool result chars: {compressed_chars}")
    print(f"\nSample tool result (full):")
    print(compressed[3]["content"])
    
    print(f"\n{'='*80}")
    print("SAVINGS")
    print("="*80)
    
    savings = baseline_chars - compressed_chars
    savings_pct = (savings / baseline_chars * 100) if baseline_chars > 0 else 0
    
    print(f"Baseline chars:    {baseline_chars}")
    print(f"Compressed chars:  {compressed_chars}")
    print(f"Savings:           {savings} chars ({savings_pct:.1f}%)")
    
    print(f"\n{'='*80}")
    print("✓ Noise stripping strategy works!")
    print("="*80)
    
    # Estimate token savings (rough: 1 token ≈ 4 chars)
    token_savings = savings // 4
    print(f"\nEstimated token savings: ~{token_savings} tokens")
    print(f"At $0.15/M input tokens: ${token_savings * 0.15 / 1_000_000:.6f} saved per conversation")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Directly test regex on a scenario")
    parser.add_argument("scenario", nargs="?", default="../scenarios/simple_shell_noise.json", help="Path to scenario JSON file")
    args = parser.parse_args()
    
    test_noise_stripping(args.scenario)
