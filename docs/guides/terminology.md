# Session Logging Terminology

Understanding what gets logged and when.

---

## Key Concepts

### 1. Session

A **session** is a continuous conversation with the same initial context.

**How it's detected:**
- Hash of the first message (system prompt) stays constant
- When the system prompt changes → new session starts

**Example:** 
- Session 1: Build calculator app (22 proxy requests)
- Session 2: Fix bug in calculator (14 proxy requests)  
- Session 3: Start new project (new session)

**In logs:**
- Each session gets a unique ID (e.g., `session_abc123.jsonl`)
- All proxy requests for that session are logged to the same file

---

### 2. Proxy Request (what we log as "turn")

A **proxy request** is each time Cursor sends an HTTP request to our proxy.

**When it happens:**
- Human user types a message in Cursor
- Agent needs to execute a tool (internal agentic loop)
- Agent needs to continue after receiving tool results

**Example of one human interaction:**

```
Human types: "check the logs"
  ↓
Proxy Request 1 (turn=1): 
  - Messages: [system, user:"check the logs"]
  - LLM responds: tool_use(Shell, "cat logs/last_request.json")
  ↓
Cursor executes tool → gets result
  ↓
Proxy Request 2 (turn=2):
  - Messages: [system, user:"check the logs", assistant:tool_use, user:tool_result]
  - LLM responds: tool_use(Shell, "python3 -c ...")
  ↓
Cursor executes tool → gets result
  ↓
Proxy Request 3 (turn=3):
  - Messages: [system, ..., assistant:tool_use, user:tool_result]
  - LLM responds: "I can see the keys are..."
  ↓
Human sees final response
```

**In logs:**
- Turn 1, 2, 3 are separate log entries
- Each has incrementing turn number
- Each contains the FULL conversation history up to that point

**Key insight:** One human message can result in MULTIPLE proxy requests (turns) due to tool use.

---

### 3. Agentic Round

An **agentic round** is one tool_use → tool_result pair within the conversation.

**Structure:**
```json
{
  "role": "assistant",
  "content": [{"type": "tool_use", "name": "Shell", "input": {...}}]
}
{
  "role": "user", 
  "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]
}
```

**Important for compression:**
- Rounds must stay paired (can't split tool_use from tool_result)
- Old rounds can be removed entirely (both messages)
- Removing just one causes "Tool not found" errors

---

### 4. Human Turn (user perspective)

A **human turn** is one complete human→agent→human interaction.

**From user's perspective:**
- They type one message
- They see one final response
- All the tool calls in between are invisible

**In the proxy:**
- This is actually MULTIPLE proxy requests
- Each tool execution triggers a new request
- The conversation grows with each request

**Example:**

| User Perspective | Proxy Perspective |
|---|---|
| Turn 1: "Build calculator app" | Proxy requests 1-8 (scaffold files, npm install, etc.) |
| Turn 2: "Fix the decimal button bug" | Proxy requests 9-14 (read file, edit, test) |
| Turn 3: "Add styling" | Proxy requests 15-22 (read CSS, update styles) |

---

## What Our Logs Currently Track

**Current behavior:**
- We log each **proxy request** as a "turn"
- `turn=1` means "first proxy request in this session"
- `turn=22` means "22nd proxy request in this session"

**What this means:**
- A 22-turn logged session might represent only 3-5 human interactions
- Most "turns" are internal agentic loops (tool execution)
- The `messages` array grows with each turn (accumulates all previous conversation)

**Example log:**

```jsonl
{"session_id":"abc123","turn":1,"messages":[...3 messages]}
{"session_id":"abc123","turn":2,"messages":[...5 messages]}  ← +2 (tool_use + tool_result)
{"session_id":"abc123","turn":3,"messages":[...7 messages]}  ← +2 (tool_use + tool_result)
{"session_id":"abc123","turn":4,"messages":[...9 messages]}  ← +2 (tool_use + tool_result)
...
```

Each turn contains the FULL conversation so far, not just the delta.

---

## Implications for Analysis

### Token counting:
- Tokens grow with each turn (more conversation history)
- Early turns: ~12K tokens (mostly system prompt)
- Late turns: ~17K tokens (system + conversation)
- Growth is slower than expected because tools dominate the conversation (short text results)

### Compression opportunities:
- Old agentic rounds (tool_use/tool_result pairs) can be removed
- Recent rounds should be kept (last 3-5 turns = last few tool calls)
- System prompt is repeated every turn (never compressed by Cursor)

### Routing decisions:
- Each proxy request should be classified for difficulty
- Simple tool executions → cheap model
- Complex reasoning → expensive model
- But: hard to predict ahead of time what the NEXT request will need

---

## Should We Change the Terminology?

**Options:**

1. **Keep current** (proxy request = "turn")
   - Pros: Accurate from proxy's perspective
   - Cons: Confusing for humans ("22 turns" sounds like a lot)

2. **Rename to "proxy_request" or "api_call"**
   - Pros: Clear what it represents
   - Cons: More verbose, harder to explain

3. **Add "human_turn" counter**
   - Track when user's message content changes
   - Log both: `proxy_request=22, human_turn=5`
   - Pros: Clear for both perspectives
   - Cons: More complex implementation

**Recommendation:** Keep "turn" for proxy requests (simpler), but document clearly that one human interaction = multiple turns.

---

## Quick Reference

| Term | Definition | Example Count in 22-turn Session |
|---|---|---|
| **Session** | Continuous conversation with same context | 1 session |
| **Proxy Request (turn)** | Each HTTP request to proxy | 22 turns |
| **Agentic Round** | One tool_use + tool_result pair | ~15-20 rounds |
| **Human Turn** | One human message + full agent response | ~3-5 human turns |

In a typical session building a calculator app:
- 22 proxy requests (logged "turns")
- ~18 agentic rounds (tool executions)  
- ~5 human turns (what user actually typed)
