#!/usr/bin/env python3
"""
CLI script to run A/B tests for compression strategies.

Usage:
    python run_ab_test.py <scenario_file>
    python run_ab_test.py scenarios/simple_shell_noise.json
    python run_ab_test.py --all  # Run all scenarios
"""

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
import json
import argparse
import statistics
from pathlib import Path

from ab_testing.framework.scenario import load_scenario, list_scenarios
from ab_testing.framework.runner import TestRunner


def print_comparison_report(results: dict):
    """Print a formatted comparison report."""
    print("\n" + "="*80)
    print("A/B TEST RESULTS")
    print("="*80)
    
    print(f"\nScenario: {results['scenario']}")
    print(f"Model: {results['model']}")
    print(f"Strategies tested: {', '.join(results['strategies_tested'])}")
    
    # Results table
    print("\n" + "-"*80)
    print(f"{'Strategy':<20} {'Turns':<8} {'Tool Calls':<12} {'Input Tokens':<15} {'Output Tokens':<15} {'Total Tokens':<15}")
    print("-"*80)
    
    for strategy, result in results['results'].items():
        if 'error' in result:
            print(f"{strategy:<20} ERROR: {result['error']}")
            continue
        
        m = result['metrics']
        print(f"{strategy:<20} {m['turns']:<8} {m['tool_calls']:<12} {m['total_input_tokens']:<15} {m['total_output_tokens']:<15} {m['total_tokens']:<15}")
    
    # Comparison
    if results['comparison']:
        print("\n" + "-"*80)
        print("SAVINGS vs BASELINE (none)")
        print("-"*80)
        
        for strategy, comp in results['comparison'].items():
            savings = comp['token_savings']
            savings_pct = comp['token_savings_pct']
            print(f"\n{strategy}:")
            print(f"  Baseline tokens:    {comp['baseline_tokens']}")
            print(f"  Compressed tokens:  {comp['compressed_tokens']}")
            print(f"  Savings:            {savings} tokens ({savings_pct}%)")
    
    print("\n" + "="*80 + "\n")


def print_aggregate_report(all_results: list):
    """Print aggregate statistics (mean, median) across multiple runs."""
    if not all_results:
        return
        
    print("\n" + "="*80)
    print(f"AGGREGATE RESULTS ({len(all_results)} runs)")
    print("="*80)
    
    # Group results by strategy
    # structure: { "noise_strip": { "savings": [], "pct": [] } }
    strategies_data = {}
    
    for run in all_results:
        comparison = run.get('comparison', {})
        for strategy, comp in comparison.items():
            if strategy not in strategies_data:
                strategies_data[strategy] = {"savings": [], "pct": []}
            strategies_data[strategy]["savings"].append(comp.get("token_savings", 0))
            # Prefer unrounded percentage to avoid accumulated rounding error
            pct = comp.get("token_savings_pct_raw", comp.get("token_savings_pct", 0))
            strategies_data[strategy]["pct"].append(pct)
            
    if not strategies_data:
        print("No comparison data available to aggregate.")
        print("="*80 + "\n")
        return
        
    for strategy, data in strategies_data.items():
        savings = data["savings"]
        pcts = data["pct"]
        
        mean_savings = statistics.mean(savings)
        median_savings = statistics.median(savings)
        mean_pct = statistics.mean(pcts)
        median_pct = statistics.median(pcts)
        
        print(f"\n{strategy}:")
        print(f"  Runs:           {len(savings)}")
        print(f"  Mean Savings:   {mean_savings:.2f} tokens ({mean_pct:.2f}%)")
        print(f"  Median Savings: {median_savings:.2f} tokens ({median_pct:.2f}%)")
        print(f"  Min/Max:        {min(savings)} / {max(savings)} tokens")
        
    print("\n" + "="*80 + "\n")
    
    return strategies_data


def main():
    parser = argparse.ArgumentParser(description="Run A/B tests for compression strategies")
    parser.add_argument("scenario", nargs="?", help="Path to scenario JSON file")
    parser.add_argument("--all", action="store_true", help="Run all scenarios in scenarios/ directory")
    parser.add_argument("--proxy-url", default="http://localhost:8000", help="Proxy server URL")
    parser.add_argument("--model", default="openai/gpt-4o-mini", help="Model to use")
    parser.add_argument("--strategies", nargs="+", default=["none", "noise_strip"], help="Strategies to compare")
    parser.add_argument("--max-turns", type=int, default=10, help="Maximum conversation turns")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature (default 0.0 for determinism)")
    parser.add_argument("--runs", type=int, default=1, help="Number of times to run each scenario")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--no-full-logging", action="store_true", help="Disable full logging of requests (full logging is enabled by default)")
    parser.add_argument("--custom-log-dir", help="Custom sub-directory for session logs")
    
    import datetime
    
    args = parser.parse_args()
    
    # Set up unified run directory
    run_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = f"run_{run_timestamp}"
    
    # Put the runs directory alongside the logs directory in the project root
    # Since run_cli.py is executed with cwd=context_optimizer, we can just use "runs"
    runs_base_dir = Path("runs")
    run_dir = runs_base_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nCreated run directory: {run_dir.absolute()}")
    
    # Update args to use the new run directory
    if not args.custom_log_dir:
        # Tell the proxy to save its .jsonl sessions in this specific run folder
        # The proxy interprets this relative to its own LOG_DIR (which defaults to 'logs')
        # So we pass a path that escapes 'logs' and points to our run directory
        args.custom_log_dir = f"../runs/{run_name}/sessions"
    
    if not args.output:
        args.output = str(run_dir / "report.json")
        
    # We also need to pass the absolute path of the run directory to the TestRunner 
    # so it can save the virtual_fs artifacts there
    abs_run_dir = str(run_dir.absolute())
    
    # Determine which scenarios to run
    if args.all:
        scenario_files = list_scenarios("scenarios")
        if not scenario_files:
            print("No scenario files found in scenarios/")
            return 1
        print(f"Found {len(scenario_files)} scenario(s)")
    elif args.scenario:
        scenario_files = [args.scenario]
    else:
        parser.print_help()
        return 1
    
    # Initialize runner
    runner = TestRunner(
        proxy_url=args.proxy_url,
        model=args.model,
        max_turns=args.max_turns,
        temperature=args.temperature,
        force_full_logging=not args.no_full_logging,
        custom_log_dir=args.custom_log_dir,
        artifacts_dir=abs_run_dir,
    )
    
    all_results = []
    
    try:
        # Run each scenario
        for scenario_file in scenario_files:
            print(f"\nLoading scenario: {scenario_file}")
            
            # Copy scenario file to run directory for archiving
            import shutil
            scenario_archive_dir = run_dir / "scenarios"
            scenario_archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(scenario_file, scenario_archive_dir / Path(scenario_file).name)
            
            try:
                scenario = load_scenario(scenario_file)
            except Exception as e:
                print(f"Error loading scenario: {e}")
                continue
            
            for run_idx in range(args.runs):
                if args.runs > 1:
                    print(f"\n>>> EXECUTING RUN {run_idx + 1}/{args.runs} <<<")
                
                # Update run index so each run gets a unique session key
                runner.run_index = run_idx + 1
                
                # Run comparison
                results = runner.compare_strategies(scenario, args.strategies)
                results["run_index"] = run_idx + 1
                all_results.append(results)
                
                # Print report
                print_comparison_report(results)
        
        # Print aggregate report if we ran multiple times
        aggregate_data = None
        if args.runs > 1:
            aggregate_data = print_aggregate_report(all_results)
        
        # Save to file if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            report_data = {
                "metadata": {
                    "timestamp": run_timestamp,
                    "command": " ".join(sys.argv),
                    "args": vars(args)
                },
                "runs": all_results
            }
            
            if aggregate_data:
                # Add the computed aggregates to the JSON report
                report_data["aggregate_summary"] = {}
                for strategy, data in aggregate_data.items():
                    report_data["aggregate_summary"][strategy] = {
                        "runs": len(data["savings"]),
                        "mean_savings": statistics.mean(data["savings"]),
                        "median_savings": statistics.median(data["savings"]),
                        "mean_pct": statistics.mean(data["pct"]),
                        "median_pct": statistics.median(data["pct"]),
                        "min_savings": min(data["savings"]),
                        "max_savings": max(data["savings"])
                    }
            
            with open(output_path, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"Results saved to {args.output}")
        
    finally:
        runner.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
