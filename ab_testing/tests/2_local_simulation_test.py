#!/usr/bin/env python3
"""
Full end-to-end A/B test demonstration.

Shows:
1. Strategy application
2. Simulator tool execution
3. Conversation flow
4. Token comparison
"""

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ab_testing.framework.strategies import no_compression, strip_tool_noise
from ab_testing.framework.simulator import RuntimeSimulator
from ab_testing.framework.scenario import load_scenario
import json

import sys
import argparse
import os

def simulate_llm_conversation(scenario_path, strategy_name):
    """
    Simulate a full LLM conversation with:
    - Real strategy application
    - Simulator tool execution
    - Realistic message flow
    """
    
    try:
        scenario = load_scenario(scenario_path)
    except FileNotFoundError:
        if not os.path.exists(scenario_path) and os.path.exists(f"../{scenario_path}"):
            scenario = load_scenario(f"../{scenario_path}")
        else:
            scenario = load_scenario(scenario_path)
    simulator = RuntimeSimulator(scenario.to_dict())
    
    print(f"\n{'='*70}")
    print(f"Scenario: {scenario.name}")
    print(f"Strategy: {strategy_name}")
    print(f"{'='*70}\n")
    
    # Start with initial message
    messages = [
        {"role": "system", "content": scenario.system_prompt},
        {"role": "user", "content": scenario.turns[0]["content"]}
    ]
    
    turn = 1
    total_tool_output_chars_before = 0
    total_tool_output_chars_after = 0
    
    # Simulate LLM deciding to call tools and getting results
    # (In reality, this would come from the LLM API response)
    
    # Turn 1: LLM reads a file
    print(f"Turn {turn}: User asks: '{scenario.turns[0]['content']}'")
    turn += 1
    
    # Simulate LLM's response with a tool call
    messages.append({
        "role": "assistant",
        "content": "I'll list the files in the directory.",
        "tool_calls": [{
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "Shell",
                "arguments": '{"command": "ls"}'
            }
        }]
    })
    
    # Simulator executes the tool
    shell_result = simulator.handle_shell("ls")
    messages.append({
        "role": "tool",
        "tool_call_id": "call_1",
        "content": shell_result
    })
    
    total_tool_output_chars_before += len(shell_result)
    print(f"  Tool call: Shell('ls')")
    print(f"  Result length: {len(shell_result)} chars\n")
    
    # Turn 2: LLM wants to run a command
    print(f"Turn {turn}: LLM decides to run the Python script")
    turn += 1
    
    messages.append({
        "role": "assistant",
        "content": "Now I'll run the Python script.",
        "tool_calls": [{
            "id": "call_2",
            "type": "function",
            "function": {
                "name": "Shell",
                "arguments": '{"command": "python hello.py"}'
            }
        }]
    })
    
    shell_result2 = simulator.handle_shell("python hello.py")
    messages.append({
        "role": "tool",
        "tool_call_id": "call_2",
        "content": shell_result2
    })
    
    total_tool_output_chars_before += len(shell_result2)
    print(f"  Tool call: Shell('python hello.py')")
    print(f"  Result length: {len(shell_result2)} chars\n")
    
    # Now apply strategy and measure savings
    print(f"Applying strategy: {strategy_name}")
    if strategy_name == "none":
        compressed_messages = no_compression(messages)
    else:
        compressed_messages = strip_tool_noise(messages)
    
    total_tool_output_chars_after = sum(
        len(str(m.get("content", ""))) 
        for m in compressed_messages 
        if m.get("role") == "tool"
    )
    
    savings = total_tool_output_chars_before - total_tool_output_chars_after
    savings_pct = (savings / total_tool_output_chars_before * 100) if total_tool_output_chars_before > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}")
    print(f"Tool output chars (before): {total_tool_output_chars_before}")
    print(f"Tool output chars (after):  {total_tool_output_chars_after}")
    print(f"Savings: {savings} chars ({savings_pct:.1f}%)")
    print(f"Est. tokens saved: ~{savings // 4}")
    print(f"{'='*70}\n")
    
    return {
        "strategy": strategy_name,
        "tool_chars_before": total_tool_output_chars_before,
        "tool_chars_after": total_tool_output_chars_after,
        "savings": savings,
        "savings_pct": savings_pct,
    }

def main():
    """Run A/B comparison."""
    parser = argparse.ArgumentParser(description="Run local simulation test")
    parser.add_argument("scenario", nargs="?", default="../scenarios/simple_shell_noise.json", help="Path to scenario JSON file")
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("FULL END-TO-END A/B TEST")
    print("="*70)
    print("\nThis demonstrates:")
    print("1. Load scenario (JSON)")
    print("2. Simulate LLM making tool calls")
    print("3. Simulator executes tools (returns predefined output)")
    print("4. Apply compression strategy")
    print("5. Compare results")
    
    results = []
    
    # Run baseline (no compression)
    result = simulate_llm_conversation(args.scenario, "none")
    results.append(result)
    
    # Run with noise stripping
    result = simulate_llm_conversation(args.scenario, "noise_strip")
    results.append(result)
    
    # Print comparison
    print("\n" + "="*70)
    print("COMPARISON")
    print("="*70)
    print(f"{'Strategy':<15} {'Chars Before':<15} {'Chars After':<15} {'Savings':<15}")
    print("-"*70)
    
    for result in results:
        print(f"{result['strategy']:<15} {result['tool_chars_before']:<15} {result['tool_chars_after']:<15} {result['savings_pct']:>6.1f}%")
    
    baseline = results[0]
    comparison = results[1]
    
    if baseline["tool_chars_before"] > 0:
        net_savings = baseline["tool_chars_before"] - comparison["tool_chars_after"]
        net_savings_pct = (net_savings / baseline["tool_chars_before"] * 100)
        print("-"*70)
        print(f"\n✓ Net savings with noise_strip: {net_savings} chars ({net_savings_pct:.1f}%)")
        print(f"  Estimated tokens: ~{net_savings // 4}")
        print(f"  Cost per char: $0.000045 (at $0.15/M tokens)")
        print(f"  Savings per conversation: ${net_savings * 0.000045 / 4:.6f}")
    
    print("\n" + "="*70 + "\n")

if __name__ == "__main__":
    main()
