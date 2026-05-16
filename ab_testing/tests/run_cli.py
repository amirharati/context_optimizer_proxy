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
import shlex
from pathlib import Path

from ab_testing.framework.scenario import load_scenario, list_scenarios
from ab_testing.framework.runner import TestRunner
from ab_testing.framework.strategies import STRATEGIES


class TeeOutput:
    """Capture stdout to both terminal and file."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, 'w', encoding='utf-8')
    
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    
    def flush(self):
        self.terminal.flush()
        self.log.flush()
    
    def close(self):
        self.log.close()


def _fmt_metric(value):
    return "n/a" if value is None else str(value)


def _display_path(path: str) -> str:
    """Prefer workspace-relative display paths when possible."""
    try:
        return Path(path).resolve().relative_to(Path.cwd().resolve()).as_posix()
    except Exception:
        return path


def _build_effective_command(args) -> str:
    """Build explicit command with resolved/default values."""
    tokens = ["python", "ab_testing/tests/run_cli.py"]
    if args.all:
        tokens.append("--all")
    elif args.scenarios:
        tokens.append("--scenarios")
        tokens.extend(_display_path(p) for p in args.scenarios)
    elif args.scenario:
        tokens.append(_display_path(args.scenario))

    tokens.extend(["--proxy-url", args.proxy_url])
    tokens.extend(["--model", args.model])
    tokens.append("--strategies")
    tokens.extend(args.strategies)
    tokens.extend(["--max-turns", str(args.max_turns)])
    tokens.extend(["--temperature", str(args.temperature)])
    tokens.extend(["--runs", str(args.runs)])
    if args.disable_cache:
        tokens.append("--disable-cache")
    if args.no_full_logging:
        tokens.append("--no-full-logging")
    if args.custom_log_dir:
        tokens.extend(["--custom-log-dir", args.custom_log_dir])
    if args.output:
        tokens.extend(["--output", args.output])
    return " ".join(shlex.quote(t) for t in tokens)


def _load_model_catalog():
    """
    Load model options from JSON config for interactive selection.
    """
    config_path = Path(__file__).resolve().parent.parent / "config" / "models.json"
    fallback_models = [
        {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini", "notes": "Default fallback"},
        {"id": "openai/gpt-4o", "label": "GPT-4o", "notes": "Fallback"},
        {"id": "anthropic/claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "notes": "Fallback"},
        {"id": "google/gemini-flash-1.5", "label": "Gemini Flash 1.5", "notes": "Fallback"},
    ]
    fallback_default = "openai/gpt-4o-mini"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        models = data.get("models", [])
        parsed_models = []
        for item in models:
            model_id = item.get("id")
            if not model_id:
                continue
            parsed_models.append({
                "id": model_id,
                "label": item.get("label", model_id),
                "notes": item.get("notes", ""),
            })
        if not parsed_models:
            return fallback_default, fallback_models
        default_model = data.get("default_model") or parsed_models[0]["id"]
        return default_model, parsed_models
    except Exception:
        return fallback_default, fallback_models


def print_comparison_report(results: dict):
    """Print a formatted comparison report."""
    print("\n" + "="*80)
    print("A/B TEST RESULTS")
    print("="*80)
    
    print(f"\nScenario: {results['scenario']}")
    print(f"Model: {results['model']}")
    print(f"Cache mode: {results.get('cache_mode', 'cache_on')}")
    print(f"Strategies tested: {', '.join(results['strategies_tested'])}")
    
    # Results table
    print("\n" + "-"*80)
    print(
        f"{'Strategy':<20} {'Turns':<6} {'Tools':<6} "
        f"{'Raw In':<10} {'Cache Read':<11} {'Cache Create':<13} "
        f"{'Billed In':<10} {'Out':<8} {'Total':<8}"
    )
    print("-"*80)
    
    for strategy, result in results['results'].items():
        if 'error' in result:
            print(f"{strategy:<20} ERROR: {result['error']}")
            continue
        
        m = result['metrics']
        print(
            f"{strategy:<20} {m['turns']:<6} {m['tool_calls']:<6} "
            f"{_fmt_metric(m.get('raw_input_tokens')):<10} "
            f"{_fmt_metric(m.get('cache_read_tokens')):<11} "
            f"{_fmt_metric(m.get('cache_creation_tokens')):<13} "
            f"{_fmt_metric(m.get('billed_input_tokens')):<10} "
            f"{_fmt_metric(m.get('total_output_tokens')):<8} "
            f"{_fmt_metric(m.get('total_tokens')):<8}"
        )
        prov = m.get("metric_provenance", {})
        if prov:
            print(
                " " * 22
                + "sources: "
                + f"raw={prov.get('raw_input_tokens', 'unavailable')}, "
                + f"cache_read={prov.get('cache_read_tokens', 'unavailable')}, "
                + f"cache_create={prov.get('cache_creation_tokens', 'unavailable')}, "
                + f"billed={prov.get('billed_input_tokens', 'unavailable')}"
            )
    
    # Comparison
    if results['comparison']:
        print("\n" + "-"*80)
        print("SAVINGS vs BASELINE (none)")
        print("-"*80)
        
        for strategy, comp in results['comparison'].items():
            savings = comp.get('token_savings')
            savings_pct = comp.get('token_savings_pct')
            print(f"\n{strategy}:")
            print(f"  Legacy total-token savings: {_fmt_metric(savings)} ({_fmt_metric(savings_pct)}%)")
            print(
                "  Compression effect (raw input): "
                f"{_fmt_metric(comp.get('raw_input_savings'))} "
                f"({_fmt_metric(comp.get('raw_input_savings_pct'))}%)"
            )
            print(
                "  Cost effect (billed input):    "
                f"{_fmt_metric(comp.get('billed_input_savings'))} "
                f"({_fmt_metric(comp.get('billed_input_savings_pct'))}%)"
            )
    
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
                strategies_data[strategy] = {
                    "savings": [],
                    "pct": [],
                    "raw_savings": [],
                    "raw_pct": [],
                    "billed_savings": [],
                    "billed_pct": [],
                }
            if comp.get("token_savings") is not None:
                strategies_data[strategy]["savings"].append(comp.get("token_savings", 0))
                # Prefer unrounded percentage to avoid accumulated rounding error
                pct = comp.get("token_savings_pct_raw", comp.get("token_savings_pct", 0))
                strategies_data[strategy]["pct"].append(pct)
            if comp.get("raw_input_savings") is not None:
                strategies_data[strategy]["raw_savings"].append(comp.get("raw_input_savings", 0))
                raw_pct = comp.get("raw_input_savings_pct_raw", comp.get("raw_input_savings_pct", 0))
                strategies_data[strategy]["raw_pct"].append(raw_pct)
            if comp.get("billed_input_savings") is not None:
                strategies_data[strategy]["billed_savings"].append(comp.get("billed_input_savings", 0))
                billed_pct = comp.get("billed_input_savings_pct_raw", comp.get("billed_input_savings_pct", 0))
                strategies_data[strategy]["billed_pct"].append(billed_pct)
            
    if not strategies_data:
        print("No comparison data available to aggregate.")
        print("="*80 + "\n")
        return
        
    for strategy, data in strategies_data.items():
        savings = data["savings"]
        pcts = data["pct"]
        if not savings:
            continue
        
        mean_savings = statistics.mean(savings)
        median_savings = statistics.median(savings)
        mean_pct = statistics.mean(pcts)
        median_pct = statistics.median(pcts)
        
        print(f"\n{strategy}:")
        print(f"  Runs:           {len(savings)}")
        print(f"  Legacy total savings: mean {mean_savings:.2f} ({mean_pct:.2f}%), median {median_savings:.2f} ({median_pct:.2f}%)")
        print(f"  Legacy total min/max: {min(savings)} / {max(savings)} tokens")
        if data["raw_savings"]:
            print(
                f"  Compression effect (raw): mean {statistics.mean(data['raw_savings']):.2f} "
                f"({statistics.mean(data['raw_pct']):.2f}%)"
            )
        if data["billed_savings"]:
            print(
                f"  Cost effect (billed):    mean {statistics.mean(data['billed_savings']):.2f} "
                f"({statistics.mean(data['billed_pct']):.2f}%)"
            )
        
    print("\n" + "="*80 + "\n")
    
    return strategies_data


def main():
    parser = argparse.ArgumentParser(description="Run A/B tests for compression strategies")
    parser.add_argument("scenario", nargs="?", help="Path to scenario JSON file")
    parser.add_argument("--scenarios", nargs="+", help="List of scenario JSON paths to run")
    parser.add_argument("--all", action="store_true", help="Run all scenarios in scenarios/ directory")
    parser.add_argument("--proxy-url", default="http://localhost:8000", help="Proxy server URL")
    parser.add_argument("--model", default="openai/gpt-4o-mini", help="Model to use")
    parser.add_argument("--strategies", nargs="+", default=["none", "noise_strip"], help="Strategies to compare (baseline 'none' is always included)")
    parser.add_argument("--list-strategies", action="store_true", help="List available strategies and exit")
    parser.add_argument("--list-models", action="store_true", help="List available models and exit")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run interactively to choose missing options")
    parser.add_argument("--max-turns", type=int, default=10, help="Maximum conversation turns")
    parser.add_argument("--temperature", type=float, default=0.0, help="LLM temperature (default 0.0 for determinism)")
    parser.add_argument("--runs", type=int, default=1, help="Number of times to run each scenario")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--disable-cache", action="store_true", help="Force cache misses with per-turn UUID injection")
    parser.add_argument("--no-full-logging", action="store_true", help="Disable full logging of requests (full logging is enabled by default)")
    parser.add_argument("--custom-log-dir", help="Custom sub-directory for session logs")
    
    import datetime
    
    args = parser.parse_args()
    
    # If no arguments provided at all, default to interactive mode
    if len(sys.argv) == 1:
        args.interactive = True
    
    if args.list_strategies:
        print("Available strategies:")
        for name in STRATEGIES:
            print(f"  - {name}")
        return 0

    configured_default_model, configured_models = _load_model_catalog()
    if args.model == parser.get_default("model"):
        args.model = configured_default_model

    if args.list_models:
        print("Available models (from ab_testing/config/models.json):")
        for model_entry in configured_models:
            extra = f" ({model_entry['notes']})" if model_entry.get("notes") else ""
            print(f"  - {model_entry['id']}{extra}")
        return 0
    
    if args.interactive:
        if not args.scenario and not args.scenarios and not args.all:
            scenarios_path = str(Path(__file__).resolve().parent.parent / "scenarios")
            scenarios = list_scenarios(scenarios_path)
            if not scenarios:
                print("No scenarios found.")
                return 1
            scenario_labels = [Path(sc).stem for sc in scenarios]
            print("\nAvailable Scenarios:")
            for idx, label in enumerate(scenario_labels, 1):
                print(f"  {idx}. {label}")
            while True:
                choice = input("\nSelect scenarios by number (comma separated) or 'all': ").strip()
                if choice.lower() == 'all':
                    args.all = True
                    break
                elif choice:
                    chosen_scenarios = []
                    for c in choice.split(','):
                        c = c.strip()
                        if c.isdigit() and 1 <= int(c) <= len(scenarios):
                            chosen_scenarios.append(scenarios[int(c)-1])
                    if chosen_scenarios:
                        args.scenarios = chosen_scenarios
                        break
        
        if "--strategies" not in sys.argv:
            print("\nAvailable Strategies:")
            strats = list(STRATEGIES.keys())
            for idx, st in enumerate(strats, 1):
                print(f"  {idx}. {st}")
            choice = input(f"\nSelect strategies by number (comma separated) [default: 1,2]: ").strip()
            if choice:
                chosen = []
                for c in choice.split(","):
                    c = c.strip()
                    if c.isdigit() and 1 <= int(c) <= len(strats):
                        chosen.append(strats[int(c)-1])
                if chosen:
                    args.strategies = chosen

        if "--model" not in sys.argv:
            model_options = [m["id"] for m in configured_models]
            print("\nSelect model:")
            for idx, model_name in enumerate(model_options, 1):
                model_entry = configured_models[idx - 1]
                label = model_entry.get("label", model_name)
                notes = model_entry.get("notes", "")
                default_tag = " (default)" if model_name == args.model else ""
                note_suffix = f" - {notes}" if notes else ""
                print(f"  {idx}. {label}: {model_name}{default_tag}{note_suffix}")
            print(f"  {len(model_options) + 1}. Custom model id")
            default_idx = model_options.index(args.model) + 1 if args.model in model_options else 1
            choice = input(f"\nModel choice [default: {default_idx}]: ").strip()
            if not choice:
                choice = str(default_idx)
            if choice.isdigit():
                selected_idx = int(choice)
                if 1 <= selected_idx <= len(model_options):
                    args.model = model_options[selected_idx - 1]
                elif selected_idx == len(model_options) + 1:
                    custom_model = input("Enter custom model id (provider/model): ").strip()
                    if custom_model:
                        args.model = custom_model
        
        if "--runs" not in sys.argv:
            choice = input("\nNumber of iterations (runs) [default: 1]: ").strip()
            if choice.isdigit():
                args.runs = int(choice)
        
        if "--disable-cache" not in sys.argv:
            choice = input("\nDisable cache? (y/N) [default: N]: ").strip().lower()
            if choice in {"y", "yes", "true", "1"}:
                args.disable_cache = True

    # Determine which scenarios to run
    if args.all:
        scenarios_path = str(Path(__file__).resolve().parent.parent / "scenarios")
        scenario_files = list_scenarios(scenarios_path)
        if not scenario_files:
            print("No scenario files found in scenarios/")
            return 1
        print(f"Found {len(scenario_files)} scenario(s)")
    elif args.scenarios:
        scenario_files = args.scenarios
        print(f"Running {len(scenario_files)} selected scenario(s)")
    elif args.scenario:
        scenario_files = [args.scenario]
    else:
        parser.print_help()
        return 1

    # Always include baseline strategy for valid A/B comparisons.
    # Preserve user order for non-baseline strategies.
    requested_strategies = list(args.strategies or [])
    normalized_strategies = ["none"]
    for strategy in requested_strategies:
        if strategy != "none" and strategy not in normalized_strategies:
            normalized_strategies.append(strategy)
    args.strategies = normalized_strategies

    # Show resolved execution command up-front (all modes).
    effective_cmd = _build_effective_command(args)
    print("\nResolved command:")
    print(f"  {effective_cmd}\n")
    if args.interactive:
        proceed = input("Proceed with this configuration? [Y/n]: ").strip().lower()
        if proceed in {"n", "no"}:
            print("Cancelled.")
            return 0

    loaded_scenarios = []
    for scenario_file in scenario_files:
        try:
            scenario = load_scenario(scenario_file)
            loaded_scenarios.append((scenario_file, scenario))
        except Exception as e:
            print(f"Error loading scenario {scenario_file}: {e}")
            return 1

    scenario_disable_modes = [
        scenario.resolve_disable_cache(cli_disable_cache=args.disable_cache)
        for _, scenario in loaded_scenarios
    ]
    if scenario_disable_modes and all(scenario_disable_modes):
        cache_mode_label = "cache_off"
    elif scenario_disable_modes and not any(scenario_disable_modes):
        cache_mode_label = "cache_on"
    else:
        cache_mode_label = "cache_mixed"

    # Set up unified run directory with date hierarchy
    now = datetime.datetime.now()
    run_timestamp = now.strftime("%Y%m%d_%H%M%S")
    run_date = now.strftime("%Y-%m-%d")
    run_name = f"run_{run_timestamp}_{cache_mode_label}"
    
    # Put the runs directory alongside logs with hierarchy:
    # runs/<YYYY-MM-DD>/<cache_mode>/<run_name>/
    runs_base_dir = Path("runs") / run_date / cache_mode_label
    run_dir = runs_base_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Capture all CLI output to a file
    output_log_path = run_dir / "cli_output.txt"
    tee = TeeOutput(output_log_path)
    original_stdout = sys.stdout
    sys.stdout = tee
    
    print(f"\nCreated run directory: {run_dir.absolute()}")
    print(f"Logging output to: {output_log_path.absolute()}")
    
    # Update args to use the new run directory
    if not args.custom_log_dir:
        # The proxy interprets custom log dir relative to LOG_DIR (default logs/),
        # so prefix ../ to target project-root runs/.
        args.custom_log_dir = f"../{run_dir.as_posix()}/sessions"
    
    if not args.output:
        args.output = str(run_dir / "report.json")
        
    # We also need to pass the absolute path of the run directory to the TestRunner 
    # so it can save the virtual_fs artifacts there
    abs_run_dir = str(run_dir.absolute())
    
    # Initialize runner
    runner = TestRunner(
        proxy_url=args.proxy_url,
        model=args.model,
        max_turns=args.max_turns,
        temperature=args.temperature,
        force_full_logging=not args.no_full_logging,
        custom_log_dir=args.custom_log_dir,
        artifacts_dir=abs_run_dir,
        disable_cache=args.disable_cache,
        cache_mode_label=cache_mode_label,
    )
    
    all_results = []
    
    try:
        # Run each scenario
        for scenario_file, scenario in loaded_scenarios:
            print(f"\nLoading scenario: {scenario_file}")
            
            # Copy scenario file to run directory for archiving
            import shutil
            scenario_archive_dir = run_dir / "scenarios"
            scenario_archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(scenario_file, scenario_archive_dir / Path(scenario_file).name)
            
            scenario_disable_cache = scenario.resolve_disable_cache(cli_disable_cache=args.disable_cache)
            scenario_cache_mode_label = "cache_off" if scenario_disable_cache else "cache_on"
            runner.disable_cache = scenario_disable_cache
            runner.cache_mode_label = scenario_cache_mode_label
            print(
                f"Scenario cache mode resolved to: {scenario_cache_mode_label} "
                f"(cli_disable_cache={args.disable_cache})"
            )
            
            for run_idx in range(args.runs):
                if args.runs > 1:
                    print(f"\n>>> EXECUTING RUN {run_idx + 1}/{args.runs} <<<")
                
                # Update run index so each run gets a unique session key
                runner.run_index = run_idx + 1
                
                # Run comparison
                results = runner.compare_strategies(scenario, args.strategies)
                results["run_index"] = run_idx + 1
                results["cache_mode"] = scenario_cache_mode_label
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
                    "run_date": run_date,
                    "command": " ".join(sys.argv),
                    "args": vars(args),
                    "cache_mode_for_run_dir": cache_mode_label,
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
                        "max_savings": max(data["savings"]),
                        "mean_raw_input_savings": statistics.mean(data["raw_savings"]) if data["raw_savings"] else None,
                        "mean_raw_input_pct": statistics.mean(data["raw_pct"]) if data["raw_pct"] else None,
                        "mean_billed_input_savings": statistics.mean(data["billed_savings"]) if data["billed_savings"] else None,
                        "mean_billed_input_pct": statistics.mean(data["billed_pct"]) if data["billed_pct"] else None,
                    }
            
            with open(output_path, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"Results saved to {args.output}")
        
    finally:
        runner.close()
        sys.stdout = original_stdout
        tee.close()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
