#!/usr/bin/env python3
"""
Test with model selection.
Lets you pick which model to use and measures token impact.
"""

import sys
import httpx
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ab_testing.framework.scenario import load_scenario
from ab_testing.framework.simulator import RuntimeSimulator
from ab_testing.framework.strategies import no_compression, strip_tool_noise

AVAILABLE_MODELS = {
    "1": ("openai/gpt-4o-mini", "$0.15/M", "CHEAP - Best for testing"),
    "2": ("openai/gpt-4o", "$5/M", "MEDIUM - Good quality"),
    "3": ("anthropic/claude-3-5-sonnet-20241022", "$3/M", "MEDIUM - Anthropic"),
    "4": ("google/gemini-flash-1.5", "VERY CHEAP", "BUDGET - Fastest"),
}

def select_model():
    """Interactive model selection."""
    print("\n" + "="*70)
    print("SELECT MODEL FOR TESTING")
    print("="*70)
    print("\nAvailable models:")
    for key, (model, price, desc) in AVAILABLE_MODELS.items():
        print(f"  {key}. {model:<45} {price:<12} ({desc})")
    print("\nEnter 1-4 (default: 1 - gpt-4o-mini):")
    
    choice = input("> ").strip() or "1"
    
    if choice not in AVAILABLE_MODELS:
        print("Invalid choice, using default (gpt-4o-mini)")
        choice = "1"
    
    model, price, desc = AVAILABLE_MODELS[choice]
    print(f"\n✓ Selected: {model}")
    print(f"  Price: {price}")
    print(f"  Description: {desc}\n")
    
    return model

def select_scenario():
    """Interactive scenario selection."""
    scenarios = {
        "1": "scenarios/simple_shell_noise.json",
        "2": "scenarios/file_read_noise.json",
        "3": "scenarios/multi_turn_debug.json",
    }
    
    print("\n" + "="*70)
    print("SELECT SCENARIO")
    print("="*70)
    print("\nAvailable scenarios:")
    print("  1. simple_shell_noise.json - Minimal (2 shell commands)")
    print("  2. file_read_noise.json - Mixed (read + shell)")
    print("  3. multi_turn_debug.json - Complex (debugging scenario)")
    print("\nEnter 1-3 (default: 1):")
    
    choice = input("> ").strip() or "1"
    
    if choice not in scenarios:
        print("Invalid choice, using default")
        choice = "1"
    
    path = scenarios[choice]
    scenario = load_scenario(path)
    print(f"\n✓ Selected: {scenario.name}")
    print(f"  Description: {scenario.description}\n")
    
    return scenario

def test_with_model(scenario, model):
    """Run test with specified model."""
    
    print("="*70)
    print(f"RUNNING TEST: {scenario.name}")
    print(f"Model: {model}")
    print("="*70)
    
    simulator = RuntimeSimulator(scenario.to_dict())
    
    # Build conversation with tool results
    messages = [
        {"role": "system", "content": scenario.system_prompt},
        {"role": "user", "content": scenario.turns[0]["content"]},
    ]
    
    # Simulate some tool calls based on scenario
    # (In real scenario, LLM would decide this)
    print("\nSimulating tool calls...")
    
    if "shell_responses" in scenario.to_dict():
        commands = list(scenario.shell_responses.keys())[:2]  # Use first 2 commands
        for i, cmd in enumerate(commands, 1):
            messages.append({
                "role": "assistant",
                "content": f"Running command: {cmd}",
                "tool_calls": [{
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": "Shell",
                        "arguments": f'{{"command": "{cmd}"}}'
                    }
                }]
            })
            
            result = simulator.handle_shell(cmd)
            messages.append({
                "role": "tool",
                "tool_call_id": f"call_{i}",
                "content": result
            })
            
            print(f"  {i}. {cmd[:50]:<50} → {len(result):>4} chars")
    
    # Measure baseline
    print("\n" + "-"*70)
    print("BASELINE (No compression)")
    print("-"*70)
    
    baseline_request = {
        "model": model,
        "messages": messages,
        "max_tokens": 100,
        "stream": False
    }
    
    baseline_chars = sum(len(str(m.get("content", ""))) for m in messages)
    print(f"Total message chars: {baseline_chars}")
    
    try:
        print("Sending to proxy...")
        response = httpx.post(
            "http://localhost:8000/v1/chat/completions",
            json=baseline_request,
            timeout=30
        )
        result = response.json()
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            baseline_usage = None
        else:
            baseline_usage = result.get("usage", {})
            print(f"✓ Input tokens: {baseline_usage.get('prompt_tokens', 0)}")
            print(f"  Output tokens: {baseline_usage.get('completion_tokens', 0)}")
            print(f"  Total: {baseline_usage.get('total_tokens', 0)}")
    except Exception as e:
        print(f"❌ Error: {e}")
        baseline_usage = None
    
    # Measure compressed
    print("\n" + "-"*70)
    print("NOISE STRIPPED (With compression)")
    print("-"*70)
    
    compressed_messages = strip_tool_noise(messages)
    compressed_chars = sum(len(str(m.get("content", ""))) for m in compressed_messages)
    
    char_savings = baseline_chars - compressed_chars
    char_savings_pct = (char_savings / baseline_chars * 100) if baseline_chars > 0 else 0
    
    print(f"Total message chars: {compressed_chars}")
    print(f"Character savings: {char_savings} chars ({char_savings_pct:.1f}%)")
    
    try:
        compressed_request = {
            "model": model,
            "messages": compressed_messages,
            "max_tokens": 100,
            "stream": False
        }
        
        print("Sending to proxy...")
        response = httpx.post(
            "http://localhost:8000/v1/chat/completions",
            json=compressed_request,
            timeout=30
        )
        result = response.json()
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            compressed_usage = None
        else:
            compressed_usage = result.get("usage", {})
            print(f"✓ Input tokens: {compressed_usage.get('prompt_tokens', 0)}")
            print(f"  Output tokens: {compressed_usage.get('completion_tokens', 0)}")
            print(f"  Total: {compressed_usage.get('total_tokens', 0)}")
    except Exception as e:
        print(f"❌ Error: {e}")
        compressed_usage = None
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    if baseline_usage and compressed_usage:
        token_savings = baseline_usage.get("total_tokens", 0) - compressed_usage.get("total_tokens", 0)
        baseline_total = baseline_usage.get("total_tokens", 0)
        token_savings_pct = (token_savings / baseline_total * 100) if baseline_total > 0 else 0
        
        print(f"\nTokens:")
        print(f"  Baseline: {baseline_usage.get('total_tokens', 0)}")
        print(f"  Compressed: {compressed_usage.get('total_tokens', 0)}")
        print(f"  Saved: {token_savings} tokens ({token_savings_pct:.1f}%)")
        
        # Estimate cost savings
        cost_per_million = 0.15  # gpt-4o-mini default
        cost_saved = token_savings * cost_per_million / 1_000_000
        print(f"\nEstimated cost savings: ${cost_saved:.6f}")
    else:
        print(f"\nCharacter savings: {char_savings} chars ({char_savings_pct:.1f}%)")
        print(f"Estimated token savings: ~{char_savings // 4} tokens")
    
    print("\n" + "="*70 + "\n")

def main():
    """Interactive testing."""
    
    try:
        # Select scenario and model
        scenario = select_scenario()
        model = select_model()
        
        # Run test
        test_with_model(scenario, model)
        
        print("\n✓ Test complete!")
        print(f"\nNext steps:")
        print(f"  - Run again with different model to compare costs")
        print(f"  - Create custom scenario in scenarios/ directory")
        print(f"  - Check QUICKSTART.md for more options")
        
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
