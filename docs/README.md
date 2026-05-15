# Context Optimizer — Documentation

Docs are grouped by role. Paths are relative to the `context_optimizer/` project root.

## Planning (`planning/`)

| File | Purpose |
|------|---------|
| [goal.md](planning/goal.md) | Problem, solution, requirements |
| [design.md](planning/design.md) | High-level architecture |
| [backlog.md](planning/backlog.md) | Deferred / future features |
| [fixes_2026-05-15.md](planning/fixes_2026-05-15.md) | Dated session / fix notes |

## Guides (`guides/`)

| File | Purpose |
|------|---------|
| [terminology.md](guides/terminology.md) | Session vs proxy request (turn) vs round |
| [logging_guide.md](guides/logging_guide.md) | Logging modes, disk, full vs minimal |

## Research (`research/`)

| File | Purpose |
|------|---------|
| [compression_research.md](research/compression_research.md) | Findings from logged sessions, phased strategy |
| [ab_testing_strategy.md](research/ab_testing_strategy.md) | A/B testing design |

### Cache deep-dives (`research/cache/`)

| File | Purpose |
|------|---------|
| [prompt_caching_explained.md](research/cache/prompt_caching_explained.md) | KV cache intuition |
| [cache_granularity.md](research/cache/cache_granularity.md) | Prefix / token-level matching |
| [cache_boundaries_explained.md](research/cache/cache_boundaries_explained.md) | Breakpoints, Anthropic `cache_control` |
| [cache_ttl_behavior.md](research/cache/cache_ttl_behavior.md) | 5-minute TTL and idle behavior |
| [proxy_boundary_management.md](research/cache/proxy_boundary_management.md) | Proxy as boundary manager |
| [removal_vs_compression.md](research/cache/removal_vs_compression.md) | Drop vs summarize |
| [provider_caching_comparison.md](research/cache/provider_caching_comparison.md) | Provider-by-provider comparison |

## Implementation (`implementation/`)

| File | Purpose |
|------|---------|
| [IMPLEMENTATION_PLAN.md](implementation/IMPLEMENTATION_PLAN.md) | Phased tasks, cache-aware order, progressive A/B |

**Suggested reading order:** `planning/goal.md` → `research/compression_research.md` → `research/cache/` (as needed) → `implementation/IMPLEMENTATION_PLAN.md`.
