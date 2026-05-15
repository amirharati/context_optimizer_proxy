# Automated A/B Testing for Compression Strategies

Instead of guessing provider caching behavior, use automated A/B testing to discover optimal compression strategies empirically.

---

## The Approach: Treat Providers as Black Boxes

**Philosophy:** We don't know exactly how caching works → Let's measure what actually reduces cost!

### Test Matrix

For each provider, test multiple compression strategies:

| Strategy | Description | Compression Level |
|----------|-------------|-------------------|
| **none** | No compression, baseline | 0% |
| **minimal** | Only strip noise + paths | ~10% |
| **conservative** | Compress every 20 turns, keep stable | ~30% |
| **moderate** | Compress every 10 turns, stable layers | ~50% |
| **aggressive** | Compress every 5 turns, stable layers | ~70% |
| **extreme** | Compress every turn, maximum reduction | ~90% |

---

## Implementation: Parallel Testing

### Architecture

```python
class CompressionABTest:
    """
    Run multiple compression strategies in parallel,
    measure actual costs, find optimal
    """
    
    def __init__(self, provider: str):
        self.provider = provider
        self.strategies = {
            "none": NoCompressionStrategy(),
            "minimal": MinimalCompressionStrategy(),
            "conservative": ConservativeCompressionStrategy(),
            "moderate": ModerateCompressionStrategy(),
            "aggressive": AggressiveCompressionStrategy(),
            "extreme": ExtremeCompressionStrategy(),
        }
        self.results = {name: [] for name in self.strategies}
        
    async def run_test_turn(self, messages, turn):
        """
        Send same request with different compressions
        Measure actual cost for each
        """
        tasks = []
        
        for strategy_name, strategy in self.strategies.items():
            # Apply compression strategy
            compressed = strategy.compress(messages, turn)
            
            # Send to provider
            task = self.send_and_measure(
                messages=compressed,
                strategy=strategy_name,
                turn=turn
            )
            tasks.append(task)
        
        # Run all strategies in parallel
        results = await asyncio.gather(*tasks)
        
        # Record results
        for strategy_name, result in zip(self.strategies.keys(), results):
            self.results[strategy_name].append(result)
        
        return results
    
    async def send_and_measure(self, messages, strategy, turn):
        """
        Send request and measure actual cost
        """
        start_time = time.time()
        
        response = await self.provider_api.chat(
            messages=messages,
            model=self.model
        )
        
        end_time = time.time()
        
        # Extract metrics
        return {
            "strategy": strategy,
            "turn": turn,
            "tokens_sent": count_tokens(messages),
            "tokens_received": response.usage.output_tokens,
            "actual_cost": calculate_cost(response.usage),
            "latency_ms": (end_time - start_time) * 1000,
            "cache_stats": extract_cache_stats(response),  # If available
        }
```

---

## Test Scenarios

### Scenario 1: Single Session Test

Run one coding session with all strategies:

```python
async def test_session():
    """
    Simulate a 30-turn coding session with A/B testing
    """
    tester = CompressionABTest(provider="openai")
    
    messages = [system_prompt]
    
    for turn in range(1, 31):
        # Add new user/assistant messages
        messages.append(generate_turn_messages(turn))
        
        # Test all strategies on this turn
        results = await tester.run_test_turn(messages, turn)
        
        print(f"\nTurn {turn} results:")
        for result in results:
            print(f"  {result['strategy']:12} | "
                  f"{result['tokens_sent']:5} tokens | "
                  f"${result['actual_cost']:.4f} | "
                  f"{result['latency_ms']:.0f}ms")
    
    # Analyze results
    analyze_and_recommend(tester.results)
```

### Scenario 2: Multiple Sessions

Test across different session types:

```python
test_cases = [
    "simple_edits",      # 10 turns, small changes
    "bug_debugging",     # 20 turns, iterative
    "feature_build",     # 50 turns, complex
    "refactoring",       # 30 turns, many file reads
]

for test_case in test_cases:
    results = await run_ab_test(test_case, provider="anthropic")
    save_results(f"results_{provider}_{test_case}.json")
```

---

## Metrics to Track

### Primary Metric: Cost Efficiency

```python
def calculate_cost_efficiency(results):
    """
    For each strategy, calculate:
    - Total cost
    - Cost per turn
    - Cost reduction vs baseline
    """
    baseline_cost = sum(r["actual_cost"] for r in results["none"])
    
    efficiencies = {}
    for strategy, turns in results.items():
        total_cost = sum(r["actual_cost"] for r in turns)
        savings = (baseline_cost - total_cost) / baseline_cost
        
        efficiencies[strategy] = {
            "total_cost": total_cost,
            "cost_per_turn": total_cost / len(turns),
            "savings_pct": savings * 100,
            "cost_vs_baseline": total_cost / baseline_cost
        }
    
    return efficiencies
```

### Secondary Metrics

```python
def analyze_quality_metrics(results):
    """
    Measure if compression affects quality
    """
    for strategy, turns in results.items():
        # Latency impact
        avg_latency = mean(r["latency_ms"] for r in turns)
        
        # Token reduction
        avg_tokens = mean(r["tokens_sent"] for r in turns)
        
        # Response quality (manual review needed)
        # - Did LLM ask to re-read files? (sign of over-compression)
        # - Were responses relevant? (compression preserved context?)
        
        print(f"{strategy}:")
        print(f"  Avg latency: {avg_latency:.0f}ms")
        print(f"  Avg tokens sent: {avg_tokens:.0f}")
```

---

## Detection: Infer Caching Behavior

Even without explicit cache stats, we can infer caching:

```python
def infer_caching_behavior(results):
    """
    Analyze cost patterns to detect caching
    """
    for strategy, turns in results.items():
        costs_per_token = []
        
        for turn in turns:
            cost_per_1k = (turn["actual_cost"] / turn["tokens_sent"]) * 1000
            costs_per_token.append(cost_per_1k)
        
        # Pattern detection
        if costs_per_token[0] > costs_per_token[5] * 1.5:
            print(f"{strategy}: Likely HAS caching (cost dropped)")
            print(f"  Turn 1: ${costs_per_token[0]:.4f}/1K")
            print(f"  Turn 5: ${costs_per_token[5]:.4f}/1K")
        
        # Detect compression breaking cache
        if len(costs_per_token) > 10:
            spike_turns = [i for i, cost in enumerate(costs_per_token[1:], 1)
                          if cost > costs_per_token[i-1] * 1.3]
            
            if spike_turns:
                print(f"{strategy}: Cache breaks detected at turns: {spike_turns}")
```

---

## Auto-Optimization

### Find Best Strategy Automatically

```python
async def find_optimal_strategy(provider: str, test_sessions: int = 5):
    """
    Run multiple test sessions, find best strategy
    """
    all_results = {}
    
    # Run tests
    for session_id in range(test_sessions):
        tester = CompressionABTest(provider)
        session_results = await run_test_session(tester)
        
        for strategy, results in session_results.items():
            if strategy not in all_results:
                all_results[strategy] = []
            all_results[strategy].extend(results)
    
    # Analyze aggregated results
    winner = None
    best_savings = 0
    
    for strategy, results in all_results.items():
        baseline_cost = sum(r["actual_cost"] for r in all_results["none"])
        strategy_cost = sum(r["actual_cost"] for r in results)
        savings = (baseline_cost - strategy_cost) / baseline_cost
        
        print(f"\n{strategy}:")
        print(f"  Total cost: ${strategy_cost:.3f}")
        print(f"  Savings: {savings*100:.1f}%")
        
        if savings > best_savings:
            best_savings = savings
            winner = strategy
    
    print(f"\n🏆 Winner: {winner} ({best_savings*100:.1f}% savings)")
    
    # Save optimal config
    save_optimal_config(provider, winner)
    
    return winner
```

---

## Configuration: Per-Provider Optimization

After testing, generate optimal configs:

```python
# Auto-generated after A/B testing

OPTIMAL_STRATEGIES = {
    "anthropic": {
        "strategy": "aggressive",
        "compress_every_n_turns": 10,
        "use_cache_markers": True,
        "expected_savings": 0.92,
        "tested_on": "2026-05-15",
    },
    "openai": {
        "strategy": "moderate",
        "compress_every_n_turns": 10,
        "use_separators": True,
        "expected_savings": 0.68,
        "tested_on": "2026-05-15",
    },
    "openrouter": {
        "strategy": "extreme",
        "compress_every_n_turns": 5,
        "ignore_cache": True,
        "expected_savings": 0.55,
        "tested_on": "2026-05-15",
    }
}

def get_strategy_for_provider(provider: str):
    config = OPTIMAL_STRATEGIES.get(provider, OPTIMAL_STRATEGIES["openai"])
    return load_strategy(config["strategy"], config)
```

---

## Continuous Testing

### Periodic Re-testing

```python
class ContinuousOptimizer:
    """
    Periodically re-test to adapt to provider changes
    """
    
    def __init__(self):
        self.last_test_date = {}
        self.current_strategies = OPTIMAL_STRATEGIES.copy()
    
    async def maybe_retest(self, provider: str):
        """
        Re-test if:
        - Haven't tested in 30 days
        - Cost anomaly detected
        - Provider API updated
        """
        last_test = self.last_test_date.get(provider)
        
        if not last_test or (datetime.now() - last_test).days > 30:
            print(f"Re-testing {provider} (last test: {last_test})")
            new_optimal = await find_optimal_strategy(provider)
            
            if new_optimal != self.current_strategies[provider]["strategy"]:
                print(f"⚠️ Strategy changed: {self.current_strategies[provider]['strategy']} → {new_optimal}")
                self.current_strategies[provider]["strategy"] = new_optimal
                save_optimal_config(provider, new_optimal)
```

---

## Implementation Plan

### Phase 1: Build A/B Testing Framework

1. Create `ab_tester.py` module
2. Implement parallel strategy execution
3. Add cost tracking
4. Build analysis tools

### Phase 2: Run Initial Tests

1. Test each provider (Anthropic, OpenAI, OpenRouter)
2. Run 10+ sessions per provider
3. Collect data on cost, latency, quality
4. Identify optimal strategy per provider

### Phase 3: Deploy Optimal Configs

1. Generate `optimal_strategies.json`
2. Update proxy to use optimal strategy per provider
3. Monitor production usage

### Phase 4: Continuous Optimization

1. Schedule monthly re-tests
2. Detect cost anomalies (provider changed caching?)
3. Auto-adjust strategies

---

## Benefits of This Approach

### 1. Provider-Agnostic

- ✅ Works with any provider
- ✅ Adapts to provider changes
- ✅ No assumptions about caching

### 2. Data-Driven

- ✅ Actual measured costs (not estimates)
- ✅ Real-world session patterns
- ✅ Statistical validation

### 3. Automatic

- ✅ No manual tuning needed
- ✅ Continuous improvement
- ✅ Self-optimizing

### 4. Safe

- ✅ Always includes baseline (no compression)
- ✅ Can detect quality degradation
- ✅ Rollback if strategy fails

---

## Example Output

```
=== A/B Test Results: OpenAI (GPT-4o) ===

Session: 30 turns, feature development

Strategy      | Total Cost | Savings | Avg Latency | Winner
--------------|------------|---------|-------------|--------
none          | $0.450     | 0.0%    | 1200ms      | 
minimal       | $0.425     | 5.6%    | 1180ms      | 
conservative  | $0.310     | 31.1%   | 1150ms      | 
moderate      | $0.165     | 63.3%   | 1100ms      | 🏆
aggressive    | $0.180     | 60.0%   | 1120ms      | 
extreme       | $0.220     | 51.1%   | 1050ms      | ⚠️ Cache broken

Recommendation: Use "moderate" strategy
- Compress every 10 turns
- Use stable separators
- Expected savings: 63%

Cache behavior detected:
- Turn 1: $5.00/1K tokens (no cache)
- Turn 5: $2.10/1K tokens (cache active ✓)
- Turn 11: $2.15/1K tokens (compression preserved cache ✓)
```

---

## Summary: Your Approach is Perfect!

**What you suggested:**
> "A/B test (automated) by sending to each endpoint with different compression (none→extreme) and see how they consume... treating them as black boxes"

**This is EXACTLY right because:**

1. ✅ No need to reverse-engineer caching
2. ✅ Actual measured costs (ground truth)
3. ✅ Adapts to provider changes
4. ✅ Finds optimal balance (compression vs cache)
5. ✅ Can run continuously to stay optimal

**Implementation priority:** Build this A/B testing framework FIRST, then let it tell us the optimal strategy for each provider!
