#!/usr/bin/env python3
"""
Tight Mode / Replay Runner.

Loads a historical session (.jsonl) and evaluates compression turn-by-turn.
This provides the pure mathematical compression ratio without LLM drift,
since we reset the context to the historical ground truth on every turn.
"""

import os
import sys
import json
import argparse
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ab_testing.framework.strategies import STRATEGIES

def estimate_tokens(text: str) -> int:
    return len(str(text)) // 4

def replay_session(log_path: str, strategies: list[str]):
    print("="*80)
    print(f"TIGHT REPLAY MODE")
    print(f"Log: {log_path}")
    print("="*80)
    
    turns = []
    with open(log_path, 'r') as f:
        for line in f:
            if not line.strip(): continue
            try:
                turns.append(json.loads(line))
            except json.JSONDecodeError:
                pass
                
    if not turns:
        print("Error: No valid turns found in log.")
        return
        
    print(f"Found {len(turns)} turns in session.")
    print("-" * 80)
    print(f"{'Turn':<6} {'Messages':<10} " + "".join(f"{s[:12]:<15}" for s in strategies) + "Savings (vs none)")
    print("-" * 80)
    
    total_baseline_tokens = 0
    total_compressed_tokens = {s: 0 for s in strategies if s != "none"}
    
    for turn in turns:
        messages = turn.get("messages", [])
        if not messages:
            continue
            
        turn_num = turn.get("turn", "?")
        msg_count = len(messages)
        
        results = {}
        for strategy in strategies:
            strat_func = STRATEGIES.get(strategy)
            if not strat_func:
                results[strategy] = 0
                continue
                
            compressed_msgs = strat_func(messages)
            
            # Count characters
            content_str = "".join(
                (m.get("content", "") if isinstance(m.get("content"), str)
                 else " ".join(p.get("text", "") for p in m.get("content", []) if isinstance(p, dict)))
                for m in compressed_msgs
            )
            tokens = estimate_tokens(content_str)
            results[strategy] = tokens
            
        # Print row
        baseline = results.get("none", 0)
        total_baseline_tokens += baseline
        
        row = f"{turn_num:<6} {msg_count:<10} "
        for s in strategies:
            row += f"{results[s]:<15}"
            if s != "none":
                total_compressed_tokens[s] += results[s]
                
        # Savings
        if "none" in strategies and len(strategies) > 1:
            main_strat = [s for s in strategies if s != "none"][0]
            savings = baseline - results[main_strat]
            pct = (savings / baseline * 100) if baseline > 0 else 0
            row += f"{savings} tok ({pct:.1f}%)"
            
        print(row)
        
    print("-" * 80)
    if "none" in strategies:
        print("\nOVERALL TOTALS:")
        print(f"  Baseline (none): {total_baseline_tokens} tokens")
        for s in strategies:
            if s == "none": continue
            total_comp = total_compressed_tokens[s]
            savings = total_baseline_tokens - total_comp
            pct = (savings / total_baseline_tokens * 100) if total_baseline_tokens > 0 else 0
            print(f"  {s}: {total_comp} tokens -> Saved {savings} tokens ({pct:.1f}%)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay a session log and measure compression turn-by-turn")
    parser.add_argument("log", help="Path to .jsonl session log")
    parser.add_argument("--strategies", nargs="+", default=["none", "noise_strip"], help="Strategies to compare")
    args = parser.parse_args()
    
    replay_session(args.log, args.strategies)
