"""
Proxy test script.
Runs two tests against the local Context Optimizer proxy:
  - Test 1: Short message (no compression expected, pure passthrough)
  - Test 2: Long conversation (compression should trigger via cheap model)

Usage:
    python test_proxy.py
    python test_proxy.py --url http://localhost:8000  # override proxy URL
    python test_proxy.py --model anthropic/claude-3-haiku  # override expensive model
"""

import argparse
import json
import urllib.request
import urllib.error
import sys

# ── CLI args ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8000", help="Proxy base URL")
parser.add_argument("--model", default="anthropic/claude-3-haiku", help="Expensive model to test with")
args = parser.parse_args()

PROXY_URL = f"{args.url}/v1/chat/completions"
MODEL = args.model

# ── Helpers ───────────────────────────────────────────────────────────────────
def call_proxy(messages: list, label: str) -> dict:
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        PROXY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[{label}] HTTP {e.code}: {body}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[{label}] Could not reach proxy at {PROXY_URL}: {e.reason}")
        print("Is the proxy running?  →  python main.py")
        sys.exit(1)


def print_result(label: str, result: dict):
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = result.get("usage", {})
    print(f"\n{'='*60}")
    print(f"[{label}] RESPONSE:")
    print(f"  Model:          {result.get('model', 'n/a')}")
    print(f"  Prompt tokens:  {usage.get('prompt_tokens', 'n/a')}")
    print(f"  Output tokens:  {usage.get('completion_tokens', 'n/a')}")
    print(f"  Answer:         {content[:300]}{'...' if len(content) > 300 else ''}")
    print(f"{'='*60}")


# ── Test 1: Short message ─────────────────────────────────────────────────────
print("\n>>> TEST 1: Short message (compression should NOT trigger)")
short_msgs = [
    {"role": "user", "content": "Reply with exactly 3 words: the proxy works."}
]
print(f"  Messages: {len(short_msgs)}  |  ~{sum(len(m['content']) for m in short_msgs)//4} tokens")
result1 = call_proxy(short_msgs, "TEST 1")
print_result("TEST 1", result1)


# ── Test 2: Long conversation ─────────────────────────────────────────────────
print("\n>>> TEST 2: Long conversation (compression SHOULD trigger via cheap model)")
long_msgs = [{"role": "system", "content": "You are a helpful coding assistant."}]
for i in range(8):
    long_msgs.append({
        "role": "user",
        "content": f"Turn {i}: " + "Can you explain Python decorators in detail? " * 80,
    })
    long_msgs.append({
        "role": "assistant",
        "content": f"Turn {i} answer: " + "Decorators wrap functions and modify their behaviour. " * 80,
    })
long_msgs.append({
    "role": "user",
    "content": "Based on everything we discussed, what is the single most important thing to remember about decorators?",
})

total_tokens = sum(len(m["content"]) for m in long_msgs) // 4
print(f"  Messages: {len(long_msgs)}  |  ~{total_tokens} tokens  (threshold: 16000)")
result2 = call_proxy(long_msgs, "TEST 2")
print_result("TEST 2", result2)


# ── Token savings log ─────────────────────────────────────────────────────────
import os
log_path = os.path.join(os.path.dirname(__file__), "logs", "token_savings.jsonl")
if os.path.exists(log_path):
    print("\n>>> TOKEN SAVINGS LOG (last 3 entries):")
    lines = open(log_path).readlines()
    for line in lines[-3:]:
        entry = json.loads(line)
        print(f"  {entry['timestamp']}  |  "
              f"original={entry['original_context_tokens']}  →  "
              f"compressed={entry['compressed_context_tokens']}  |  "
              f"saved {entry['savings_percentage']}%")
else:
    print("\n(No token savings log found — compression may not have triggered yet)")
